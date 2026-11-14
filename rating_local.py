"""Numerics for local median calibration. No filesystem or GUI operations.

Only the conditional distribution among participants is modelled. Truncation
bounds are observation rules, not zero scores for absent/unmatched people.
Validation restores the *already observed* reference cohort, not the unknown
population below its original award threshold.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Callable, Optional

import numpy as np
from scipy import optimize, special

FAMILIES = ("normal", "t5")
BANDWIDTHS = (0.01, 0.02, 0.03, 0.05)
MIN_FIT_N = 40
MIN_ESS = 30


class AnalysisCancelled(Exception):
    pass


def check_cancel(cancel: Optional[Callable[[], bool]]) -> None:
    if cancel and cancel():
        raise AnalysisCancelled("计算已取消。")


def weighted_quantile(values, weights, probability=0.5):
    values, weights = np.asarray(values, float), np.asarray(weights, float)
    keep = np.isfinite(values) & np.isfinite(weights) & (weights > 0)
    if not np.any(keep):
        raise ValueError("没有有效加权样本。")
    values, weights = values[keep], weights[keep]
    order = np.argsort(values, kind="stable")
    values, weights = values[order], weights[order]
    positions = (np.cumsum(weights) - weights / 2) / np.sum(weights)
    return np.interp(probability, positions, values, left=values[0], right=values[-1])


def weighted_median(values, weights):
    """An actual minimizer of weighted absolute loss (not interpolated ranks)."""
    values, weights = np.asarray(values, float), np.asarray(weights, float)
    keep = np.isfinite(values) & np.isfinite(weights) & (weights > 0)
    values, weights = values[keep], weights[keep]
    if len(values) == 0:
        raise ValueError("没有有效加权样本。")
    order = np.argsort(values, kind="stable")
    values, weights = values[order], weights[order]
    cumulative = np.cumsum(weights)
    half = cumulative[-1] / 2
    index = int(np.searchsorted(cumulative, half, side="left"))
    if index + 1 < len(values) and abs(cumulative[index] - half) < 1e-12 * cumulative[-1]:
        return float((values[index] + values[index + 1]) / 2)
    return float(values[index])


def effective_n(weights) -> float:
    weights = np.asarray(weights, float)
    denominator = float(np.sum(weights ** 2))
    return float(np.sum(weights) ** 2 / denominator) if denominator > 0 else 0.0


def kernel_weights(percentiles, target: float, bandwidth: float):
    distance = np.abs(np.asarray(percentiles, float) - target) / bandwidth
    return np.maximum(0.0, 1.0 - np.minimum(distance, 1.0) ** 3) ** 3


@dataclass
class LocalSample:
    x: np.ndarray
    y: np.ndarray
    p: np.ndarray
    lower: np.ndarray
    school: np.ndarray
    province: np.ndarray
    grade: np.ndarray

    def subset(self, mask) -> "LocalSample":
        return LocalSample(*(getattr(self, field)[mask] for field in self.__dataclass_fields__))

    def __len__(self):
        return len(self.y)


@dataclass
class MedianLine:
    intercept: float
    slope: float
    center: float
    x_scale: float

    def predict(self, x):
        return self.intercept + self.slope * (np.asarray(x) - self.center) / self.x_scale


def median_line(x, y, weights, center: float, x_scale: float) -> MedianLine:
    """Weighted LAD with a nonnegative slope, profiled over the intercept.

    At each slope the weighted median is an exact minimizer in the intercept.
    The scalar convex objective also checks the zero-slope endpoint explicitly.
    """
    x, y, weights = np.asarray(x), np.asarray(y), np.asarray(weights)
    keep = weights > 0
    z, y, weights = (x[keep] - center) / x_scale, y[keep], weights[keep]
    if len(y) == 0:
        raise ValueError("没有局部样本。")

    def objective(slope):
        residual = y - slope * z
        location = weighted_median(residual, weights)
        return float(np.dot(weights, np.abs(residual - location)) / weights.sum())

    upper = max(100.0, float(np.ptp(y)) * 2)
    if np.ptp(z) < 1e-9:
        slope = 0.0
    else:
        result = optimize.minimize_scalar(objective, bounds=(0, upper), method="bounded",
                                          options={"xatol": 1e-5})
        slope = min((0.0, float(result.x), upper), key=objective)
    intercept = weighted_median(y - slope * z, weights)
    return MedianLine(intercept, slope, center, x_scale)


def _logcdf(family, z):
    if family == "normal":
        return special.log_ndtr(z)
    with np.errstate(divide="ignore"):
        return np.log(special.stdtr(5, z))


def _logmass(family, low, high):
    """Stable log(P(low < Z < high)), including normal tails beyond 38σ."""
    low, high = np.broadcast_arrays(low, high)
    mirrored = low >= 0
    log_big = _logcdf(family, np.where(mirrored, -low, high))
    log_small = _logcdf(family, np.where(mirrored, -high, low))
    with np.errstate(divide="ignore", invalid="ignore"):
        value = log_big + np.log(-np.expm1(np.minimum(log_small - log_big, 0)))
    return np.where(high <= low, -np.inf, value)


def _inverse_logcdf(family, logp):
    if family == "normal":
        return special.ndtri_exp(logp)
    return special.stdtrit(5, np.exp(logp))


@dataclass
class TruncatedFit:
    family: str
    intercept: float
    slope: float
    sigma: float
    center: float
    x_scale: float
    maximum: float
    loss: float
    converged: bool
    boundary_hit: bool

    def location(self, x):
        return self.intercept + self.slope * (np.asarray(x) - self.center) / self.x_scale

    def quantile(self, probability=0.5, x=None, lower=0.0):
        """Quantile on [lower, maximum], inverted in the log-CDF/SF domain."""
        if not 0 <= probability <= 1:
            raise ValueError("分位数概率不在[0,1]内。")
        mu = self.location(self.center if x is None else x)
        low = (np.asarray(lower) - mu) / self.sigma
        high = (self.maximum - mu) / self.sigma
        mirrored = low > 0
        # F(z)=(1-p)F(lo)+pF(hi); in a positive tail use the survival
        # analogue and ndtri_exp, without flooring tiny probabilities.
        a = _logcdf(self.family, np.where(mirrored, -low, low))
        b = _logcdf(self.family, np.where(mirrored, -high, high))
        with np.errstate(divide="ignore"):
            log_probability = np.logaddexp(np.log1p(-probability) + a, np.log(probability) + b)
        z = _inverse_logcdf(self.family, log_probability)
        z = np.where(mirrored, -z, z)
        return np.clip(mu + self.sigma * z, lower, self.maximum)

    def cdf(self, score, x=None, lower=0.0):
        mu = self.location(self.center if x is None else x)
        lo = (np.asarray(lower) - mu) / self.sigma
        hi = (self.maximum - mu) / self.sigma
        yy = (np.clip(score, lower, self.maximum) - mu) / self.sigma
        value = np.exp(_logmass(self.family, lo, yy) - _logmass(self.family, lo, hi))
        return np.clip(value, 0, 1)

    def log_prob(self, x, y, lower):
        """Score bins of width one; bounds include the observed threshold bin.

        [0, maximum] is the continuous score approximation's natural support.
        A score exactly on an award line is not silently dropped.
        """
        mu = self.location(x)
        low_y = np.maximum(np.maximum(0.0, np.asarray(y) - 0.5), np.maximum(0.0, np.asarray(lower) - 0.5))
        high_y = np.minimum(self.maximum, np.asarray(y) + 0.5)
        low_obs = np.maximum(0.0, np.asarray(lower) - 0.5)
        numerator = _logmass(self.family, (low_y - mu) / self.sigma, (high_y - mu) / self.sigma)
        denominator = _logmass(self.family, (low_obs - mu) / self.sigma, (self.maximum - mu) / self.sigma)
        return numerator - denominator


def fit_truncated(x, y, lower, weights, center, x_scale, maximum,
                  family="normal", start: Optional[TruncatedFit] = None) -> Optional[TruncatedFit]:
    if family not in FAMILIES:
        raise ValueError("未知条件分布。")
    x, y, lower, weights = (np.asarray(v, float) for v in (x, y, lower, weights))
    keep = (weights > 0) & np.isfinite(lower) & (y >= lower) & np.isfinite(x) & np.isfinite(y)
    x, y, lower, weights = (v[keep] for v in (x, y, lower, weights))
    if len(y) < MIN_FIT_N or effective_n(weights) < MIN_ESS:
        return None
    if not (np.min(x) <= center <= np.max(x)) or np.ptp(x) < 1e-9:
        return None
    weights = weights / weights.sum()
    bounds = [(-maximum, maximum), (0.0, 2 * maximum), (math.log(1.0), math.log(maximum))]
    visible_median = float(weighted_quantile(y, weights))
    spread = max(5.0, float(np.sqrt(np.dot(weights, (y - visible_median) ** 2))))
    if start is not None and start.family == family:
        initial = [start.intercept, start.slope, math.log(start.sigma)]
        starts = [initial]
    else:
        initial = [visible_median - 0.25 * spread, max(0.0, spread / 3), math.log(spread)]
        starts = [initial, [visible_median - spread, 0.0, math.log(spread * 1.5)]]

    def make(parameters, loss=math.inf, converged=False):
        mu, slope, logsigma = parameters
        hit = (mu <= -maximum + 0.05 or mu >= maximum - 0.05 or
               slope >= 2 * maximum - 0.05 or logsigma <= bounds[2][0] + 1e-3 or
               logsigma >= bounds[2][1] - 1e-3)
        return TruncatedFit(family, float(mu), float(slope), float(np.exp(logsigma)),
                            float(center), float(x_scale), float(maximum), float(loss), converged, bool(hit))

    def loss(parameters):
        model = make(parameters)
        return float(-np.dot(weights, model.log_prob(x, y, lower)))

    candidates = []
    for initial in starts:
        result = optimize.minimize(loss, initial, method="L-BFGS-B", bounds=bounds,
                                   options={"maxiter": 180, "ftol": 1e-10})
        if result.success and np.isfinite(result.fun):
            candidates.append(make(result.x, result.fun, True))
    return min(candidates, key=lambda fit: fit.loss) if candidates else None


def _group_folds(schools, seed, folds=5):
    names = np.unique(schools)
    rng = np.random.default_rng(seed)
    rng.shuffle(names)
    assignment = {name: i % folds for i, name in enumerate(names)}
    return np.array([assignment[name] for name in schools])


def conditional_prediction_mae(fit, x, y, original_lowers, weights):
    """Score conditional medians at EACH held-out pupil's actual X and floor.

    Both predictors in the masking audit face these same outcomes, weights and
    observation rules. Do not compare a centre-X mixture median with an LAD
    intercept evaluated on a different covariate distribution.
    """
    weights = np.asarray(weights, float)
    predictions = fit.quantile(x=x, lower=np.maximum(0, np.asarray(original_lowers) - 0.5))
    error = float(np.dot(weights, np.abs(np.asarray(y) - predictions)) / weights.sum())
    return error, predictions


def validate_local(sample: LocalSample, center_score, center_p, maximum, seed,
                   cancel=None, progress=None):
    """Select with inner school-group CV; gate with untouched outer schools.

    All candidates use the same validation band. School fold 0 is held out
    from *every* hyperparameter choice. Three masking trials share that audit
    set and are not described as three independent experiments.
    """
    school_fold = _group_folds(sample.school, seed, 5)
    outer = school_fold == 0
    inner = ~outer
    x_scale = max(1.0, float(np.std(sample.x[inner]))) if np.any(inner) else 1.0
    common_eval = kernel_weights(sample.p, center_p, 0.01)
    inner_fold = _group_folds(sample.school[inner], seed + 1, 3)
    folds = np.full(len(sample), -1)
    folds[inner] = inner_fold
    candidates = []
    full_fits = {}
    for bandwidth in BANDWIDTHS:
        weights = kernel_weights(sample.p, center_p, bandwidth)
        for family in FAMILIES:
            check_cancel(cancel)
            if progress:
                progress(f"分组验证：{family}，边界窗口 ±{bandwidth * 100:g} 个百分点")
            numerator = denominator = 0.0
            valid_folds = 0
            for fold in range(3):
                train = inner & (folds != fold) & (weights > 0)
                test = inner & (folds == fold) & (common_eval > 0)
                if np.count_nonzero(test) < 10:
                    continue
                model = fit_truncated(sample.x[train], sample.y[train], sample.lower[train],
                                      weights[train], center_score, x_scale, maximum, family)
                if model is None or model.boundary_hit:
                    continue
                # No unsupported X extrapolation in the validation score.
                inside = test & (sample.x >= np.min(sample.x[train])) & (sample.x <= np.max(sample.x[train]))
                if np.count_nonzero(inside) != np.count_nonzero(test):
                    continue
                logp = model.log_prob(sample.x[test], sample.y[test], sample.lower[test])
                numerator += float(-np.dot(common_eval[test], logp))
                denominator += float(common_eval[test].sum())
                valid_folds += 1
            full = fit_truncated(sample.x, sample.y, sample.lower, weights, center_score, x_scale, maximum, family)
            key = (family, bandwidth)
            full_fits[key] = full
            cv_loss = numerator / denominator if valid_folds == 3 and denominator > 0 else None
            candidates.append({
                "family": family, "half_width_pp": bandwidth * 100,
                "n": int(np.count_nonzero(weights)), "effective_n": effective_n(weights),
                "cv_log_loss": cv_loss, "valid_folds": valid_folds,
                "converged": bool(full and full.converged),
                "boundary_hit": bool(full and full.boundary_hit),
                "score": float(full.quantile()) if full else None,
                "sigma": full.sigma if full else None,
            })
    # Full-data fits are for the final refit/sensitivity only. Filtering the
    # hyperparameter choice by their convergence would leak audit outcomes.
    eligible = [row for row in candidates if row["cv_log_loss"] is not None]
    if not eligible:
        return None, candidates, {"passed": False, "reason": "没有模型完成全部学校分组验证。", "trials": []}, full_fits
    selected = min(eligible, key=lambda row: (row["cv_log_loss"], row["half_width_pp"], row["family"]))
    bandwidth = selected["half_width_pp"] / 100
    weights = kernel_weights(sample.p, center_p, bandwidth)
    family = selected["family"]
    train = inner & (weights > 0)
    audit = outer & (common_eval > 0)
    audit_n = int(np.count_nonzero(audit))
    audit_schools = len(np.unique(sample.school[audit]))
    outcome = {"passed": False, "reason": "", "trials": [], "audit_n": audit_n,
               "audit_schools": audit_schools, "train_schools": len(np.unique(sample.school[inner])),
               "split": "学校五组中的一组独立审计；其余学校内三折选模型", "selected_family": family,
               "metric": "同一未遮挡审计集上、按实际CSP-S分数和原门槛计算逐人中位数预测MAE",
               "selected_half_width_pp": bandwidth * 100}
    if audit_n < 30 or audit_schools < 5:
        outcome["reason"] = "独立审计集边界样本/学校不足。"
        return selected, candidates, outcome, full_fits
    reference_line = median_line(sample.x[audit], sample.y[audit], common_eval[audit], center_score, x_scale)
    reference = reference_line.intercept
    train_sample = sample.subset(train)
    train_weights = weights[train]
    for depth in (0.10, 0.20, 0.30):
        check_cancel(cancel)
        # Use an integer score boundary consistent with the width-one score
        # bins in the likelihood (not half a bin of unobserved probability).
        threshold = float(math.floor(weighted_quantile(train_sample.y, train_weights, depth)) + 1)
        new_lower = np.maximum(train_sample.lower, threshold)
        keep = train_sample.y >= new_lower
        retained = train_sample.subset(keep)
        local_weights = train_weights[keep]
        if len(retained) < MIN_FIT_N or not (np.min(retained.x) <= center_score <= np.max(retained.x)):
            continue
        model = fit_truncated(retained.x, retained.y, new_lower[keep], local_weights,
                              center_score, x_scale, maximum, family)
        if not model or model.boundary_hit:
            continue
        naive_line = median_line(retained.x, retained.y, local_weights, center_score, x_scale)
        corrected_error, predictions = conditional_prediction_mae(
            model, sample.x[audit], sample.y[audit], sample.lower[audit], common_eval[audit])
        naive_error = float(np.dot(common_eval[audit], np.abs(sample.y[audit] - naive_line.predict(sample.x[audit]))) / common_eval[audit].sum())
        # The three intercepts are descriptive ONLY; the adoption criterion uses
        # pupil-level losses on identical held-out X, Y and original thresholds.
        recovered_line = median_line(sample.x[audit], predictions, common_eval[audit], center_score, x_scale)
        outcome["trials"].append({"hidden_target_fraction": depth, "artificial_line": threshold,
                                  "train_retained": len(retained), "reference_score": reference,
                                  "naive_score": naive_line.intercept, "recovered_score": recovered_line.intercept,
                                  "position_label": "局部位置仅作描述，采用判断不比较这些截距",
                                  "naive_abs_error": naive_error,
                                  "corrected_abs_error": corrected_error})
    trials = outcome["trials"]
    if len(trials) < 3:
        outcome["reason"] = "部分人工遮挡试验拟合失败，不能通过采用门槛。"
    else:
        naive_error = float(np.mean([t["naive_abs_error"] for t in trials]))
        corrected_error = float(np.mean([t["corrected_abs_error"] for t in trials]))
        improved = sum(t["corrected_abs_error"] < t["naive_abs_error"] for t in trials)
        gain = naive_error - corrected_error
        relative = gain / max(naive_error, 1e-9)
        outcome.update(naive_mae=naive_error, corrected_mae=corrected_error,
                       improvement=relative, improved_trials=improved)
        # Predeclared operational adoption rule, NOT an official quality grade.
        outcome["passed"] = gain >= 0.5 and relative >= 0.10 and improved >= 2
        outcome["reason"] = ("通过：逐人中位数预测MAE至少改善10%且0.5分，三个遮挡深度至少两个改善。"
                             if outcome["passed"] else "遮挡后的逐人中位数预测未达到预设改善标准；不采用校正为主结果。")
    return selected, candidates, outcome, full_fits


def cluster_multiplicities(sample: LocalSample, rng):
    """Sample schools within fixed province strata; never Bernoulli-drop matches."""
    multipliers = np.zeros(len(sample), float)
    for province in np.unique(sample.province):
        idx = np.flatnonzero(sample.province == province)
        schools, reverse = np.unique(sample.school[idx], return_inverse=True)
        counts = rng.multinomial(len(schools), np.full(len(schools), 1 / len(schools)))
        multipliers[idx] = counts[reverse]
    return multipliers


def bootstrap_design(sample, weights):
    weights = np.asarray(weights, float)
    active = weights > 0
    fixed_provinces = []
    fixed_weight = 0.0
    resampleable = 0
    for province in np.unique(sample.province[active]):
        mask = active & (sample.province == province)
        schools = len(np.unique(sample.school[mask]))
        if schools < 2:
            fixed_provinces.append(str(province))
            fixed_weight += float(weights[mask].sum())
        else:
            resampleable += 1
    return {"estimable": resampleable > 0,
            "resampleable_provinces": resampleable,
            "fixed_single_school_provinces": fixed_provinces,
            "fixed_weight_fraction": min(1.0, max(0.0, fixed_weight / float(weights.sum()))) if weights.sum() else 1.0,
            "interpretation": "省内仅1校的分层无法提供组间重抽方差；不能用更多重复次数制造信息"}


def bootstrap_local(sample, center_score, center_p, bandwidth, model, reps, seed,
                    maximum, cancel=None, progress=None):
    """Conditional-on-selected-model intervals; tuning uncertainty is separate."""
    rng = np.random.default_rng(seed)
    weights = kernel_weights(sample.p, center_p, bandwidth)
    active = weights > 0
    sample, weights = sample.subset(active), weights[active]
    output = {"baseline": [], "corrected": [], "design": bootstrap_design(sample, weights)}
    if not output["design"]["estimable"] or reps == 0:
        return output
    x_scale = model.x_scale if model else max(1.0, float(np.std(sample.x)))
    for iteration in range(reps):
        check_cancel(cancel)
        ww = weights * cluster_multiplicities(sample, rng)
        if np.count_nonzero(ww) < 15 or effective_n(ww) < 10:
            continue
        xs = sample.x[ww > 0]
        if not (xs.min() <= center_score <= xs.max()):
            continue
        baseline = median_line(sample.x, sample.y, ww, center_score, x_scale)
        if math.isfinite(baseline.intercept) and 0 <= baseline.intercept <= maximum:
            output["baseline"].append(float(baseline.intercept))
        if model:
            fitted = fit_truncated(sample.x, sample.y, sample.lower, ww, center_score,
                                   x_scale, maximum, model.family, start=model)
            if fitted and not fitted.boundary_hit:
                output["corrected"].append(float(fitted.quantile()))
        if progress and ((iteration + 1) % max(1, reps // 20) == 0 or iteration == 0):
            progress(f"学校整组重抽 {iteration + 1}/{reps}")
    return output
