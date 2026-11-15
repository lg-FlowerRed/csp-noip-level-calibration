#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Local CSP-S boundary calibration, with audited award-truncation correction.

CLI and GUI share this report. Visible-cohort baselines, conditional model
estimates, counting bounds, bootstrap intervals and missing-mass scenarios
remain separate. Provincial quotas/estimated participation are never inputs.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from functools import lru_cache
import json
import math
from pathlib import Path
import sys
from typing import Optional

from rating_records import (
    DATA_DIR, AWARDS, LEVEL_DEFAULTS, AwardRecord, MatchedPair, TieBand,
    available_years, canonicalize_school, capacity_of, default_year,
    load_award_records, load_contests, load_school_aliases, match_records,
    normalize_grade, normalize_name, score_band_for_top_fraction, score_percentile_map,
)

NUMERICAL_IMPORT_ERROR = None
try:
    import numpy as np
    from rating_local import (AnalysisCancelled, BANDWIDTHS, LocalSample, bootstrap_local,
                              check_cancel, effective_n, fit_truncated, kernel_weights,
                              median_line, validate_local, weighted_quantile)
except ImportError as exc:
    NUMERICAL_IMPORT_ERROR = exc

VERSION = "3.0-local"
METHODS = {"corrected": "局部截断校正（模型条件推荐）",
           "visible_baseline": "仅可见获奖者基线，不作唯一全国建议",
           "unavailable": "边界样本不足或锚点不可识别"}
FAMILY_LABELS = {"normal": "有界正态", "t5": "有界厚尾 t(5)"}


@dataclass
class RuleInfo:
    province: str
    counting_floor: Optional[float]
    observation_floor: Optional[float]
    source_url: str
    status: str
    reason: str
    observed_minimum: Optional[float]
    constraining: bool = True


@dataclass
class TailResult:
    score: float
    effective_score: Optional[float]
    known_ge: int
    known_gt: int
    q: Optional[float]
    strict_q: Optional[float]
    known_lower: float
    count_upper: float
    complete: bool
    status: str


@dataclass
class LocalLevel:
    level: int
    q_s: float
    available: bool = False
    reason: str = ""
    csp_score: Optional[float] = None
    csp_strict: Optional[float] = None
    csp_inclusive: Optional[float] = None
    anchor_verified: bool = False
    selected_method: str = "unavailable"
    adoption_reasons: list = field(default_factory=list)
    half_width_pp: float = 2.0
    local_pairs: int = 0
    effective_n: float = 0.0
    schools: int = 0
    provinces: int = 0
    visible_iqr: list = field(default_factory=list)
    baseline: Optional[TailResult] = None
    corrected: Optional[TailResult] = None
    selected: Optional[TailResult] = None
    model_family: Optional[str] = None
    model_parameters: dict = field(default_factory=dict)
    estimated_missing_mass: Optional[float] = None
    common_floor: Optional[float] = None
    candidates: list = field(default_factory=list)
    validation: dict = field(default_factory=dict)
    bootstrap: dict = field(default_factory=dict)
    sensitivity: dict = field(default_factory=dict)
    scenarios: list = field(default_factory=list)
    local_points: list = field(default_factory=list)
    model_curve: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


@dataclass
class AnalysisReport:
    version: str
    year: int
    settings: dict
    data_summary: dict
    match: dict
    rules: dict
    levels: dict
    province_diagnostics: list
    sources: list
    warnings: list
    sections: dict = field(default_factory=dict)


@dataclass
class PreparedYear:
    contests: dict
    csp: list
    noip: list
    pairs: list
    ambiguous: int
    rules: dict
    csp_capacity: int
    noip_capacity: int
    noip_maximum: float
    fingerprint: tuple
    duplicate_counts: dict


def require_dependencies():
    if NUMERICAL_IMPORT_ERROR is not None:
        raise RuntimeError("缺少 NumPy/SciPy，请先运行：py -m pip install -r requirements.txt") from NUMERICAL_IMPORT_ERROR


def fmt_pct(value):
    return "—" if value is None or not math.isfinite(float(value)) else f"{value * 100:.2f}%"


def fmt_score(value):
    return "—" if value is None or not math.isfinite(float(value)) else f"{value:.2f}".rstrip("0").rstrip(".")


def fmt_int(value):
    return "—" if value is None else f"{value:,.0f}"


def parse_percentage(value):
    text = str(value).strip()
    if text.endswith(("%", "％")):
        return float(text[:-1]) / 100
    number = float(text)
    return number / 100 if number >= 1 else number


def dataset_fingerprint(data_dir):
    paths = ("contests.json", "raw.txt", "school.txt", "province_cutoffs.json")
    root = Path(data_dir)
    return tuple((p, (root / p).stat().st_mtime_ns, (root / p).stat().st_size)
                 if (root / p).exists() else (p, None, None) for p in paths)


def load_rule_info(records, official):
    """Counting above a known award line differs from modelling all awards.

    Missing lower-prize rules do not become zeros or observed minima. A known
    first-prize line can certify a high-tail count, but cannot describe the
    inclusion mechanism of all second/third prize records.
    """
    by_province = defaultdict(list)
    for record in records:
        by_province[record.province].append(record)
    result = {}
    published = official.get("provinces", {})
    for province in sorted(set(by_province) | set(published)):
        rows = by_province.get(province, [])
        table = published.get(province, {})
        values = {}
        invalid = False
        for short in ("一等", "二等", "三等"):
            cell = table.get(short)
            if cell and cell[0] is not None:
                value = cell[0]
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                    invalid = True
                else:
                    values[short + "奖"] = float(value)
        inconsistent = any(r.award in values and r.score < values[r.award] for r in rows)
        lowest_observed_award = max({r.award for r in rows}, key=AWARDS.index, default="最低奖项")
        needed = {r.award for r in rows}
        known = bool(values) and not invalid and not inconsistent
        lower_complete = known and needed.issubset(values)
        # A province with no award records and no positive published count has
        # nobody who could be missed; it must not block the national floor.
        positive_published = any(cell and len(cell) > 1 and cell[1] and cell[1] > 0
                                 for cell in table.values())
        zero_award = not rows and not positive_published
        # Also include explicitly published lower lines with zero recipients.
        floor = min(values.values()) if known else None
        reason = ("该省无获奖记录，不构成全国门槛约束" if zero_award else
                  "原始分数低于对应官方奖项线，需核对" if inconsistent else
                  "规则含非法门槛值" if invalid else
                  "未收录该省官方分数线" if not known else
                  f"缺少{lowest_observed_award}等最低获奖规则，仅高分计数可核对" if not lower_complete else
                  "本地官方门槛与已收录各奖项分数一致")
        result[province] = RuleInfo(province, floor, floor if lower_complete else None,
                                    official.get("source_url", ""),
                                    "无获奖" if zero_award else "完整门槛" if lower_complete else "部分门槛" if known else "未核实",
                                    reason, min((r.score for r in rows), default=None),
                                    constraining=not zero_award)
    return result


@lru_cache(maxsize=3)
def _prepare_cached(root_string, year, fingerprint):
    root = Path(root_string)
    contests = load_contests(root)
    csp_name, noip_name = f"CSP{year}提高", f"NOIP{year}"
    if csp_name not in contests or noip_name not in contests:
        raise ValueError(f"{year} 年没有可配对的 CSP-S/NOIP 数据。")
    nc, nn = capacity_of(contests[csp_name]), capacity_of(contests[noip_name])
    if nc is None or nn is None:
        raise ValueError("缺少全国实际参赛人数 capacity。")
    duplicate_counts = {}
    records = load_award_records(root, [csp_name, noip_name], diagnostics=duplicate_counts)
    csp, noip = records[csp_name], records[noip_name]
    for name, rows, total in ((csp_name, csp, nc), (noip_name, noip, nn)):
        if not rows or len(rows) > total:
            raise ValueError(f"{name} 获奖记录为空或超过实际参赛人数。")
        maximum = float(contests[name]["full_score"])
        if any(r.score > maximum for r in rows):
            raise ValueError(f"{name} 含超过满分的成绩。")
    official_path = root / "province_cutoffs.json"
    official = {}
    if official_path.exists():
        with official_path.open(encoding="utf-8-sig") as handle:
            official = json.load(handle).get("contests", {})
    rules = {"csp": load_rule_info(csp, official.get(csp_name, {})),
             "noip": load_rule_info(noip, official.get(noip_name, {}))}
    pairs, ambiguous, _, _ = match_records(csp, noip, mode="fuzzy")
    return PreparedYear(contests, csp, noip, pairs, ambiguous, rules, nc, nn,
                        float(contests[noip_name]["full_score"]), fingerprint, duplicate_counts)


def prepare_year(data_dir, year):
    root = Path(data_dir).resolve()
    return _prepare_cached(str(root), year, dataset_fingerprint(root))


def counting_floor(rules):
    constraining = [r for r in (rules or {}).values() if r.constraining]
    if not constraining or any(r.counting_floor is None for r in constraining):
        return None
    return max(r.counting_floor for r in constraining)


def observation_complete(rules):
    constraining = [r for r in (rules or {}).values() if r.constraining]
    return bool(constraining) and all(r.observation_floor is not None for r in constraining)


class ScoreTail:
    def __init__(self, records, capacity, rules, maximum):
        self.values = np.sort([r.score for r in records])
        self.capacity = capacity
        self.floor = counting_floor(rules)
        self.maximum = maximum

    def evaluate(self, score):
        score = float(score)
        if not math.isfinite(score) or not 0 <= score <= self.maximum:
            raise ValueError("候选分数线不在合法成绩范围内。")
        # Remove only optimization round-off near an actually observed score;
        # e.g. 118.00000017 must not accidentally exclude all 118-point ties.
        near = int(np.searchsorted(self.values, score, side="left"))
        for i in (near - 1, near):
            if 0 <= i < len(self.values) and abs(float(self.values[i]) - score) <= 1e-6:
                score = float(self.values[i])
                break
        index = int(np.searchsorted(self.values, score, side="left"))
        right = int(np.searchsorted(self.values, score, side="right"))
        ge, gt = len(self.values) - index, len(self.values) - right
        complete = self.floor is not None and score >= self.floor
        lower = ge / self.capacity
        upper = min(1.0, (ge + self.capacity - len(self.values)) / self.capacity)
        return TailResult(score, float(self.values[index]) if index < len(self.values) else None,
                          ge, gt, lower if complete else None, gt / self.capacity if complete else None,
                          lower, lower if complete else upper, complete,
                          "固定分数线以上可完整计数（依赖已收录官方规则）" if complete else
                          "仅已知获奖人数下界；固定分数线计数上界含所有未知成绩")


def _make_sample(pairs, csp_map, rules):
    return LocalSample(
        np.array([p.csp.score for p in pairs]), np.array([p.noip.score for p in pairs]),
        np.array([csp_map[p.csp.score].midpoint for p in pairs]),
        np.array([rules[p.noip.province].observation_floor
                  if rules[p.noip.province].observation_floor is not None else np.nan for p in pairs]),
        np.array([p.noip.province + "|" + p.noip.canonical_school for p in pairs]),
        np.array([p.noip.province for p in pairs]), np.array([p.noip.normalized_grade for p in pairs]),
    )


def _interval(scores, tail, requested):
    valid = len(scores)
    if requested == 0:
        return {"requested": 0, "valid": 0, "score_interval": None, "ratio_interval": None,
                "label": "未执行重抽"}
    if valid < max(20, math.ceil(requested * 0.8)):
        return {"requested": requested, "valid": valid, "score_interval": None, "ratio_interval": None,
                "label": "有效重抽不足，不报告95%区间"}
    score_interval = [float(v) for v in np.quantile(scores, [0.025, 0.975])]
    counts = [tail.evaluate(s) for s in scores]
    # No silent dropping of uncountable draws: retain score CI and withhold q CI.
    ratio_interval = ([float(v) for v in np.quantile([r.q for r in counts], [0.025, 0.975])]
                      if all(r.complete for r in counts) else None)
    return {"requested": requested, "valid": valid, "score_interval": score_interval,
            "ratio_interval": ratio_interval,
            "label": "95%近似重抽区间；固定所选分布/带宽，不含模型选择和未知缺失机制",
            "low_repetitions": requested < 200}


def compare_candidate_models(candidates, best_loss):
    comparable = [r for r in candidates if r["cv_log_loss"] is not None and r["cv_log_loss"] <= best_loss + 0.15]
    unresolved = [r for r in comparable if not r["converged"] or r["boundary_hit"] or r.get("q") is None]
    qs = [r["q"] for r in comparable if r not in unresolved]
    scores = [r["score"] for r in comparable if r["score"] is not None]
    return {
        "model_range": [min(qs), max(qs)] if qs and not unresolved else None,
        "model_score_range": [min(scores), max(scores)] if scores else None,
        "known_candidate_ratio_range": [min(qs), max(qs)] if qs else None,
        "unresolved_comparable_models": [{"family": r["family"], "half_width_pp": r["half_width_pp"]} for r in unresolved],
        "comparable_families": sorted({r["family"] for r in comparable}),
        "model_range_label": "样本外对数损失在最优值+0.15以内的同目标模型范围；有未知/不可计数候选时不认证稳定，非95%区间",
    }


def _run_level(level, q, prepared, strict_pairs, all_pairs, reps, seed, fuzzy_sensitivity, progress, cancel):
    result = LocalLevel(level, q)
    band = score_band_for_top_fraction(prepared.csp, prepared.csp_capacity, q)
    if band is None:
        result.reason = "目标 CSP-S 比例超出完整获奖名单的已观测范围。"
        return result
    result.csp_score, result.csp_strict, result.csp_inclusive = band.score, band.strict, band.inclusive
    csp_floor = counting_floor(prepared.rules["csp"])
    result.anchor_verified = csp_floor is not None and band.score >= csp_floor
    csp_map = score_percentile_map(prepared.csp, prepared.csp_capacity)
    nearby = [p for p in strict_pairs if abs(csp_map[p.csp.score].midpoint - band.midpoint) < max(BANDWIDTHS)]
    sample = _make_sample(nearby, csp_map, prepared.rules["noip"])
    if len(sample) < 30 or not (sample.x.min() <= band.score <= sample.x.max()):
        result.reason = "边界附近配对不足30人或不覆盖分数线两侧，不外推。"
        return result
    tail = ScoreTail(prepared.noip, prepared.noip_capacity, prepared.rules["noip"], prepared.noip_maximum)
    result.common_floor = tail.floor
    all_rules = observation_complete(prepared.rules["noip"])
    can_correct = result.anchor_verified and all_rules and np.all(np.isfinite(sample.lower))
    selected_model, full_fits, selected_row = None, {}, None
    bandwidth = 0.02
    if can_correct:
        selected_row, candidates, validation, full_fits = validate_local(
            sample, band.score, band.midpoint, prepared.noip_maximum, seed, cancel,
            lambda msg: progress(f"{level}级：{msg}"))
        result.candidates, result.validation = candidates, validation
        if selected_row:
            bandwidth = selected_row["half_width_pp"] / 100
            selected_model = full_fits[(selected_row["family"], bandwidth)]
    else:
        result.validation = {"passed": False, "reason": "CSP-S 锚点或 NOIP 最低获奖门槛未完整核实；只计算可见基线。", "trials": []}
        result.warnings.append("缺失的官方门槛未用实际最低获奖分代替。")
    def supported_window(ww):
        xx = sample.x[ww > 0]
        return len(xx) >= 30 and xx.min() <= band.score <= xx.max()
    weights = kernel_weights(sample.p, band.midpoint, bandwidth)
    if not supported_window(weights):
        bandwidth = next((h for h in BANDWIDTHS if supported_window(kernel_weights(sample.p, band.midpoint, h))), None)
        if bandwidth is None:
            result.reason = "候选窗口均未覆盖边界两侧或人数不足，不外推局部线。"
            return result
        weights = kernel_weights(sample.p, band.midpoint, bandwidth)
    active = weights > 0
    x_scale = selected_model.x_scale if selected_model else max(1.0, float(np.std(sample.x[active])))
    baseline_line = median_line(sample.x, sample.y, weights, band.score, x_scale)
    if not 0 <= baseline_line.intercept <= prepared.noip_maximum:
        result.reason = "局部中位数线超出合法分数范围，样本不支持该锚点。"
        return result
    result.available = True
    result.baseline = tail.evaluate(baseline_line.intercept)
    result.selected, result.selected_method = result.baseline, "visible_baseline"
    result.half_width_pp = bandwidth * 100
    result.local_pairs = int(np.count_nonzero(active))
    result.effective_n = effective_n(weights)
    result.schools = len(np.unique(sample.school[active]))
    result.provinces = len(np.unique(sample.province[active]))
    # This is person-to-person spread, NOT uncertainty of an estimated median.
    result.visible_iqr = [float(v) for v in weighted_quantile(sample.y, weights, [0.25, 0.5, 0.75])]
    result.local_points = [[float(x), float(y)] for x, y in zip(sample.x[active], sample.y[active])]
    for row in result.candidates:
        if row["score"] is not None:
            counted = tail.evaluate(row["score"])
            row["q"] = counted.q
            row["missing_mass"] = (float(full_fits[(row["family"], row["half_width_pp"] / 100)].cdf(tail.floor - 0.5))
                                   if tail.floor is not None else None)
        row["selected"] = bool(selected_row and row is selected_row)

    if selected_model:
        result.corrected = tail.evaluate(float(selected_model.quantile()))
        result.model_family = selected_model.family
        result.model_parameters = asdict(selected_model)
        result.estimated_missing_mass = (float(selected_model.cdf(max(0, tail.floor - 0.5))) if tail.floor is not None else None)
        # Compare only models of the SAME target with reasonable held-out fit.
        result.sensitivity.update(compare_candidate_models(result.candidates, selected_row["cv_log_loss"]))
        model_range = result.sensitivity["model_range"]
        span = model_range[1] - model_range[0] if model_range else None
        reasons = []
        if result.sensitivity["unresolved_comparable_models"]:
            reasons.append("存在同等验证表现但无法稳定拟合/完整计数的竞争模型，不能将未知差异当作一致。")
        if not result.validation.get("passed"):
            reasons.append(result.validation.get("reason", "未通过遮挡回测"))
        if result.effective_n < 100 or result.schools < 10:
            reasons.append("有效边界样本少于100或学校少于10。")
        if not result.corrected.complete:
            reasons.append("校正候选线以上的全国人数不能完整计数。")
        if selected_model.boundary_hit:
            reasons.append("模型参数撞到约束边界。")
        if len(result.sensitivity["comparable_families"]) < 2:
            reasons.append("仅一种分布通过可比验证，尾部分布稳健性不足。")
        if span is None or span > 0.05:
            reasons.append("同目标模型的全国比例跨度超过5个百分点或无法比较。")
        if result.estimated_missing_mass is None or result.estimated_missing_mass >= 0.5:
            reasons.append("模型中位数落在共同可见门槛以下，尾部校正不可可靠定位。")
        result.adoption_reasons = reasons
        if not reasons:
            result.selected, result.selected_method = result.corrected, "corrected"
            result.adoption_reasons = ["通过预设遮挡恢复、有效样本量、计数覆盖与同目标模型稳定性检查。"]
        xx = np.linspace(float(sample.x[active].min()), float(sample.x[active].max()), 60)
        result.model_curve = [[float(x), float(y)] for x, y in zip(xx, selected_model.quantile(x=xx))]
    else:
        result.adoption_reasons = (["最终全样本拟合未收敛，不能给出校正候选。"] if selected_row else
                                   [result.validation.get("reason", "没有可靠截断模型")])

    # Transparent local baseline at every bandwidth, independent of adoption.
    bands = []
    for h in BANDWIDTHS:
        ww = kernel_weights(sample.p, band.midpoint, h)
        if np.count_nonzero(ww) < 15:
            continue
        line = median_line(sample.x, sample.y, ww, band.score, x_scale)
        bands.append({"half_width_pp": h * 100, "n": int(np.count_nonzero(ww)),
                      "effective_n": effective_n(ww), "median_score": line.intercept,
                      "q": tail.evaluate(line.intercept).q})
    result.sensitivity["bandwidth_baselines"] = bands

    # Common-threshold scenarios use the observable cohort above that SAME line.
    # They are not measurements of the missing proportion and never auto-adopted.
    if tail.floor is not None:
        common = active & (sample.y >= tail.floor)
        scenario_w = weights[common]
        if np.count_nonzero(common) >= 15:
            # Raw G is deliberately used; label it a window sensitivity, not a fitted correction.
            for pi in (0.0, 0.10, 0.20, 0.30, 0.40, 0.50):
                score = None if pi >= 0.5 else float(weighted_quantile(sample.y[common], scenario_w, (0.5 - pi) / (1 - pi)))
                result.scenarios.append({"assumed_missing_mass": pi, "visible_quantile": None if pi >= 0.5 else (0.5 - pi) / (1 - pi),
                                         "score": score, "q": tail.evaluate(score).q if score is not None else None,
                                         "status": "假设情景，非实测、非置信区间" if score is not None else "中位数在门槛以下，不能定位"})
            result.sensitivity["scenario_n"] = int(np.count_nonzero(common))
            result.sensitivity["scenario_note"] = "共同门槛以上窗口内加权经验分布；不含局部斜率校正，因此π=0可不同于局部线性基线"

    if fuzzy_sensitivity:
        extra = [p for p in all_pairs if abs(csp_map[p.csp.score].midpoint - band.midpoint) < bandwidth]
        alt = _make_sample(extra, csp_map, prepared.rules["noip"])
        ww = kernel_weights(alt.p, band.midpoint, bandwidth)
        if len(alt) >= 30:
            other = median_line(alt.x, alt.y, ww, band.score, x_scale).intercept
            result.sensitivity["fuzzy_extra_pairs"] = sum(p.method == "fuzzy" for p in extra)
            result.sensitivity["fuzzy_baseline_score_shift"] = other - result.baseline.score
            if selected_model and np.all(np.isfinite(alt.lower)):
                fit = fit_truncated(alt.x, alt.y, alt.lower, ww, band.score, x_scale,
                                    prepared.noip_maximum, selected_model.family, selected_model)
                result.sensitivity["fuzzy_corrected_score_shift"] = (float(fit.quantile()) - result.corrected.score) if fit else None

    # Leave-one-province and the largest schools measure local composition effects.
    influence = []
    major_schools = Counter(sample.school[active]).most_common(3)
    removals = [("省份", p, sample.province == p) for p in np.unique(sample.province[active])]
    removals += [("学校", s, sample.school == s) for s, _ in major_schools]
    for kind, label, remove in removals:
        check_cancel(cancel)
        ww = weights.copy(); ww[remove] = 0
        if np.count_nonzero(ww) < 40 or not (sample.x[ww > 0].min() <= band.score <= sample.x[ww > 0].max()):
            continue
        if selected_model:
            fit = fit_truncated(sample.x, sample.y, sample.lower, ww, band.score, x_scale,
                                prepared.noip_maximum, selected_model.family, selected_model)
            other = float(fit.quantile()) if fit and not fit.boundary_hit else None
            reference = result.corrected
        else:
            other = median_line(sample.x, sample.y, ww, band.score, x_scale).intercept
            reference = result.baseline
        counted = tail.evaluate(other) if other is not None else None
        influence.append({"kind": kind, "label": label, "score_shift": other - reference.score if other is not None else None,
                          "q_shift": counted.q - reference.q if counted and counted.q is not None and reference.q is not None else None})
    result.sensitivity["leave_one_out"] = influence
    max_shift = max((abs(r["q_shift"]) for r in influence if r["q_shift"] is not None), default=0)
    if max_shift > 0.05:
        result.warnings.append("删去一个省或一个大学校后比例变化超过5个百分点。")
        if result.selected_method == "corrected":
            result.selected_method, result.selected = "visible_baseline", result.baseline
            result.adoption_reasons = ["省份/学校影响超过预设范围，校正不作主推荐。"]

    progress(f"{level}级：计算学校整组重抽区间")
    draws = bootstrap_local(sample, band.score, band.midpoint, bandwidth, selected_model, reps, seed + 70,
                            prepared.noip_maximum, cancel, lambda msg: progress(f"{level}级：{msg}"))
    result.bootstrap = {key: _interval(draws[key], tail, reps) for key in ("baseline", "corrected")}
    result.bootstrap["design"] = draws["design"]
    if not draws["design"]["estimable"]:
        result.warnings.append("各省局部样本均仅1校，分层学校重抽没有可估计变异；不报告虚假的零宽区间。")
        for key in ("baseline", "corrected"):
            result.bootstrap[key]["label"] = "省内没有至少2个学校的可重抽分层，无法估计该95%区间"
        if result.selected_method == "corrected":
            result.selected_method, result.selected = "visible_baseline", result.baseline
            result.adoption_reasons = ["现有学校分层无法估计所声明的重抽不确定性。"]
    elif draws["design"]["fixed_single_school_provinces"]:
        result.warnings.append("部分省份局部样本只有1校，重抽中视为固定分层，其组间不确定性未估计："
                               + "、".join(draws["design"]["fixed_single_school_provinces"])
                               + f"（局部权重{fmt_pct(draws['design']['fixed_weight_fraction'])}）")
    if selected_model and reps and result.bootstrap["corrected"]["score_interval"] is None:
        result.warnings.append("校正模型有效重抽不足，未报告区间。")
        if result.selected_method == "corrected":
            result.selected_method, result.selected = "visible_baseline", result.baseline
            result.adoption_reasons = ["校正模型在重抽中不稳定。"]
    if not result.anchor_verified:
        result.warnings.append("CSP-S 全国锚点采用获奖尾部近似，官方门槛覆盖不足，不能认证为精确全国百分位。")
    result.warnings.append("未匹配者未被视作0分或未获奖；未知尾部的校正依赖分布和匹配机制假设。")
    return result


def analyze_year(data_dir, year, qs_by_level, bootstrap_reps=1000, seed=2026,
                 match_mode="strict", progress=None, cancel=None):
    require_dependencies()
    progress = progress or (lambda message: None)
    if set(qs_by_level) != {6, 7} or not all(math.isfinite(float(q)) and 0 < q < 1 for q in qs_by_level.values()):
        raise ValueError("必须提供6级与7级，且比例均在0%到100%之间。")
    if qs_by_level[7] >= qs_by_level[6]:
        raise ValueError("7级累计比例必须小于6级累计比例。")
    if not isinstance(bootstrap_reps, int) or not 0 <= bootstrap_reps <= 10000:
        raise ValueError("重抽次数必须是0到10000之间的整数。")
    if not isinstance(seed, int) or seed < 0:
        raise ValueError("随机种子必须为非负整数。")
    if match_mode not in ("strict", "fuzzy"):
        raise ValueError("匹配模式必须为strict或fuzzy；fuzzy仅用于敏感性，主分析始终严格匹配。")
    check_cancel(cancel)
    progress("读取本地数据、核对官方获奖门槛与身份匹配…")
    prepared = prepare_year(data_dir, year)
    strict = [p for p in prepared.pairs if p.method == "exact"]
    levels, by_score = {}, {}
    for level in (6, 7):
        anchor = score_band_for_top_fraction(prepared.csp, prepared.csp_capacity, qs_by_level[level])
        if anchor is not None and anchor.score in by_score:
            estimate = deepcopy(by_score[anchor.score])
            estimate.level, estimate.q_s = level, qs_by_level[level]
            estimate.warnings.append("两级锚点落在同一个CSP-S同分块，复用同一标定与区间，不因随机划分产生两条不同线。")
        else:
            estimate = _run_level(level, qs_by_level[level], prepared, strict, prepared.pairs,
                                  bootstrap_reps, seed + level * 100, match_mode == "fuzzy", progress, cancel)
            if anchor is not None:
                by_score[anchor.score] = estimate
        levels[level] = estimate
    warnings = ["只使用现有资料；未读取省参赛估算/名额作分母，也未估计不存在的个人成绩。",
                "全国计数完整性依赖获奖名单完整、所收录地区与资格口径一致、官方门槛足以保证入奖。",
                "采用检验是操作性门槛，不是无条件准确性证明；未通过时不会用可见基线冒充总体中位数。"]
    if prepared.duplicate_counts:
        warnings.append("完全相同的重复行已仅计一次，源文件未改：" + str(prepared.duplicate_counts))
    if bootstrap_reps < 200:
        warnings.append("重抽少于200次：仅作快速探索，区间精度有限；0次表示未执行。")
    a, b = levels[6], levels[7]
    for attribute in ("corrected", "baseline"):
        x, y = getattr(a, attribute), getattr(b, attribute)
        if x and y and x.score > y.score + 1e-8:
            warnings.append(f"两级{attribute}分数线发生交叉，未强行裁剪；不提供校正主推荐。")
            for level in levels.values():
                if level.available:
                    level.selected_method, level.selected = "visible_baseline", level.baseline
                    level.adoption_reasons = ["两级单调嵌套关系未通过。"]
    # Do not let a hybrid corrected/baseline display reverse the grade ordering.
    if a.selected and b.selected and a.selected.score > b.selected.score + 1e-8:
        warnings.append("混合口径主显示会交叉，统一显示两级可见基线，校正另列。")
        for level in levels.values():
            level.selected_method, level.selected = "visible_baseline", level.baseline
            level.adoption_reasons = ["避免混合口径导致等级交叉。"]

    csp_counts = Counter(r.province for r in prepared.csp)
    noip_counts = Counter(r.province for r in prepared.noip)
    linked = Counter(p.noip.province for p in strict)
    diagnostics = [{"province": p, "csp_awards": csp_counts[p], "noip_awards": noip_counts[p],
                    "strict_matches": linked[p], "award_match_rate": linked[p] / noip_counts[p] if noip_counts[p] else None,
                    "csp_rule": asdict(prepared.rules["csp"][p]) if p in prepared.rules["csp"] else None,
                    "noip_rule": asdict(prepared.rules["noip"][p]) if p in prepared.rules["noip"] else None}
                   for p in sorted(csp_counts.keys() | noip_counts.keys() | prepared.rules["csp"].keys() | prepared.rules["noip"].keys())]
    rules = {name: {p: asdict(rule) for p, rule in mapping.items()} for name, mapping in prepared.rules.items()}
    report = AnalysisReport(VERSION, year,
        {"q_s": qs_by_level, "bootstrap": bootstrap_reps, "seed": seed, "match_mode": match_mode,
         "estimand": "实际NOIP参赛者在CSP-S等级边界处的条件成绩中位数；可见获奖者基线单独报告",
         "data_fingerprint": prepared.fingerprint},
        {"csp_capacity": prepared.csp_capacity, "noip_capacity": prepared.noip_capacity,
         "csp_awards": len(prepared.csp), "noip_awards": len(prepared.noip),
         "csp_award_counts": dict(Counter(r.award for r in prepared.csp)),
         "noip_award_counts": dict(Counter(r.award for r in prepared.noip)),
         "csp_counting_floor": counting_floor(prepared.rules["csp"]),
         "noip_counting_floor": counting_floor(prepared.rules["noip"]),
         "duplicate_records_removed": prepared.duplicate_counts,
         "official_noip_observation_rules_complete": observation_complete(prepared.rules["noip"])},
        {"strict": len(strict), "fuzzy_extra": len(prepared.pairs) - len(strict), "ambiguous_records": prepared.ambiguous,
         "noip_unmatched_award_records": len(prepared.noip) - len(strict),
         "noip_award_match_rate": len(strict) / len(prepared.noip),
         "csp_unmatched_award_records": len(prepared.csp) - len(strict)},
        rules, levels, diagnostics,
        sorted({r.source_url for group in prepared.rules.values() for r in group.values() if r.source_url}), warnings)
    report.sections = report_sections(report)
    progress("计算完成。")
    return report


def describe_tail(result):
    if result is None:
        return "未计算"
    if result.complete:
        value = fmt_pct(result.q)
    else:
        value = f"至少{fmt_pct(result.known_lower)}；固定分数线计数范围至{fmt_pct(result.count_upper)}"
    return f"{fmt_score(result.score)}分 → {value}（名单中≥线{result.known_ge}人）"


def describe_interval(item):
    if not item or item.get("score_interval") is None:
        return (item or {}).get("label", "未执行")
    low, high = item["score_interval"]
    text = f"分数线[{fmt_score(low)}, {fmt_score(high)}]"
    if item.get("ratio_interval") is not None:
        a, b = item["ratio_interval"]
        text += f"；比例[{fmt_pct(a)}, {fmt_pct(b)}]"
    else:
        text += "；部分重抽分数线无法完整计数，未报告比例区间"
    return text + f"；有效{item['valid']}/{item['requested']}次"


def report_sections(report):
    summary = [f"{report.year}年 CSP-S → NOIP 局部标定", "目标：边界选手的典型 NOIP 表现（条件中位数）", ""]
    validation = ["学校分组与人工遮挡验证", "模型选择：留出1/5学校作为独立审计集，其余学校内三折选分布和窗口。",
                  "遮挡后，对同一批未遮挡审计选手逐人预测，使用各自实际CSP-S分数与原获奖门槛；不假装知道真实线下人群。", ""]
    sensitivity = ["模型与缺失敏感性（不是95%置信区间）", "π是人为设定的边界低分缺失比例，不是未匹配率或全国未获奖率。", ""]
    for k in (6, 7):
        level = report.levels[k]
        title = f"{k}级 | CSP-S前{fmt_pct(level.q_s)}"
        summary += [title, f"主显示：{METHODS[level.selected_method]}"]
        if not level.available:
            summary += ["无法标定：" + level.reason, ""]
            continue
        summary += [f"CSP-S线：{fmt_score(level.csp_score)}分；严格高于/包含同分：{fmt_pct(level.csp_strict)} / {fmt_pct(level.csp_inclusive)}",
                    f"锚点门槛核验：{'已覆盖' if level.anchor_verified else '未完整覆盖，近似锚点'}",
                    f"局部窗口：±{level.half_width_pp:g}个百分点；{level.local_pairs}对；有效样本量{level.effective_n:.1f}；{level.schools}所学校、{level.provinces}省",
                    "可见获奖者局部线性中位数：" + describe_tail(level.baseline),
                    "截断校正候选：" + describe_tail(level.corrected),
                    "校正分布：" + FAMILY_LABELS.get(level.model_family, "无可用模型"),
                    f"模型估计的共同门槛以下质量π：{fmt_pct(level.estimated_missing_mass)}（依赖分布假设）",
                    "采用判断：" + "；".join(level.adoption_reasons),
                    "可见基线95%近似重抽区间：" + describe_interval(level.bootstrap.get("baseline")),
                    "校正模型95%近似重抽区间：" + describe_interval(level.bootstrap.get("corrected")),
                    "以上重抽固定所选分布/带宽；模型选择及缺失假设差异另看敏感性，未被区间消除。",
                    "可见个体成绩25%/50%/75%分位：" + " / ".join(fmt_score(v) for v in level.visible_iqr) + "分（个体离散，不是置信区间）"]
        if level.selected:
            summary += [f"主显示门槛的同分计数：严格高于{level.selected.known_gt}人，包含同分{level.selected.known_ge}人；{level.selected.status}"]
        summary += ["提示：" + s for s in level.warnings] + [""]
        validation += [title, level.validation.get("reason", "未验证"),
                       f"独立审计：{level.validation.get('audit_n', 0)}个边界样本 / {level.validation.get('audit_schools', 0)}所学校"]
        for row in level.candidates:
            validation.append(f"{FAMILY_LABELS[row['family']]} ±{row['half_width_pp']:g}pp：n={row['n']} ESS={row['effective_n']:.1f}；"
                              f"三折对数损失={fmt_score(row['cv_log_loss'])}；候选线={fmt_score(row['score'])}；比例={fmt_pct(row.get('q'))}"
                              + (" [选择]" if row['selected'] else "")
                              + (" [参数边界/拟合失败]" if row['boundary_hit'] or not row['converged'] else ""))
        for trial in level.validation.get("trials", []):
            validation.append(f"额外遮挡目标{fmt_pct(trial['hidden_target_fraction'])}，人工保留线{fmt_score(trial['artificial_line'])}分，训练保留{trial['train_retained']}人："
                              f"朴素逐人预测MAE {fmt_score(trial['naive_abs_error'])}分 → 校正 {fmt_score(trial['corrected_abs_error'])}分")
            validation.append(f"  描述性局部位置：参考{fmt_score(trial['reference_score'])}；朴素预测{fmt_score(trial['naive_score'])}；"
                              f"校正预测{fmt_score(trial['recovered_score'])}分；这些截距不用于采用判定。")
        if "naive_mae" in level.validation:
            validation += [f"平均逐人预测MAE：朴素{fmt_score(level.validation['naive_mae'])}分，校正{fmt_score(level.validation['corrected_mae'])}分；"
                           f"改善{fmt_pct(level.validation['improvement'])}。三个深度共用审计集，不是三个独立实验。"]
        validation += [""]
        sensitivity += [title]
        r = level.sensitivity.get("model_range")
        sensitivity += [(f"同目标候选比例范围：{fmt_pct(r[0])}～{fmt_pct(r[1])}（非置信区间）" if r else "同目标模型范围：不足以计算或含未解决候选，不认证稳定")]
        for row in level.sensitivity.get("unresolved_comparable_models", []):
            sensitivity.append(f"未解决的可比候选：{FAMILY_LABELS[row['family']]} ±{row['half_width_pp']:g}pp，未从稳健性检查中删除。")
        for row in level.sensitivity.get("bandwidth_baselines", []):
            sensitivity.append(f"可见基线 ±{row['half_width_pp']:g}pp：{row['n']}人，{fmt_score(row['median_score'])}分，{fmt_pct(row['q'])}")
        if "fuzzy_baseline_score_shift" in level.sensitivity:
            sensitivity += [f"加入{level.sensitivity['fuzzy_extra_pairs']}对模糊候选：基线分数变化{fmt_score(level.sensitivity['fuzzy_baseline_score_shift'])}；"
                            f"校正变化{fmt_score(level.sensitivity.get('fuzzy_corrected_score_shift'))}分（不进入主结果）。"]
        sensitivity += [f"假设情景，共同门槛={fmt_score(level.common_floor)}分（包含门槛分数为可见）：",
                        level.sensitivity.get("scenario_note", "门槛不完整，未构造共同门槛情景")]
        for row in level.scenarios:
            sensitivity.append(f"假设π={fmt_pct(row['assumed_missing_mass'])}：{fmt_score(row['score'])}分 → {fmt_pct(row['q'])}；{row['status']}")
        for row in level.sensitivity.get("leave_one_out", []):
            sensitivity.append(f"去掉{row['kind']} {row['label']}：候选分数变化{fmt_score(row['score_shift'])}分，比例变化{fmt_pct(row['q_shift'])}")
        sensitivity += [""]
    ds, match = report.data_summary, report.match
    data = ["数据与门槛核验", f"CSP-S总人数{ds['csp_capacity']:,}，获奖记录{ds['csp_awards']:,}；NOIP总人数{ds['noip_capacity']:,}，获奖记录{ds['noip_awards']:,}",
            f"严格匹配{match['strict']:,}对，额外模糊候选{match['fuzzy_extra']}对，歧义记录{match['ambiguous_records']}条；NOIP获奖者严格匹配率{fmt_pct(match['noip_award_match_rate'])}",
            f"CSP-S未匹配获奖记录{match['csp_unmatched_award_records']}；NOIP未匹配获奖记录{match['noip_unmatched_award_records']}。未匹配不等于参赛未获奖。",
            f"全国可核对计数线：CSP-S {fmt_score(ds['csp_counting_floor'])}分，NOIP {fmt_score(ds['noip_counting_floor'])}分。",
            "匹配质量、门槛覆盖、估计稳定性分别报告，不再用算法差异打A/B/C总分。", ""]
    for row in report.province_diagnostics:
        data.append(f"{row['province']}：CSP获奖{row['csp_awards']} / NOIP获奖{row['noip_awards']} / 严格匹配{row['strict_matches']} / 匹配率{fmt_pct(row['award_match_rate'])}")
        for key, name in (("csp_rule", "CSP-S"), ("noip_rule", "NOIP")):
            rule = row[key]
            if rule:
                data.append(f"  {name}：{rule['status']}；计数线{fmt_score(rule['counting_floor'])}；观测门槛{fmt_score(rule['observation_floor'])}；"
                            f"实际最低获奖分{fmt_score(rule['observed_minimum'])}（不能冒充官方线）；{rule['reason']}")
    method = ["方法与边界", "1. 全国累计比例定位CSP-S同分块；主样本始终为严格同人配对。",
              "2. 以等级边界为中心尝试±1/2/3/5个百分点窗口；用非负斜率局部中位数线建立可见基线。",
              "3. 原始NOIP分数按各省官方获奖门槛进入条件截断似然；不因全国最低分稀疏而额外删去低分配对。",
              "4. 比较有界正态与厚尾t(5)，三折学校分组验证选模型；独立学校人工遮挡检查恢复原可见队列的能力。",
              "5. 仅当遮挡后同一审计集的逐人中位数预测MAE改善≥10%且≥0.5分、至少2/3深度改善、有效样本≥100、学校≥10、两分布稳健且候选比例跨度≤5pp、门槛计数完整时，才允许模型条件推荐。",
              "6. 窗口及模型选择不包含在固定模型重抽区间里，另列同目标模型敏感性；缺失π场景不是实测概率或置信区间。",
              "7. 省份/年级只作覆盖与影响诊断；不拟合无法可靠标准化到总体的省份人数权重，不加入未经验证的省份效应。",
              "8. 人工遮挡能检验已知尾部的恢复能力，不能证明真实门槛以下的分布假设；正式参赛者在边界处的省份构成仍未知。",
              "9. 各年独立标定，不硬编码2022为低质量，不混合各年原始分数；特殊推荐类别未获奖身份缺失仍可能造成选择偏差。", "",
              "设置：" + json.dumps(report.settings, ensure_ascii=False), "", "来源："] + report.sources + ["", "风险："] + report.warnings
    summary += ["总体提示："] + report.warnings
    return {"结论": "\n".join(summary), "模型与验证": "\n".join(validation),
            "敏感性": "\n".join(sensitivity), "数据与门槛": "\n".join(data), "方法与限制": "\n".join(method)}


def report_to_text(report, include_provinces=True):
    sections = report.sections or report_sections(report)
    return "\n\n".join(f"【{name}】\n{text}" for name, text in sections.items()
                         if include_provinces or name != "数据与门槛")


def report_to_json(report):
    return json.dumps(asdict(report), ensure_ascii=False, indent=2, allow_nan=False)


def main():
    parser = argparse.ArgumentParser(description="CSP-S边界局部中位数标定、获奖截断校正和独立遮挡验证")
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--year", type=int, help="默认最近可配对年份")
    parser.add_argument("--q-s-6", default="20", help="6级比例：15或15%%为15%%，0.15亦为15%%")
    parser.add_argument("--q-s-7", default="10", help="7级比例：7.5或7.5%%为7.5%%，1为1%%")
    parser.add_argument("--bootstrap", type=int, default=1000, help="省内按学校整组重抽；0跳过区间")
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--match-mode", choices=("strict", "fuzzy"), default="strict", help="主样本始终严格匹配；fuzzy附加模糊匹配敏感性")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--output", type=Path, help="保存完整报告（UTF-8）；拒绝覆盖已有文件")
    args = parser.parse_args()
    try:
        if args.output is not None and args.output.exists():
            raise ValueError("输出文件已存在，请换一个名称，避免覆盖。")
        year = args.year if args.year is not None else default_year(load_contests(args.data_dir))
        if year is None:
            raise ValueError("没有可配对年份。")
        report = analyze_year(args.data_dir, year, {6: parse_percentage(args.q_s_6), 7: parse_percentage(args.q_s_7)},
                              args.bootstrap, args.seed, args.match_mode,
                              lambda message: print(message, file=sys.stderr))
        text = report_to_json(report) if args.json else report_to_text(report)
        if args.output is not None:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x", encoding="utf-8") as handle:
                handle.write(text + "\n")
            print(f"完整报告已保存：{args.output}")
        else:
            print(text)
        return 0
    except (OSError, ValueError, RuntimeError, ImportError) as exc:
        print(f"计算失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
