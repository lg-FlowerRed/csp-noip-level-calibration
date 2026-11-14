"""Shared, auditable record loading and conservative same-year linkage."""
from __future__ import annotations

import csv
import json
import math
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

DATA_DIR = Path(__file__).resolve().parent / "data"
AWARDS = ("一等奖", "二等奖", "三等奖")
LEVEL_DEFAULTS = {6: 0.20, 7: 0.10}


@dataclass(frozen=True)
class AwardRecord:
    contest: str
    award: str
    name: str
    grade: str
    school: str
    score: float
    province: str
    gender: str
    note: str
    canonical_school: str
    normalized_name: str
    normalized_grade: str


@dataclass
class MatchedPair:
    csp: AwardRecord
    noip: AwardRecord
    method: str
    similarity: float = 1.0  # string similarity only; never a calibrated probability


@dataclass(frozen=True)
class TieBand:
    score: float
    strict: float
    inclusive: float
    midpoint: float


def _norm_text(value):
    value = unicodedata.normalize("NFKC", value or "").strip().lower()
    return re.sub(r"[\s\-—_·•,，.。()（）【】\[\]{}]+", "", value)


def normalize_name(value):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value or "").strip()).lower()


def normalize_province(value):
    text = unicodedata.normalize("NFKC", value).strip()
    for long, short in (("内蒙古自治区", "内蒙古"), ("广西壮族自治区", "广西"),
                        ("宁夏回族自治区", "宁夏"), ("新疆维吾尔自治区", "新疆"),
                        ("西藏自治区", "西藏"), ("香港特别行政区", "香港"), ("澳门特别行政区", "澳门")):
        if text == long:
            return short
    return re.sub(r"[省市]$", "", text)


def normalize_grade(value):
    text = unicodedata.normalize("NFKC", value or "").strip()
    aliases = {"高中一年级": "高一", "十年级": "高一", "10": "高一", "4": "高一",
               "高中二年级": "高二", "十一年级": "高二", "11": "高二", "5": "高二",
               "高中三年级": "高三", "十二年级": "高三", "12": "高三", "6": "高三",
               "初三": "九年级", "9": "九年级", "初二": "八年级", "8": "八年级",
               "初一": "七年级", "7": "七年级"}
    # Legacy 4/5/6 follow the supplied grades.json special masks, not primary grades.
    return aliases.get(text, text)


def load_contests(data_dir=DATA_DIR):
    with (Path(data_dir) / "contests.json").open(encoding="utf-8-sig") as handle:
        return {item["name"]: item for item in json.load(handle)}


def capacity_of(contest: Optional[dict]):
    if not contest or contest.get("capacity") is None:
        return None
    value = contest["capacity"]
    if isinstance(value, bool) or not math.isfinite(float(value)) or float(value) != int(value) or int(value) <= 0:
        raise ValueError("capacity 必须为正整数。")
    return int(value)


def available_years(contests):
    return sorted({int(c["year"]) for c in contests.values()
                   if c.get("type") == "CSP提高"
                   and f"NOIP{int(c['year'])}" in contests
                   and capacity_of(c) and capacity_of(contests[f"NOIP{int(c['year'])}"])})


def default_year(contests):
    years = available_years(contests)
    return max(years) if years else None


def load_school_aliases(data_dir=DATA_DIR):
    candidates = defaultdict(set)
    with (Path(data_dir) / "school.txt").open(encoding="utf-8-sig") as handle:
        for raw in handle:
            if not raw.strip() or raw.lstrip().startswith("#"):
                continue
            row = next(csv.reader([raw]))
            if len(row) < 3:
                continue
            province, canonical = normalize_province(row[0]), _norm_text(row[2])
            for alias in row[2:]:
                if _norm_text(alias):
                    candidates[(province, _norm_text(alias))].add(canonical)
    # Ambiguous aliases are not arbitrarily assigned to the first school.
    return {key: next(iter(values)) for key, values in candidates.items() if len(values) == 1}


def canonicalize_school(school, province, aliases):
    return _norm_text(aliases.get((normalize_province(province), _norm_text(school)), school))


def load_award_records(data_dir, contest_names, aliases=None, diagnostics=None):
    result = {name: [] for name in contest_names}
    aliases = aliases if aliases is not None else load_school_aliases(data_dir)
    seen = set()
    with (Path(data_dir) / "raw.txt").open(encoding="utf-8-sig") as handle:
        for line_number, raw in enumerate(handle, 1):
            if not raw.strip() or raw.lstrip().startswith("#"):
                continue
            # Avoid parsing hundreds of thousands of irrelevant historical records.
            if raw.split(",", 1)[0].strip() not in result:
                continue
            row = next(csv.reader([raw]))
            if len(row) != 9:
                raise ValueError(f"raw.txt 第 {line_number} 行字段数不是9。")
            contest, award, name, grade, school, score, province, gender, note = (s.strip() for s in row)
            value = float(score)
            if not math.isfinite(value) or value < 0 or award not in AWARDS:
                raise ValueError(f"raw.txt 第 {line_number} 行分数或奖项无效。")
            province = normalize_province(province)
            record = AwardRecord(contest, award, name, grade, school, value, province, gender, note,
                                 canonicalize_school(school, province, aliases), normalize_name(name), normalize_grade(grade))
            if record in seen:
                # Deduplicate exact repeated records without rewriting the source.
                # Different scores under the same identity remain an audit conflict.
                if diagnostics is not None:
                    diagnostics[contest] = diagnostics.get(contest, 0) + 1
                continue
            seen.add(record)
            result[contest].append(record)
    return result


def _exact_key(record):
    return (record.normalized_name, record.province, record.canonical_school, record.normalized_grade)


def _candidate_key(record):
    return (record.normalized_name, record.province, record.normalized_grade)


def _gender_compatible(a, b):
    return not a.gender or not b.gender or a.gender == b.gender


def match_records(csp_records, noip_records, mode="strict", fuzzy_threshold=0.84, fuzzy_margin=0.08):
    if mode not in ("strict", "fuzzy"):
        raise ValueError("匹配模式只能是 strict 或 fuzzy。")
    left, right = defaultdict(list), defaultdict(list)
    for i, record in enumerate(csp_records):
        left[_exact_key(record)].append(i)
    for i, record in enumerate(noip_records):
        right[_exact_key(record)].append(i)
    pairs, used_csp, used_noip = [], set(), set()
    blocked_csp, blocked_noip = set(), set()
    for key in sorted(left.keys() & right.keys()):
        c, n = left[key], right[key]
        # Empty identity fields never form an automatic high-confidence match.
        if all(key) and len(c) == len(n) == 1 and _gender_compatible(csp_records[c[0]], noip_records[n[0]]):
            pairs.append(MatchedPair(csp_records[c[0]], noip_records[n[0]], "exact"))
            used_csp.add(c[0]); used_noip.add(n[0])
        else:
            blocked_csp.update(c); blocked_noip.update(n)
    ambiguous_csp, ambiguous_noip = set(blocked_csp), set(blocked_noip)
    if mode == "fuzzy":
        cg, ng = defaultdict(list), defaultdict(list)
        for i, record in enumerate(csp_records):
            if i not in used_csp | blocked_csp:
                cg[_candidate_key(record)].append(i)
        for i, record in enumerate(noip_records):
            if i not in used_noip | blocked_noip:
                ng[_candidate_key(record)].append(i)
        for key in sorted(cg.keys() & ng.keys()):
            if not all(key):
                continue
            scores = {(ci, ni): SequenceMatcher(None, csp_records[ci].canonical_school,
                                                 noip_records[ni].canonical_school).ratio()
                      for ci in cg[key] for ni in ng[key]
                      if _gender_compatible(csp_records[ci], noip_records[ni])
                      and csp_records[ci].canonical_school and noip_records[ni].canonical_school}
            for (ci, ni), score in sorted(scores.items()):
                ca = [s for (c, n), s in scores.items() if c == ci and n != ni]
                na = [s for (c, n), s in scores.items() if n == ni and c != ci]
                if (score >= fuzzy_threshold and score - max(ca, default=0) >= fuzzy_margin
                        and score - max(na, default=0) >= fuzzy_margin):
                    pairs.append(MatchedPair(csp_records[ci], noip_records[ni], "fuzzy", score))
                    used_csp.add(ci); used_noip.add(ni)
            ambiguous_csp.update(ci for ci, _ in scores if ci not in used_csp)
            ambiguous_noip.update(ni for _, ni in scores if ni not in used_noip)
    return pairs, len(ambiguous_csp) + len(ambiguous_noip), used_csp, used_noip


def score_percentile_map(records, capacity):
    counts = Counter(r.score for r in records)
    result, above = {}, 0
    for score in sorted(counts, reverse=True):
        equal = counts[score]
        strict, inclusive = above / capacity, (above + equal) / capacity
        result[score] = TieBand(score, strict, inclusive, (strict + inclusive) / 2)
        above += equal
    return result


def score_band_for_top_fraction(records, capacity, q):
    if not (0 < q < 1) or not records or q > len(records) / capacity + 1e-12:
        return None
    for band in score_percentile_map(records, capacity).values():
        if band.inclusive + 1e-12 >= q:
            return band
    return None
