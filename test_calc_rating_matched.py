# -*- coding: utf-8 -*-
"""Unit tests for the local-calibration pipeline and observation semantics."""
import json
import math
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

import numpy as np

import calc_rating_matched as app
from rating_local import (AnalysisCancelled, LocalSample, TruncatedFit, _group_folds,
                          bootstrap_local, bootstrap_design, check_cancel, cluster_multiplicities,
                          conditional_prediction_mae, effective_n, fit_truncated,
                          kernel_weights, median_line, weighted_median, weighted_quantile)
from rating_records import AwardRecord, match_records, normalize_grade


def record(name, school, score, province="北京", grade="高一", gender="男", award="一等奖", contest="X"):
    return AwardRecord(contest, award, name, grade, school, float(score), province, gender, "",
                       school.lower(), name.lower(), normalize_grade(grade))


def rules(floor=80):
    return {"北京": app.RuleInfo("北京", floor, floor, "https://example.invalid/rule", "完整门槛", "", floor + 5)}


def synthetic_sample(seed=3, size=1800, mu=110, threshold=100):
    rng = np.random.default_rng(seed)
    x = rng.uniform(120, 180, size)
    y = np.clip(np.round(mu + 0.4 * (x - 150) + rng.normal(0, 25, size)), 0, 400)
    keep = y >= threshold
    ids = np.arange(size)[keep]
    return LocalSample(x[keep], y[keep], 0.15 - (x[keep] - 150) / 1000,
                       np.full(np.count_nonzero(keep), threshold, dtype=float),
                       np.array([f"p{i % 2}|school{i % 40}" for i in ids]),
                       np.array([f"p{i % 2}" for i in ids]),
                       np.full(np.count_nonzero(keep), "高一"))


class MatchingTests(unittest.TestCase):
    def test_strict_school_alias(self):
        alias = {("北京", "简称"): "正式中学"}
        self.assertEqual(app.canonicalize_school("简称", "北京市", alias), "正式中学")

    def test_conflicting_gender_never_links(self):
        for mode in ("strict", "fuzzy"):
            pairs, count, _, _ = match_records([record("a", "school", 300)],
                                                [record("a", "school", 200, gender="女")], mode)
            self.assertEqual(pairs, [])
            self.assertEqual(count, 2)

    def test_missing_gender_is_not_conflict(self):
        pairs, _, _, _ = match_records([record("a", "school", 300, gender="")],
                                       [record("a", "school", 200)])
        self.assertEqual(len(pairs), 1)

    def test_duplicate_identity_not_rescued_by_fuzzy(self):
        c = [record("a", "school", 200), record("a", "school", 300)]
        for mode in ("strict", "fuzzy"):
            pairs, count, _, _ = match_records(c, [record("a", "school", 100)], mode)
            self.assertEqual(pairs, [])
            self.assertEqual(count, 3)

    def test_equal_fuzzy_candidates_stay_ambiguous(self):
        pairs, _, _, _ = match_records([record("a", "schoolabcd", 300)],
                                       [record("a", "schoolabce", 200), record("a", "schoolabcf", 150)], "fuzzy")
        self.assertEqual(pairs, [])

    def test_unique_fuzzy_is_sensitivity_only(self):
        c, n = [record("a", "experimentalschool", 300)], [record("a", "experimentalschoo", 200)]
        self.assertEqual(len(match_records(c, n, "strict")[0]), 0)
        self.assertEqual(match_records(c, n, "fuzzy")[0][0].method, "fuzzy")

    def test_empty_identity_not_linked(self):
        self.assertEqual(match_records([record("", "s", 100)], [record("", "s", 200)])[0], [])

    def test_legacy_grade_masks(self):
        self.assertEqual(normalize_grade("4"), "高一")
        self.assertEqual(normalize_grade("6"), "高三")
        self.assertEqual(normalize_grade("初三"), "九年级")

    def test_loader_deduplicates_identical_rows_with_audit_count(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "school.txt").write_text("北京,北京,school\n", encoding="utf-8")
            row = "X,一等奖,a,高一,school,100,北京,男,\n"
            (root / "raw.txt").write_text(row + row, encoding="utf-8")
            diagnostics = {}
            loaded = app.load_award_records(root, ["X"], diagnostics=diagnostics)
            self.assertEqual(len(loaded["X"]), 1)
            self.assertEqual(diagnostics, {"X": 1})

    def test_loader_rejects_nan(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "school.txt").write_text("北京,北京,school\n", encoding="utf-8")
            (root / "raw.txt").write_text("X,一等奖,a,高一,school,nan,北京,男,\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                app.load_award_records(root, ["X"])


class CountingAndRuleTests(unittest.TestCase):
    def test_percentage_units(self):
        for text, expected in (("1", .01), ("15", .15), ("0.15", .15), ("0.5%", .005)):
            self.assertAlmostEqual(app.parse_percentage(text), expected)

    def test_tie_anchor(self):
        rows = [record("a", "s", 100), record("b", "s", 100), record("c", "s", 90)]
        band = app.score_band_for_top_fraction(rows, 10, .15)
        self.assertEqual((band.strict, band.inclusive), (0, .2))
        self.assertIsNone(app.score_band_for_top_fraction(rows, 10, .4))

    def test_tail_ties_and_between_scores(self):
        tail = app.ScoreTail([record(str(i), "s", v) for i, v in enumerate((120, 100, 100, 90))], 10, rules(), 400)
        result = tail.evaluate(100)
        self.assertEqual((result.known_ge, result.known_gt), (3, 1))
        self.assertAlmostEqual(result.q, .3)
        self.assertEqual(tail.evaluate(100.01).known_ge, 1)
        self.assertEqual(tail.evaluate(100.0000001).known_ge, 3)
        self.assertEqual(tail.evaluate(101).effective_score, 120)

    def test_unobserved_tail_is_not_exact(self):
        tail = app.ScoreTail([record("a", "s", 100)], 10, rules(80), 400)
        result = tail.evaluate(70)
        self.assertIsNone(result.q)
        self.assertEqual(result.known_lower, .1)
        self.assertEqual(result.count_upper, 1)

    def test_official_not_actual_minimum(self):
        rows = [record("a", "s", 100, award="三等奖")]
        parsed = app.load_rule_info(rows, {"provinces": {"北京": {"三等": [80, 1]}}})
        self.assertEqual(parsed["北京"].observation_floor, 80)
        self.assertEqual(parsed["北京"].observed_minimum, 100)

    def test_missing_lower_award_not_zero(self):
        rows = [record("a", "s", 180), record("b", "s", 100, award="二等奖")]
        parsed = app.load_rule_info(rows, {"provinces": {"北京": {"一等": [150, 1], "二等": [None, None]}}})
        self.assertEqual(parsed["北京"].counting_floor, 150)
        self.assertIsNone(parsed["北京"].observation_floor)

    def test_zero_award_province_does_not_constrain_counting_floor(self):
        rows = [record('a', 's', 120, province='甲'), record('b', 's', 150, province='甲')]
        official = {'provinces': {'甲': {'一等': [100, 2]}, '乙': {'一等': [200, 0]}}}
        parsed = app.load_rule_info(rows, official)
        self.assertIn('乙', parsed)
        self.assertFalse(parsed['乙'].constraining)
        self.assertEqual(app.counting_floor(parsed), 100)
        tail = app.ScoreTail(rows, 4, parsed, 400)
        self.assertTrue(tail.evaluate(150).complete)
        self.assertAlmostEqual(tail.evaluate(150).q, .25)

    def test_unknown_zero_award_province_does_not_block(self):
        parsed = app.load_rule_info([record('a', 's', 150)], {'provinces': {
            '北京': {'一等': [100, 1]}, '乙': {'一等': [None, None]}}})
        self.assertEqual(app.counting_floor(parsed), 100)
        self.assertFalse(parsed['乙'].constraining)

    def test_positive_awards_without_line_still_block(self):
        parsed = app.load_rule_info([record('a', 's', 150)], {'provinces': {
            '北京': {'一等': [100, 1]}, '乙': {'一等': [None, 5]}}})
        self.assertIsNone(app.counting_floor(parsed))
        self.assertTrue(parsed['乙'].constraining)

    def test_uncountable_competitor_is_not_dropped_from_stability(self):
        rows = [dict(family='normal', half_width_pp=2, cv_log_loss=4., converged=True,
                     boundary_hit=False, score=120, q=.30),
                dict(family='t5', half_width_pp=2, cv_log_loss=4.01, converged=True,
                     boundary_hit=False, score=120, q=.30),
                dict(family='normal', half_width_pp=5, cv_log_loss=4.02, converged=True,
                     boundary_hit=False, score=60, q=None)]
        compared = app.compare_candidate_models(rows, 4.)
        self.assertIsNone(compared['model_range'])
        self.assertEqual(len(compared['unresolved_comparable_models']), 1)

    def test_contradictory_rule_not_used(self):
        parsed = app.load_rule_info([record("a", "s", 120)], {"provinces": {"北京": {"一等": [150, 1]}}})
        self.assertIsNone(parsed["北京"].counting_floor)
        self.assertIsNone(parsed["北京"].observation_floor)


class NumericalTests(unittest.TestCase):
    def test_actual_weighted_median(self):
        self.assertEqual(weighted_median([0, 10], [9, 1]), 0)
        self.assertEqual(weighted_median([0, 10], [1, 1]), 5)
        self.assertEqual(weighted_quantile([1, 2], [1, 1], 0), 1)
        self.assertEqual(effective_n([1, 1, 1]), 3)

    def test_local_median_recovers_line(self):
        x = np.linspace(100, 200, 101)
        y = 80 + .5 * (x - 150)
        line = median_line(x, y, np.ones(101), 150, 30)
        self.assertAlmostEqual(line.intercept, 80, places=4)
        self.assertAlmostEqual(float(line.predict(180)), 95, places=3)

    def test_kernel_zero_outside_window(self):
        np.testing.assert_allclose(kernel_weights([.1, .15, .2], .15, .02), [0, 1, 0])

    def test_score_bin_probabilities_sum_to_one(self):
        for family in ("normal", "t5"):
            fit = TruncatedFit(family, 110, 0, 30, 150, 20, 400, 0, True, False)
            yy = np.arange(80, 401)
            probability = np.exp(fit.log_prob(np.full(len(yy), 150), yy, np.full(len(yy), 80)))
            self.assertAlmostEqual(float(probability.sum()), 1, places=10)

    def test_bounded_quantile_cdf_inverse(self):
        for family in ("normal", "t5"):
            for mu in (20, 150, 390):
                fit = TruncatedFit(family, mu, 1, 35, 150, 20, 400, 0, True, False)
                median = float(fit.quantile(lower=80))
                self.assertTrue(80 <= median <= 400)
                self.assertAlmostEqual(float(fit.cdf(median, lower=80)), .5, places=7)

    def test_truncated_normal_recovers_hidden_center(self):
        sample = synthetic_sample(size=7000)
        fit = fit_truncated(sample.x, sample.y, sample.lower, np.ones(len(sample)), 150, 20, 400)
        self.assertIsNotNone(fit)
        self.assertTrue(fit.converged)
        self.assertAlmostEqual(fit.intercept, 110, delta=3.0)
        self.assertAlmostEqual(fit.sigma, 25, delta=3.0)
        self.assertLess(abs(float(fit.quantile()) - 110), abs(np.median(sample.y) - 110))

    def test_target_outside_x_not_extrapolated(self):
        sample = synthetic_sample()
        fit = fit_truncated(sample.x, sample.y, sample.lower, np.ones(len(sample)), 400, 20, 400)
        self.assertIsNone(fit)

    def test_reference_prediction_uses_each_actual_x_and_original_floor(self):
        fit = TruncatedFit("normal", 100, 50, 10, 0, 1, 400, 0, True, False)
        x, floors = np.array([-1., 1.]), np.array([0., 130.])
        y = fit.quantile(x=x, lower=np.maximum(0, floors - .5))
        error, predictions = conditional_prediction_mae(fit, x, y, floors, np.ones(2))
        self.assertAlmostEqual(error, 0, places=10)
        self.assertLess(predictions[0], 60)
        self.assertGreater(predictions[1], 140)
        self.assertGreater(float(fit.quantile(lower=130)), 130)

    def test_extreme_normal_tail_remains_a_probability_distribution(self):
        fit = TruncatedFit("normal", -20, 0, 2, 0, 1, 400, 0, True, False)
        med = float(fit.quantile())
        self.assertGreater(med, 0)
        self.assertAlmostEqual(float(fit.cdf(med)), .5, places=9)
        values = np.arange(100, 401)
        probability = np.exp(fit.log_prob(np.zeros(len(values)), values, np.full(len(values), 100)))
        self.assertAlmostEqual(float(probability.sum()), 1, places=9)
        self.assertLess(probability[1], 1e-6)
        self.assertLess(probability[2], 1e-12)

    def test_single_school_strata_do_not_generate_fake_intervals(self):
        x = np.tile(np.linspace(140, 160, 20), 10)
        province = np.repeat([f"p{i}" for i in range(10)], 20)
        sample = LocalSample(x, 100 + .1 * x, .15 - (x - 150) / 1000,
                             np.full(200, 80.), province.copy(), province, np.full(200, "高一"))
        output = bootstrap_local(sample, 150, .15, .05, None, 20, 8, 400)
        self.assertFalse(output['design']['estimable'])
        self.assertEqual(output['baseline'], [])
        self.assertEqual(output['design']['fixed_weight_fraction'], 1)

    def test_school_split_has_no_overlap(self):
        schools = np.array([f"s{i // 5}" for i in range(200)])
        folds = _group_folds(schools, 5)
        for school in np.unique(schools):
            self.assertEqual(len(np.unique(folds[schools == school])), 1)
        self.assertFalse(set(schools[folds == 0]) & set(schools[folds != 0]))

    def test_bootstrap_preserves_school_groups(self):
        sample = synthetic_sample()
        weights = cluster_multiplicities(sample, np.random.default_rng(5))
        for school in np.unique(sample.school):
            self.assertEqual(len(np.unique(weights[sample.school == school])), 1)

    def test_reproducible_baseline_bootstrap(self):
        sample = synthetic_sample(size=500)
        a = bootstrap_local(sample, 150, .15, .05, None, 20, 8, 400)
        b = bootstrap_local(sample, 150, .15, .05, None, 20, 8, 400)
        self.assertEqual(a, b)
        self.assertGreaterEqual(len(a["baseline"]), 18)
        self.assertTrue(all(math.isfinite(v) for v in a["baseline"]))
        self.assertEqual(a["corrected"], [])

    def test_cancellation(self):
        with self.assertRaises(AnalysisCancelled):
            check_cancel(lambda: True)


class RealDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (app.DATA_DIR / "raw.txt").exists() or not (app.DATA_DIR / "school.txt").exists():
            raise unittest.SkipTest("private raw.txt/school.txt are not included in the public repository")
        cls.prepared = app.prepare_year(app.DATA_DIR, 2025)

    def test_official_floors_2025(self):
        self.assertEqual(app.counting_floor(self.prepared.rules["csp"]), 30)
        self.assertEqual(app.counting_floor(self.prepared.rules["noip"]), 86)
        self.assertTrue(app.observation_complete(self.prepared.rules["noip"]))

    def test_known_line_national_count(self):
        p = self.prepared
        tail = app.ScoreTail(p.noip, p.noip_capacity, p.rules["noip"], 400)
        self.assertEqual(tail.evaluate(120).known_ge, 2462)
        self.assertEqual(tail.evaluate(132).known_ge, 1761)
        self.assertEqual(p.noip_capacity, 7548)

    def test_matching_keeps_low_noip_scores(self):
        pairs = [p for p in self.prepared.pairs if p.method == "exact"]
        self.assertGreater(len(pairs), 4000)
        self.assertTrue(any(p.noip.score <= 93 for p in pairs))
        self.assertFalse(any(p.csp.gender and p.noip.gender and p.csp.gender != p.noip.gender for p in pairs))

    def test_same_csp_tie_block_reuses_one_calibration(self):
        fixture = app.LocalLevel(6, .154, reason='test fixture')
        with patch.object(app, '_run_level', return_value=fixture) as run:
            report = app.analyze_year(app.DATA_DIR, 2025, {6:.154, 7:.150}, bootstrap_reps=0)
        self.assertEqual(run.call_count, 1)
        self.assertEqual(report.levels[7].level, 7)
        self.assertEqual(report.levels[7].q_s, .15)
        self.assertIsNot(report.levels[6], report.levels[7])

    def test_inputs_checked_before_analysis(self):
        for levels in ({6:.1, 7:.2}, {6:float('nan'), 7:.1}, {6:.2}, {6:1, 7:.1}):
            with self.assertRaises(ValueError):
                app.analyze_year(app.DATA_DIR, 2025, levels, bootstrap_reps=0)
        with self.assertRaises(ValueError):
            app.analyze_year(app.DATA_DIR, 2025, {6:.2, 7:.1}, seed=-1)

    def test_all_supported_years_have_auditable_baselines(self):
        for year in range(2020, 2026):
            report = app.analyze_year(app.DATA_DIR, year, {6:.15, 7:.075}, bootstrap_reps=0)
            for level in report.levels.values():
                self.assertTrue(level.available)
                self.assertIsNotNone(level.baseline)
                self.assertIn(level.selected_method, {"visible_baseline", "corrected"})
            json.loads(app.report_to_json(report))
            self.assertNotIn("quality_grade", app.report_to_json(report))


if __name__ == "__main__":
    unittest.main()
