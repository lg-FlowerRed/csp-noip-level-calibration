#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CSP-S → NOIP 6/7 级比例测算（基于 data/ 获奖数据）

数据说明
--------
data/contests.json
    赛事元数据列表。关键字段：
      name        赛事名称，如 "CSP2025提高"、"NOIP2025"
      type        赛事类型，如 "CSP提高"、"NOIP"
      year        年份
      capacity    该赛事总参赛人数（CSP-S 为提高组第二轮人数；
                  NOIP 为实际参赛高中生人数）
data/raw.txt
    获奖名单，逗号分隔，字段：
      赛事名称, 奖项, 姓名, 年级, 学校, 分数, 省份, 性别, 备注/类别
    以 # 开头的行为注释。
data/scoring.json
    各赛事类型的积分权重（本计算不使用）。
data/school.txt / grades.json / surnames.json / name_exceptions.json
    学校别名、年级归一化、姓名首拼等辅助数据（本计算不使用）。

方法
----
设：
  q_S      CSP-S 6/7 级百分比（如 0.20、0.10）
  D        NOIP 相对 CSP-S 的难度比（1.2 表示难 1.2 倍）
  N_CSP    CSP-S 提高组第二轮总人数（contests.json 的 capacity）
  N_NOIP   NOIP 总人数（contests.json 的 capacity）
  s        N_NOIP / N_CSP

两种难度比口径：
  通过率比：q_S_eq = q_S / D
  几率比：  q_S_eq = q_S / (q_S + D * (1 - q_S))

纯截断近似（数据只有总人数和获奖名单，没有全体成绩分布）：
  q_N = min(1, q_S_eq / s)

解释：把 NOIP 看作 CSP-S 中按成绩选出的前 s 比例；NOIP 等级线在
CSP-S 参照系中的等价百分位为 q_S_eq，NOIP 池内达标比例即 q_S_eq / s。

用法
----
  python calc_rating_percentage.py
  python calc_rating_percentage.py --year 2025 --q-s-6 15 --q-s-7 7.5 --d 1.2 --measure both
  python calc_rating_percentage.py --describe
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Dict, Iterable, Optional

AWARDS = ("一等奖", "二等奖", "三等奖")
LEVEL_DEFAULTS = {6: 0.20, 7: 0.10}
DATA_DIR = Path(__file__).resolve().parent / "data"


# ---------------------------------------------------------------------------
# 数据读取
# ---------------------------------------------------------------------------
def load_contests(data_dir: Path) -> Dict[str, dict]:
    """读取 contests.json，返回 {赛事名称: 赛事元数据}。"""
    path = data_dir / "contests.json"
    if not path.exists():
        raise FileNotFoundError(f"找不到 {path}，请确认 data 文件夹位置。")
    with path.open(encoding="utf-8") as f:
        items = json.load(f)
    return {item["name"]: item for item in items}


def load_award_counts(data_dir: Path, names: Iterable[str]) -> Dict[str, Dict[str, int]]:
    """从 raw.txt 统计指定赛事的各奖项人数。"""
    names = set(names)
    counts = {name: {award: 0 for award in AWARDS} for name in names}
    path = data_dir / "raw.txt"
    if not path.exists():
        return counts
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                parts = next(csv.reader([line]))
            except csv.Error:
                continue
            if len(parts) < 2:
                continue
            contest, award = parts[0].strip(), parts[1].strip()
            if contest in counts and award in counts[contest]:
                counts[contest][award] += 1
    return counts


def capacity_of(contest: Optional[dict]) -> Optional[int]:
    """取赛事总人数 capacity；缺失返回 None。"""
    if not contest:
        return None
    value = contest.get("capacity")
    return int(value) if value is not None else None


def available_years(contests: Dict[str, dict]) -> list[int]:
    """列出有 CSP-S 提高组数据的年份。"""
    years = {
        item["year"]
        for item in contests.values()
        if item.get("type") == "CSP提高"
    }
    return sorted(years)


def default_year(contests: Dict[str, dict]) -> Optional[int]:
    """默认年份：最近一个同时有 CSP-S 和 NOIP 数据的年份。"""
    years = [
        y
        for y in available_years(contests)
        if f"CSP{y}提高" in contests and f"NOIP{y}" in contests
    ]
    return max(years) if years else None


# ---------------------------------------------------------------------------
# 输入与格式化
# ---------------------------------------------------------------------------
def ask(prompt: str, default=None, cast=str, validate=None):
    """交互式输入；空输入使用 default。"""
    while True:
        raw = input(prompt).strip()
        if not raw and default is not None:
            return default
        try:
            value = cast(raw)
        except ValueError:
            print("  输入格式有误，请重试。")
            continue
        if validate is not None and not validate(value):
            print("  输入超出范围，请重试。")
            continue
        return value


def parse_percentage(value: float) -> float:
    """20 或 0.2 都表示 20%。"""
    return value / 100.0 if value > 1 else value


def fmt_pct(x: float) -> str:
    return f"{x * 100:.2f}%"


def fmt_int(n: Optional[int]) -> str:
    return f"{n:,}" if n is not None else "—"


# ---------------------------------------------------------------------------
# 计算
# ---------------------------------------------------------------------------
def qs_eq_pass(qS: float, D: float) -> float:
    """通过率比口径：q_S_eq = q_S / D；超过 100% 按 100% 处理。"""
    return min(1.0, qS / D)


def qs_eq_odds(qS: float, D: float) -> float:
    """几率比口径：q_S_eq = q_S / (q_S + D * (1 - q_S))。"""
    return qS / (qS + D * (1.0 - qS))


def qn_from_qseq(qS_eq: float, s: float) -> float:
    """纯截断近似：q_N = min(1, q_S_eq / s)。"""
    return min(1.0, qS_eq / s)


def compute(qS: float, D: float, s: float, measure: str):
    """返回 {口径: (q_S_eq, q_N)}。"""
    results = {}
    if measure in ("pass", "both"):
        qeq = qs_eq_pass(qS, D)
        results["pass"] = (qeq, qn_from_qseq(qeq, s))
    if measure in ("odds", "both"):
        qeq = qs_eq_odds(qS, D)
        results["odds"] = (qeq, qn_from_qseq(qeq, s))
    return results


# ---------------------------------------------------------------------------
# 输出
# ---------------------------------------------------------------------------
def describe_data() -> None:
    print(
        """
数据文件说明
============
contests.json
  赛事元数据列表，字段：
    name        赛事名称，如 CSP2025提高、NOIP2025
    type        赛事类型，如 CSP提高、NOIP
    year        年份
    full_score  满分
    fall_semester 是否秋季学期
    capacity    该赛事总参赛人数（CSP-S 为提高组第二轮人数；
                NOIP 为实际参赛高中生人数）

raw.txt
  获奖名单，逗号分隔：
    赛事名称, 奖项, 姓名, 年级, 学校, 分数, 省份, 性别, 备注/类别
  以 # 开头为注释。

scoring.json
  各赛事类型的积分权重（本计算不使用）。

school.txt
  学校别名表：省, 市, 正式校名, 别名1, 别名2, ...

grades.json
  年级归一化映射（小学/初中/高中等）。

surnames.json / name_exceptions.json
  姓名首拼与多音字处理辅助数据。
"""
    )


def print_data_check(
    year: int,
    csp: dict,
    noip: dict,
    csp_counts: Dict[str, int],
    noip_counts: Dict[str, int],
    qs_by_level: Dict[int, float],
) -> None:
    csp_cap = capacity_of(csp)
    noip_cap = capacity_of(noip)
    print(f"\n--- 数据检查（{year}）---")
    print(f"CSP-S 提高组总人数（capacity）: {fmt_int(csp_cap)}")
    print(f"NOIP 总人数（capacity）: {fmt_int(noip_cap)}")
    if csp_cap and noip_cap:
        print(
            f"选拔率 s = N_NOIP / N_CSP = "
            f"{fmt_int(noip_cap)} / {fmt_int(csp_cap)} = {fmt_pct(noip_cap / csp_cap)}"
        )

    def show_counts(label: str, counts: Dict[str, int], cap: Optional[int]) -> None:
        pieces = [f"{a} {fmt_int(counts[a])}" for a in AWARDS]
        print(f"{label}获奖人数: " + "；".join(pieces))
        if cap:
            rates = [f"{a} {fmt_pct(counts[a] / cap)}" for a in AWARDS]
            print(f"{label}获奖率: " + "；".join(rates))

    show_counts("CSP-S ", csp_counts, csp_cap)
    show_counts("NOIP  ", noip_counts, noip_cap)

    if csp_cap and csp_counts["一等奖"]:
        actual_first = csp_counts["一等奖"] / csp_cap
        level_rates = "，".join(
            f"{level} 级 q_S={fmt_pct(qs)}"
            for level, qs in sorted(qs_by_level.items())
        )
        print(
            f"注：CSP-S 一等奖实际比例 {fmt_pct(actual_first)}；"
            f"你输入的是 {level_rates}（等级百分比不必然等于一等奖率）。"
        )


def print_results(
    qs_by_level: Dict[int, float], D: float, s: float, measure: str
) -> None:
    print("\n--- 计算结果（同时计算 6 级与 7 级）---")
    print(f"D = {D:.4g}（NOIP 难度 / CSP-S 难度）")
    print(f"s = {fmt_pct(s)}（NOIP 总人数 / CSP-S 总人数）")

    for level, qS in sorted(qs_by_level.items()):
        results = compute(qS, D, s, measure)
        print(f"\n[{level} 级] CSP-S q_S = {fmt_pct(qS)}")

        if "pass" in results:
            qeq, qn = results["pass"]
            print("  通过率比口径")
            print(f"    q_S_eq = q_S / D = {fmt_pct(qeq)}")
            print(f"    q_N = min(1, q_S_eq / s) = {fmt_pct(qn)}")
            if qn >= 1.0:
                print("    注意：q_N 达到 100%，该等级在 NOIP 池内人人达标，已失去区分度。")

        if "odds" in results:
            qeq, qn = results["odds"]
            print("  几率比口径")
            print(f"    q_S_eq = q_S / (q_S + D * (1 - q_S)) = {fmt_pct(qeq)}")
            print(f"    q_N = min(1, q_S_eq / s) = {fmt_pct(qn)}")
            if qn >= 1.0:
                print("    注意：q_N 达到 100%，该等级在 NOIP 池内人人达标，已失去区分度。")

        print("  同百分比（q_N = q_S）下的难度比")
        print(f"    通过率口径 D0 = 1 / s = {1.0 / s:.4g}")
        if qS < 1.0:
            d0_odds = (1.0 / s - qS) / (1.0 - qS)
            print(f"    几率口径 D0 = (1/s - q_S) / (1 - q_S) = {d0_odds:.4g}")


def print_sensitivity(
    qs_by_level: Dict[int, float], s: float, measure: str, d_input: float
) -> None:
    ds = sorted({1.0, 1.1, 1.2, 1.3, 1.5, 2.0, float(d_input)})
    print("\n--- 敏感性：不同 D 下的 q_N ---")
    for level, qS in sorted(qs_by_level.items()):
        print(f"\n[{level} 级，CSP-S q_S={fmt_pct(qS)}]")
        header = "  D      "
        if measure in ("pass", "both"):
            header += "通过率口径   "
        if measure in ("odds", "both"):
            header += "几率口径"
        print(header)
        for d in ds:
            row = f"  {d:<6.2f}"
            if measure in ("pass", "both"):
                qn = qn_from_qseq(qs_eq_pass(qS, d), s)
                row += f" {fmt_pct(qn):>10}"
            if measure in ("odds", "both"):
                qn = qn_from_qseq(qs_eq_odds(qS, d), s)
                row += f" {fmt_pct(qn):>10}"
            print(row)


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(
        description="按 CSP-S 6/7 级百分比与难度比同时测算 NOIP 两级比例",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DATA_DIR,
        help=f"data 文件夹路径（默认：{DATA_DIR}）",
    )
    parser.add_argument("--year", type=int, help="年份，如 2025")
    parser.add_argument(
        "--q-s-6",
        type=float,
        help="CSP-S 6 级百分比（默认 20；15 或 0.15 都表示 15%%）",
    )
    parser.add_argument(
        "--q-s-7",
        type=float,
        help="CSP-S 7 级百分比（默认 10；7.5 或 0.075 都表示 7.5%%）",
    )
    # 兼容旧命令：--level N --q-s X 仅覆盖对应级别，仍同时输出两级。
    parser.add_argument("--level", choices=["6", "7"], help=argparse.SUPPRESS)
    parser.add_argument("--q-s", type=float, help=argparse.SUPPRESS)
    parser.add_argument("--d", type=float, help="难度比 D，如 1.2")
    parser.add_argument(
        "--measure",
        choices=["pass", "odds", "both"],
        help="难度比口径：pass=通过率比，odds=几率比，both=两者",
    )
    parser.add_argument(
        "--describe",
        action="store_true",
        help="只打印 data 文件夹的格式说明",
    )
    args = parser.parse_args()

    if args.describe:
        describe_data()
        return 0

    try:
        contests = load_contests(args.data_dir)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"读取数据失败：{exc}", file=sys.stderr)
        return 1

    years = available_years(contests)
    if not years:
        print("contests.json 中没有 CSP提高 类型的数据。", file=sys.stderr)
        return 1

    # 年份
    if args.year is not None:
        year = args.year
    else:
        default = default_year(contests)
        print("=== CSP-S → NOIP 6/7 级比例测算 ===")
        print(f"数据目录: {args.data_dir}")
        print(f"可用年份: {', '.join(map(str, years))}")
        print(f"默认年份: {default}（最近一个同时有 CSP-S 与 NOIP 数据的年份）")
        year = ask(
            f"请输入年份 [{default}]: ",
            default=default,
            cast=int,
            validate=lambda y: y in years,
        )

    csp_name = f"CSP{year}提高"
    noip_name = f"NOIP{year}"
    csp = contests.get(csp_name)
    noip = contests.get(noip_name)

    if not csp:
        print(f"{year} 年没有 {csp_name} 数据。可用年份: {', '.join(map(str, years))}")
        return 1

    if not noip:
        print(
            f"\n{year} 年没有 NOIP 数据"
            "（2019 年 NOIP 停办；2026 年 NOIP 尚未举行），无法计算 q_N。"
        )
        print(f"CSP-S 提高组总人数: {fmt_int(capacity_of(csp))}")
        return 0

    csp_cap = capacity_of(csp)
    noip_cap = capacity_of(noip)
    if not csp_cap or not noip_cap:
        print(
            f"{year} 年 contests.json 缺少 capacity："
            f"{csp_name}={csp_cap}, {noip_name}={noip_cap}",
            file=sys.stderr,
        )
        return 1

    # 6/7 级 CSP-S 百分比：始终同时计算，分别支持自定义。
    qs_by_level = dict(LEVEL_DEFAULTS)
    provided = {6: args.q_s_6, 7: args.q_s_7}
    for level, raw_qs in provided.items():
        if raw_qs is not None:
            qs_by_level[level] = parse_percentage(raw_qs)

    # 兼容旧参数：--level 6 --q-s 15 等价于 --q-s-6 15。
    if args.q_s is not None:
        if args.level is None:
            print("旧参数 --q-s 必须与 --level 6 或 --level 7 一起使用。", file=sys.stderr)
            return 1
        qs_by_level[int(args.level)] = parse_percentage(args.q_s)

    if (
        all(value is None for value in provided.values())
        and args.q_s is None
        and args.level is None
    ):
        print("\nCSP-S 等级百分比（直接回车使用默认值，可输入小数）：")
        for level, default_qs in LEVEL_DEFAULTS.items():
            raw_qs = ask(
                f"请输入 {level} 级百分比 [{default_qs * 100:g}]: ",
                default=default_qs * 100,
                cast=float,
                validate=lambda x: 0 < x < 100,
            )
            qs_by_level[level] = parse_percentage(raw_qs)

    for level, qS in qs_by_level.items():
        if not (0 < qS < 1):
            print(f"{level} 级 q_S 必须在 (0, 100%) 内。", file=sys.stderr)
            return 1

    # 难度比 D
    if args.d is not None:
        D = args.d
    else:
        D = ask(
            "请输入难度比 D（NOIP 相对 CSP-S，1.2 表示难 1.2 倍）[1.2]: ",
            default=1.2,
            cast=float,
            validate=lambda x: x > 0,
        )
    if D <= 0:
        print("D 必须大于 0。", file=sys.stderr)
        return 1

    # 口径
    if args.measure is not None:
        measure = args.measure
    else:
        print("\n难度比口径：1=通过率比  2=几率比  3=两者都算")
        choice = input("请选择 [3]: ").strip() or "3"
        while choice not in ("1", "2", "3"):
            choice = input("请输入 1、2 或 3: ").strip()
        measure = {"1": "pass", "2": "odds", "3": "both"}[choice]

    # 获奖数据
    award_counts = load_award_counts(args.data_dir, [csp_name, noip_name])
    csp_counts = award_counts.get(csp_name, {a: 0 for a in AWARDS})
    noip_counts = award_counts.get(noip_name, {a: 0 for a in AWARDS})

    print_data_check(year, csp, noip, csp_counts, noip_counts, qs_by_level)
    s = noip_cap / csp_cap
    print_results(qs_by_level, D, s, measure)
    print_sensitivity(qs_by_level, s, measure, D)

    print(
        "\n说明：以上为纯截断近似——把 NOIP 看作 CSP-S 中按成绩选出的前 s 比例。"
        "\n若实际选拔不是硬截断（例如按省名额、推荐名额），结果会有一定偏差；"
        "\n如需更精确的结果，需要 CSP-S/NOIP 全体成绩分布与考生链接数据。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
