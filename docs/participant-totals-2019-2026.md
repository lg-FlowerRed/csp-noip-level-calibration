# CSP-S / NOIP 参赛总人数（2019–2026）

> 数据截至 2026-11-14。总人数以 `data/contests.json` 的 `capacity` 为准；该数值已与“获奖人数 ÷ 获奖比例”交叉校验。配套明细见 [CSV](participant-totals-2019-2026.csv)；当前程序见根目录 `calc_rating_matched.py`，旧纯截断程序在 `legacy/`。

## 一、总表

| 年份 | CSP-S 提高组第二轮总人数 | NOIP 总人数 | 备注 |
|---:|---:|---:|---|
| 2019 | 13,903 | — | NOIP 2019 停办；CSP-J/S 首次举办 |
| 2020 | 11,048 | 4,693 | NOIP 2020 恢复，不分组 |
| 2021 | 11,601 | 5,261 | |
| 2022 | 9,216 | 4,372 | 此前按 20% 估算的 6,165 已废弃 |
| 2023 | 19,202 | 6,670 | |
| 2024 | 27,521 | 7,510 | |
| 2025 | 30,497 | 7,548 | |
| 2026 | 32,643 | — | NOIP 2026 于 2026-11-28 举行，尚无数据 |

## 二、CSP-S 提高组第二轮明细

| 年份 | 一等奖人数 | 一等奖比例 | 总人数（capacity） | 来源 |
|---:|---:|---:|---:|---|
| 2019 | 2,859 | 20.56% | 13,903 | data/contests.json；[规则转载](https://www.sohu.com/a/359625054_821349) |
| 2020 | 2,393 | 21.66% | 11,048 | data/contests.json；[规则转载](https://www.cnblogs.com/buaaliang/p/14071076.html) |
| 2021 | 2,354 | 20.29% | 11,601 | data/contests.json；[NOI 官网](https://www.noi.cn/xw/2021-11-05/749734.shtml) |
| 2022 | 1,964 | 21.31% | 9,216 | data/contests.json；[NOI 官网](https://www.noi.cn/xw/2022-11-17/777448.shtml) |
| 2023 | 3,898 | 20.30% | 19,202 | data/contests.json；[NOI 官网](https://www.noi.cn/xw/2023-11-15/798182.shtml) |
| 2024 | 5,507 | 20.01% | 27,521 | data/contests.json；[NOI 官网](https://www.noi.cn/xw/2024-11-19/834421.shtml) |
| 2025 | 6,194 | 20.31% | 30,497 | data/contests.json；[NOI 官网](https://www.noi.cn/xw/2025-11-14/853110.shtml) |
| 2026 | 6,607 | 20.24% | 32,643 | data/contests.json；[NOI 官网](https://www.noi.cn/xw/2026-11-13/947969.shtml) |

> 口径：CSP-S（提高组）第二轮实际参加人数。capacity 与“一等奖人数 ÷ 一等奖比例”的差异在 0.1% 以内（四舍五入）。

## 三、NOIP 明细

| 年份 | 一等奖人数 | 一等奖比例 | 二等奖人数 | 二等奖比例 | 三等奖人数 | 三等奖比例 | 总人数（capacity） | 来源 |
|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 2020 | 1,130 | 24.08% | 1,174 | 25.02% | 676 | 14.40% | 4,693 | data/contests.json；[NOI 官网](https://www.noi.cn/hjmd/mdgs/2020/2020-12-15/718388.shtml) |
| 2021 | 1,441 | 27.39% | — | — | — | — | 5,261 | data/contests.json；[NOI 官网](https://www.noi.cn/hjmd/mdgs/2021/2021-12-03/750910.shtml) |
| 2022 | 1,233 | 28.20% | 1,107 | 25.32% | 185 | 4.23% | 4,372 | data/contests.json；[NOI 官网](https://www.noi.cn/hjmd/mdgs/2022/2022-12-13/781313.shtml) |
| 2023 | 1,785 | 26.76% | 2,180 | 32.68% | 727 | 10.90% | 6,670 | data/contests.json；[NOI 官网](https://www.noi.cn/hjmd/mdgs/2023/2023-12-12/810464.shtml) |
| 2024 | 1,517 | 20.20% | 1,712 | 22.80% | 1,883 | 25.07% | 7,510 | data/contests.json；[NOI 官网](https://www.noi.cn/hjmd/mdgs/2024/2024-12-17/836103.shtml) |
| 2025 | 1,545 | 20.47% | 1,761 | 23.33% | 1,768 | 23.42% | 7,548 | data/contests.json；[NOI 官网](https://www.noi.cn/hjmd/mdgs/2025/2025-12-13/854072.shtml) |

> 口径：NOIP 实际参加竞赛的高中选手人数。2021 年二、三等奖人数未在本次统计中提取，故留空。

## 四、计算与校验说明

1. **总人数来源**：`data/contests.json` 的 `capacity` 字段。该字段与“一等奖人数 ÷ 一等奖比例”反推结果一致（差异来自四舍五入），因此本表直接采用 capacity，避免二次舍入误差。
2. **2022 年 NOIP**：capacity 为 4,372；一等奖 1,233 人，一等奖率 28.20%，与 2021 年（27.39%）、2023 年（26.76%）的高一等奖率一致。此前按“20% 计划比例”估算的 6,165 已废弃。
3. **2020/2021/2023 年 NOIP 一等奖率偏高**（24.08%/27.39%/26.76%），是当年名额分配方案（含历年获奖、新获奖名额）造成的，不代表总获奖率。
4. **CSP-S 2022 一等奖率 21.31%** 高于常规 20%，是当年省际调整后的实际比例。
5. **“参赛总人数”与“获奖人数”不同**：本表是实际参赛人数，不是获奖人数，也不是名额数。
6. **未包含**：CSP-J（入门组）、NOI、NOIP 2019（停办）、NOIP 2026（未举行）。

## 五、来源

- [data/contests.json（本数据集的赛事总人数）](data/contests.json)
- [CSP-J/S2019 第二轮评级规则（搜狐转载）](https://www.sohu.com/a/359625054_821349)
- [CSP-J/S2020 第二轮评级规则（博客园转载）](https://www.cnblogs.com/buaaliang/p/14071076.html)
- [CCF CSP-J/S 2021 第二轮评级规则（NOI 官网）](https://www.noi.cn/xw/2021-11-05/749734.shtml)
- [CCF CSP-JS 2022 第二轮评级规则（NOI 官网）](https://www.noi.cn/xw/2022-11-17/777448.shtml)
- [CSP-J/S 2023 第二轮评级规则（NOI 官网）](https://www.noi.cn/xw/2023-11-15/798182.shtml)
- [CSP-J/S2024 第二轮评级规则（NOI 官网）](https://www.noi.cn/xw/2024-11-19/834421.shtml)
- [CCF CSP-J/S2025 第二轮评级规则（NOI 官网）](https://www.noi.cn/xw/2025-11-14/853110.shtml)
- [CSP-J/S 2026 第二轮评级规则（NOI 官网）](https://www.noi.cn/xw/2026-11-13/947969.shtml)
- [NOIP2020 获奖名单（NOI 官网）](https://www.noi.cn/hjmd/mdgs/2020/2020-12-15/718388.shtml)
- [NOIP 2021 获奖名单（NOI 官网）](https://www.noi.cn/hjmd/mdgs/2021/2021-12-03/750910.shtml)
- [NOIP 2022 获奖名单（NOI 官网）](https://www.noi.cn/hjmd/mdgs/2022/2022-12-13/781313.shtml)
- [NOIP 2023 获奖名单（NOI 官网）](https://www.noi.cn/hjmd/mdgs/2023/2023-12-12/810464.shtml)
- [NOIP2024 获奖名单公示（NOI 官网）](https://www.noi.cn/hjmd/mdgs/2024/2024-12-17/836103.shtml)
- [NOIP2025 获奖名单公示（NOI 官网）](https://www.noi.cn/hjmd/mdgs/2025/2025-12-13/854072.shtml)
- [NOIP2025 评奖规则与获奖分数线（NOI 官网）](https://www.noi.cn/xw/2025-12-13/854070.shtml)
