# NOIP 6/7 级比例测算方法

> **当前程序说明（v3.0-local）**：现行 CLI/GUI 已改为边界局部中位数、官方获奖门槛截断校正和独立学校遮挡验证，不再使用人工难度比 D 或全局平均百分位等张回归。下文 v1.0 章节保留为历史理论背景；现行算法以 [局部标定改进方案](method-v3-local-calibration.md) 和 [安装与使用说明](install-windows.md) 为准。


## 以 CSP-S 为共同参照的难度对齐（含通过率比与几率比两种口径）

| 项目 | 内容 |
|---|---|
| 版本 | v1.0 |
| 日期 | 2026-11-14 |
| 适用对象 | CCF 中学生计算机程序设计能力等级评价 6 级、7 级 |
| 输入 | CSP-S 6/7 级百分比 $q_S$、NOIP 相对 CSP-S 的难度比 $D$、年份 $t$ |
| 输出 | NOIP 6/7 级百分比 $q_N$ |
| 数据基础 | 年份 $t$ 的 CSP-S 成绩分布、NOIP 参赛池及其 CSP-S 成绩（链接数据） |

> **一句话版本：** 先把 NOIP 的等级线翻译成“相当于 CSP-S 前百分之几”，再数 NOIP 里有多少人在这条线以上；这个人数占比，就是与 CSP-S 难度持平的 NOIP 百分比。

> **公式阅读说明：** 本文使用 LaTeX 公式（`$...$` 与 `$$...$$`）。建议用支持 MathJax/KaTeX 的 Markdown 阅读器（如 Typora、Obsidian、VS Code）打开；若渲染器不支持，公式仍以源码形式可读。

---

## 摘要

本文给出一个可复现的计算框架，用于回答：**给定 CSP-S 的 6/7 级百分比 $q_S$、NOIP 相对 CSP-S 的难度比 $D$ 和数据年份 $t$，NOIP 的 6/7 级百分比 $q_N$ 应该定为多少，才能使两项赛事的等级难度基本持平？**

核心思想是把 CSP-S 当作共同参照系。NOIP 考生本身是 CSP-S 考生中按成绩和名额筛选出来的子集，因此不能把两边的“前 20%”直接当成同一把尺子。本文先把 NOIP 的等级线映射到 CSP-S 的百分位，再回到 NOIP 池内计算达标比例。

难度比保留两种衡量方式：

- **通过率比（pass-rate ratio）**：$D_{\text{pass}} = q_S / q_S^{\text{eq}}$，直观、便于对外解释；
- **几率比（odds ratio）**：$D_{\text{odds}} = \operatorname{odds}(q_S) / \operatorname{odds}(q_S^{\text{eq}})$，在对数几率尺度上线性、统计性质更稳。

两种口径都归结为同一个主公式：

$$
q_N = 1 - F_{N,t}\!\left(Q_{S,t}\!\left(1 - g(q_S, D)\right)\right),
$$

其中 $g(q_S,D)$ 在通过率口径下为 $q_S/D$，在几率口径下为 $q_S/[q_S + D(1-q_S)]$。$F_{S,t}$、$F_{N,t}$ 分别是年份 $t$ 的 CSP-S 成绩分布和 NOIP 池的 CSP-S 成绩分布，$Q_{S,t}$ 是 $F_{S,t}$ 的分位数函数。

文档分为三部分：第一部分用池塘比喻和算术例子讲清思路；第二部分给出严格定义、估计方法、不确定性量化和模型校验；第三部分给出数据表结构、伪代码和实施清单。

---

## 阅读指南

| 读者 | 建议阅读 | 预计时间 |
|---|---|---|
| 只想快速理解结论 | 第一部分 1.1–1.6 | 10 分钟 |
| 需要向他人解释方法 | 第一部分全部 + 第二部分 2.3–2.4 | 30 分钟 |
| 统计学专业人士 | 第二部分全部 | 60 分钟 |
| 负责落地计算 | 第三部分 + 附录 A/B | 60 分钟 |

---

# 第一部分 通俗解释（小白也能看懂）

## 1.1 要解决的问题

CCF 的 6 级、7 级评级标准写的是“全国前 20%”“全国前 10%”。但这句话放在 CSP-S 和 NOIP 里，难度并不一样：NOIP 的选手是从 CSP-S 里挑出来的高中生，整体更强。于是同样写“前 20%”，NOIP 的 20% 实际上比 CSP-S 的 20% 难得多。

现在反过来问：**如果希望 NOIP 的 6/7 级难度和 CSP-S 基本持平，NOIP 的百分比应该放宽到多少？**

## 1.2 两个池塘：为什么同样 20% 难度不同

把 CSP-S 想成一个大池塘：所有符合年龄条件的中学生都能进来，水平参差不齐。把 NOIP 想成一个小池塘：只从大池塘里按成绩捞走一部分高中生，而且捞走的都是相对靠前的。

同样说“前 20%”：

- 大池塘的前 20%，是“所有参赛者里排前 20%”；
- 小池塘的前 20%，是“已经被筛过一遍的人里再排前 20%”。

小池塘里的鱼平均更强，所以小池塘的前 20% 更难拿到。这就是“同样百分比、难度不同”的根本原因。

## 1.3 “难度比 1.2 倍”到底是什么意思

“在 NOIP 拿 6 级比在 CSP-S 难 1.2 倍”，不能理解成“NOIP 前 20% 等于 CSP-S 前 16.7%”。正确的理解是：

> 把 NOIP 的 6 级线放到 CSP-S 的尺子上，它相当于 CSP-S 的前 16.7%（20% ÷ 1.2）。

也就是说，NOIP 的等级线比 CSP-S 的等级线更靠前。线越靠前，越难达到。

这里用到的“尺子”是 CSP-S 的全国百分位。NOIP 考生每个人都有一个 CSP-S 成绩，因此可以问：**NOIP 的这条等级线，相当于 CSP-S 的百分之几？** 这个百分位就是两种口径共同的桥梁。

## 1.4 两种算法：通过率比与几率比

设：

- $q_S$：CSP-S 的 6/7 级百分比（例如 20% 或 10%）；
- $q_S^{\text{eq}}$：NOIP 等级线在 CSP-S 尺子上对应的百分位；
- $D$：NOIP 相对 CSP-S 的难度比（$D=1.2$ 表示难 1.2 倍）。

### 算法一：通过率比

$$
D_{\text{pass}} = \frac{q_S}{q_S^{\text{eq}}}
\quad\Longrightarrow\quad
q_S^{\text{eq}} = \frac{q_S}{D_{\text{pass}}}.
$$

直观理解：难度是 1.2 倍，就把 CSP-S 的百分位除以 1.2。

例：$q_S=20\%$，$D_{\text{pass}}=1.2$，则 $q_S^{\text{eq}}=20\%/1.2=16.67\%$。

### 算法二：几率比

“几率”是“达标人数 ÷ 未达标人数”。例如 20% 的几率是 $20/80=0.25$。

$$
D_{\text{odds}}
= \frac{\operatorname{odds}(q_S)}{\operatorname{odds}(q_S^{\text{eq}})}
\quad\Longrightarrow\quad
q_S^{\text{eq}}
= \frac{q_S}{q_S + D_{\text{odds}}(1-q_S)}.
$$

例：$q_S=20\%$，$D_{\text{odds}}=1.2$，则

$$
q_S^{\text{eq}}
= \frac{0.20}{0.20 + 1.2\times 0.80}
= 17.24\%.
$$

### 两种算法怎么选

| 口径 | 优点 | 缺点 | 适用场景 |
|---|---|---|---|
| 通过率比 | 直观，一句话能解释 | 在 0%/100% 附近不稳定；$D<q_S$ 时会出现 $q_N>100\%$ | 对外沟通、政策说明 |
| 几率比 | 对数几率尺度线性；无上界问题；适合回归 | 不如“除以 1.2”直观 | 统计建模、多年数据、置信区间 |

同一数值的 $D$ 在两种口径下含义略有不同：$q_S=20\%$、$D=1.2$ 时，通过率口径给出 16.67%，几率口径给出 17.24%。$D=1$ 时两者完全一致。建议**主报一种、附报另一种**，并在报告中注明口径。

## 1.5 三步算出 NOIP 百分比

有了 $q_S^{\text{eq}}$，剩下的事情很直接：

**第一步：算 $q_S^{\text{eq}}$。** 用 1.4 的公式，从 $q_S$ 和 $D$ 算出 NOIP 等级线在 CSP-S 尺子上的百分位。

**第二步：找分数线。** 在年份 $t$ 的 CSP-S 成绩表里，找到第 $(1-q_S^{\text{eq}})$ 百分位的分数 $c$。例如 $q_S^{\text{eq}}=16.67\%$，就找 CSP-S 成绩从高到低排第 16.67% 的那条线。

**第三步：数 NOIP 里的人。** 在年份 $t$ 的 NOIP 考生里，数 CSP-S 成绩不低于 $c$ 的人，占比就是 $q_N$：

$$
q_N = P_{N,t}(X \ge c) = 1 - F_{N,t}(c).
$$

其中 $F_{N,t}$ 是“NOIP 考生的 CSP-S 成绩分布”。

如果 NOIP 是从 CSP-S 前 $s$ 比例里按成绩选的，并且假设“在这一段里均匀挑选”，还可以用一个更简单的近似：

$$
q_N \approx \frac{q_S^{\text{eq}}}{s}.
$$

例：$s=23\%$（NOIP 约 7,500 人，对应 CSP-S 高中生池约 32,600 人），$q_S=20\%$，$D_{\text{pass}}=1.2$：

$$
q_S^{\text{eq}} = 16.67\%
\quad\Longrightarrow\quad
q_N \approx \frac{16.67\%}{23\%} = 72.5\%.
$$

也就是说，如果目标是“NOIP 只比 CSP-S 难 1.2 倍”，NOIP 的 6 级比例大约要放到 72%，而不是 20%。

## 1.6 一个完整的数字例子（2025 假设数据）

假设 2025 年：

- CSP-S 提高组高中生池约 32,600 人；
- NOIP 约 7,500 人；
- 因此 $s=7500/32600\approx 23\%$；
- 用“均匀截断”近似，$q_N\approx q_S^{\text{eq}}/s$。

### 6 级（$q_S=20\%$）

| 难度比 $D$ | 通过率口径 $q_S^{\text{eq}}$ | 通过率口径 $q_N$ | 几率口径 $q_S^{\text{eq}}$ | 几率口径 $q_N$ |
|---:|---:|---:|---:|---:|
| 1.0 | 20.00% | 86.96% | 20.00% | 86.96% |
| 1.2 | 16.67% | 72.46% | 17.24% | 74.96% |
| 1.5 | 13.33% | 57.97% | 14.29% | 62.13% |
| 2.0 | 10.00% | 43.48% | 11.11% | 48.31% |

### 7 级（$q_S=10\%$）

| 难度比 $D$ | 通过率口径 $q_S^{\text{eq}}$ | 通过率口径 $q_N$ | 几率口径 $q_S^{\text{eq}}$ | 几率口径 $q_N$ |
|---:|---:|---:|---:|---:|
| 1.0 | 10.00% | 43.48% | 10.00% | 43.48% |
| 1.2 | 8.33% | 36.23% | 8.47% | 36.83% |
| 1.5 | 6.67% | 29.00% | 6.90% | 30.00% |
| 2.0 | 5.00% | 21.74% | 5.26% | 22.87% |

> 注意：上表的 $q_N$ 是“均匀截断模型”的示例，用来说明数量级，不是真实估计。真实计算要用当年 NOIP 考生的 CSP-S 成绩分布（见第二部分）。

### 从表里能读出什么

1. **同样 20%，NOIP 确实难得多。** 在均匀截断模型下，$D=1$ 时 6 级要放到约 87%，说明当前 20% 对应的难度比约为 $1/s\approx 4.3$ 倍。这解释了“NOIP 6/7 级远难于 CSP-S”的数量级。
2. **难度比每增加一点，NOIP 比例下降得很快。** 6 级从 $D=1$ 的 87% 降到 $D=1.2$ 的 72%，再降到 $D=1.5$ 的 58%。
3. **7 级比 6 级更敏感。** 因为基数更小，同样的难度比变化会带来更大的相对降幅。

## 1.7 年份为什么重要

每年的 CSP-S 分数分布、NOIP 名额、省份构成都不一样，所以 $F_{S,t}$、$F_{N,t}$、$s_t$ 都会变。输入“2025”，就表示：

- 用 2025 年的 CSP-S 成绩分布找分数线；
- 用 2025 年的 NOIP 考生池（含他们的 CSP-S 成绩）数达标人数；
- 如果难度比 $D$ 要从数据里估计，就用 2025 年的数据估计 $D_{2025}$。

如果 $D$ 是外部给定的目标值（例如政策制定者说“希望难 1.2 倍”），年份仍然决定“尺子”和“池子”的形状，因此会改变最终的 $q_N$。

## 1.8 常见问题（FAQ）

**Q1：为什么算出来可能是 80%、90% 甚至 100%？**

因为 NOIP 已经是筛选后的强池。要让 NOIP 的等级难度和 CSP-S 持平，等级线就要放到 CSP-S 较靠前的位置，NOIP 里大部分人都会在线以上。100% 是“NOIP 入口线已经高于 CSP-S 等级线”的边界情况：按 CSP-S 百分位标准，这个等级在 NOIP 里已经人人都有，失去了区分度。这时方法给出的是数学边界，不是政策建议（见 2.10）。

**Q2：为什么不直接用 $20\%\div1.2=16.7\%$ 作为 NOIP 比例？**

因为 16.7% 只是“NOIP 等级线在 CSP-S 尺子上的位置”，不是“NOIP 池内的比例”。NOIP 是筛选池，还要除以 $s$（或用真实分布），所以 NOIP 比例会远大于 16.7%。直接除以 1.2 的公式，只有在“NOIP 池和 CSP-S 池一样强”时才成立。

**Q3：两种难度比会不会给出不同答案？**

会略有不同。同一数值 $D$ 在两种口径下含义不同；$D=1$ 时完全一致。建议在报告中同时给出两种结果，并注明主口径。

**Q4：数据不够怎么办？**

最低要求是：CSP-S 成绩分布 + NOIP 人数/名额。没有个体链接数据时，可以用截断分布模型估计 $s$ 和 $F_N$，并给出区间；只有聚合数据时，不要只报一个点估计（见 2.5.4 和 2.9）。

**Q5：这个方法适用于 2019 年以前吗？**

不适用。2019 年以前没有 CSP-S，只有 NOIP 普及组/提高组；那时 6/7 级的参照系是 NOIP 内部，不能拿 CSP-S 当尺子。本文方法适用于 2019 年 CSP-J/S 设立之后，尤其是 2020 年 NOIP 恢复、不分组之后的数据。

# 第二部分 详细科学解释（给统计学专业人士）

## 2.1 符号、目标与适用范围

### 2.1.1 符号

| 符号 | 含义 |
|---|---|
| $t$ | 数据年份（如 2025） |
| $S_t$ | 年份 $t$ 的 CSP-S 提高组第二轮参考人群 |
| $N_t$ | 年份 $t$ 的 NOIP 参赛人群，$N_t\subseteq S_t$（按成绩/名额筛选） |
| $X$ | 考生的 CSP-S 提高组第二轮成绩（连续或有序分数） |
| $F_{S,t}(x)$ | $S_t$ 中 $X\le x$ 的分布函数 |
| $F_{N,t}(x)$ | $N_t$ 中 $X\le x$ 的分布函数（即 NOIP 考生的 CSP-S 成绩分布） |
| $Q_{S,t}(u)$ | $F_{S,t}$ 的分位数函数，$Q_{S,t}(u)=F_{S,t}^{-1}(u)$ |
| $q_S$ | CSP-S 的 6/7 级百分比（如 0.20、0.10） |
| $q_N$ | NOIP 的 6/7 级百分比（待求） |
| $D$ | NOIP 相对 CSP-S 的难度比（$D>1$ 表示 NOIP 更难） |
| $q_S^{\text{eq}}$ | NOIP 等级线在 CSP-S 参照系中的等价百分位 |
| $s_t$ | NOIP 名额占 CSP-S 参考人群的比例，$s_t=N_{N,t}/N_{S,t}$ |

### 2.1.2 目标函数

$$
\boxed{
q_N = f(q_S, D, t)
= 1 - F_{N,t}\!\left(Q_{S,t}\!\left(1 - g(q_S, D)\right)\right)
}
$$

其中

$$
g_{\text{pass}}(q_S,D)=\frac{q_S}{D},
\qquad
g_{\text{odds}}(q_S,D)=\frac{q_S}{q_S + D(1-q_S)}.
$$

$g$ 把“NOIP 相对 CSP-S 的难度比”翻译成“NOIP 等级线在 CSP-S 参照系中的等价百分位” $q_S^{\text{eq}}$。$Q_{S,t}(1-q_S^{\text{eq}})$ 是这条等价线在 CSP-S 分数尺度上的位置，$F_{N,t}$ 则把它换算成 NOIP 池内的达标比例。

### 2.1.3 适用范围与关键假设

本方法适用于 2019 年 CSP-J/S 设立之后，尤其是 2020 年 NOIP 恢复、不分组之后的数据。2019 年以前没有 CSP-S，6/7 级的参照系只能是 NOIP 内部，不能用本文的 CSP-S 锚。

关键假设：

1. **参照人群一致。** $S_t$ 与 $N_t$ 的成绩来自同一年的 CSP-S 提高组第二轮，且 $q_S$ 的定义人群与 $S_t$ 一致（见 2.2）。
2. **成绩可比。** CSP-S 成绩在年份内可比；跨年比较需先做等值（2.5.3、2.6.3）。
3. **筛选机制已知或可估。** $N_t$ 是按 CSP-S 成绩/名额从 $S_t$ 中选出的；$F_{N,t}$ 可由链接数据直接估计，或用截断模型近似。
4. **等级线可定位。** CSP-S 的 $q_S$ 分位线 $Q_{S,t}(1-q_S)$ 可由成绩分布或官方分数线确定。

## 2.2 参照人群与共同标尺

### 2.2.1 为什么用 CSP-S 作为参照

NOIP 的参赛资格由 CSP-S 第二轮成绩和各省名额决定（2026 年广东细则明确要求“成功参加 CSP-S 2026 第二轮”）。因此 CSP-S 是 NOIP 的上游池，NOIP 考生天然带有 CSP-S 成绩，可以把 CSP-S 当作共同标尺。

### 2.2.2 参照人群的精确定义

若 $q_S$ 是“全体 CSP-S 考生”的百分比，而 NOIP 只从高中生中选拔，则应把参照人群限定为“符合 NOIP 报名资格的 CSP-S 考生”（在籍在校高中生），记为 $S_t^{\text{HS}}$。此时应按年级子集计算：

$$
q_S^{\text{HS}}
=P_{S,t}(X\ge c_S\mid G=\text{高中})
=\frac{\sum_{i\in S_t}\mathbf{1}\{G_i=\text{高中},\,X_i\ge c_S\}}
{\sum_{i\in S_t}\mathbf{1}\{G_i=\text{高中}\}}.
$$

若只能拿到按年级汇总的分数分布，可直接用高中生子集的分布 $F_{S,t}^{\text{HS}}$：

$$
q_S^{\text{HS}}=1-F_{S,t}^{\text{HS}}(c_S).
$$

若官方公布的 $q_S$ 已经是高中生口径，则无需调整。**报告中必须写明 $q_S$ 的定义人群**，否则结果不可比。

### 2.2.3 NOIP 池的构成

各省的 NOIP 名额分 A/B/C/D 类，选拔线 $\tau_{p,t}$ 因省而异。因此 $F_{N,t}$ 一般是省际混合分布：

$$
F_{N,t}(x)=\sum_{p=1}^{P} w_{p,t} F_{N,p,t}(x),
\qquad
w_{p,t}=\frac{N_{N,p,t}}{N_{N,t}},
$$

其中 $p$ 表示省份。全国统一的 $q_N$ 是各省 $q_{N,p}$ 的加权平均：

$$
q_N=\sum_{p=1}^{P} w_{p,t}\, q_{N,p}.
$$

若只做全国层面，可直接用合并样本估计 $F_{N,t}$；若各省名额差异大，建议分省计算后再加权（见 2.9）。

## 2.3 两种难度比的定义（共同参照池）

### 2.3.1 通过率比（pass-rate ratio）

设 NOIP 的等级线为 $c_N$。它在 CSP-S 参照系中的等价通过率为

$$
q_S^{\text{eq}}(c_N)=P_{S,t}(X\ge c_N)=1-F_{S,t}(c_N).
$$

定义通过率难度比：

$$
\boxed{D_{\text{pass}}=\frac{q_S}{q_S^{\text{eq}}(c_N)}}.
$$

解释：$D_{\text{pass}}=1.2$ 表示 NOIP 的等级线相当于 CSP-S 的 $q_S/1.2$ 通过率；$D_{\text{pass}}>1$ 表示 NOIP 线更高、更难。

反解：

$$
q_S^{\text{eq}}=\frac{q_S}{D_{\text{pass}}},
\qquad
c_N=Q_{S,t}\!\left(1-\frac{q_S}{D_{\text{pass}}}\right).
$$

约束：$q_S^{\text{eq}}\in(0,1)$，故 $D_{\text{pass}}>q_S$。若 $D_{\text{pass}}\le q_S$，则 $q_S^{\text{eq}}\ge1$，意味着 NOIP 线低到“所有人都在线上”，此时 $q_N=1$（见 2.4.4 的边界处理）。

### 2.3.2 几率比（odds ratio）

定义几率 $\operatorname{odds}(q)=q/(1-q)$。在共同参照池中：

$$
\boxed{
D_{\text{odds}}
=\frac{\operatorname{odds}(q_S)}{\operatorname{odds}(q_S^{\text{eq}})}
=\frac{q_S/(1-q_S)}{q_S^{\text{eq}}/(1-q_S^{\text{eq}})}
}.
$$

等价地，在对数几率（logit）尺度上是一个平移：

$$
\operatorname{logit}(q_S^{\text{eq}})
=\operatorname{logit}(q_S)-\ln D_{\text{odds}}.
$$

反解：

$$
\boxed{
q_S^{\text{eq}}
=\frac{q_S}{q_S + D_{\text{odds}}(1-q_S)}
},
\qquad
c_N=Q_{S,t}(1-q_S^{\text{eq}}).
$$

优点：$D_{\text{odds}}\in(0,\infty)$ 无额外约束；$\ln D_{\text{odds}}$ 可正可负，适合线性回归和层次模型；在 $q$ 接近 0 或 1 时比通过率比稳定。

### 2.3.3 两种口径的关系

由定义直接可得：

$$
D_{\text{odds}}
=\frac{q_S}{q_S^{\text{eq}}}\cdot\frac{1-q_S^{\text{eq}}}{1-q_S}
=D_{\text{pass}}\cdot\frac{1-q_S^{\text{eq}}}{1-q_S}.
$$

代入 $q_S^{\text{eq}}=q_S/D_{\text{pass}}$：

$$
\boxed{
D_{\text{odds}}=\frac{D_{\text{pass}}-q_S}{1-q_S}
},
\qquad
\boxed{
D_{\text{pass}}=q_S+D_{\text{odds}}(1-q_S)
}.
$$

这是共同参照池口径下的线性关系。几个性质：

- $D_{\text{pass}}=D_{\text{odds}}=1$ 当且仅当 $q_S^{\text{eq}}=q_S$（等级线相同）。
- 固定 $q_S$ 时，$D_{\text{odds}}$ 是 $D_{\text{pass}}$ 的线性变换，因此两者对难度的排序完全一致；同一数值（如 1.2）在两种口径下对应的 $q_S^{\text{eq}}$ 不同。
- 在 $q_S=20\%$ 时，$D_{\text{pass}}=1.2$ 对应 $D_{\text{odds}}=1.25$；$D_{\text{odds}}=1.2$ 对应 $D_{\text{pass}}=1.16$。

### 2.3.4 口径选择建议

| 目的 | 建议口径 | 理由 |
|---|---|---|
| 政策沟通、对外解释 | 通过率比 | “难度是 1.2 倍”可以直接讲成“通过率除以 1.2” |
| 统计建模、多年趋势 | 几率比 | logit 线性、无上界约束、便于加协变量 |
| 置信区间、敏感性 | 两者都报 | 互为稳健性检验 |
| 与官方百分比口径对齐 | 通过率比 | 官方标准以“前 x%”表述 |

## 2.4 主公式、性质与边界

### 2.4.1 主公式

把 2.3 的 $q_S^{\text{eq}}$ 代入 NOIP 池的达标比例：

$$
\boxed{
q_N(D)
=1-F_{N,t}\!\left(Q_{S,t}(1-q_S^{\text{eq}})\right)
=1-F_{N,t}\!\left(Q_{S,t}\!\left(1-g(q_S,D)\right)\right)
}.
$$

通过率口径：

$$
q_N^{\text{pass}}
=1-F_{N,t}\!\left(Q_{S,t}\!\left(1-\frac{q_S}{D_{\text{pass}}}\right)\right).
$$

几率口径：

$$
q_N^{\text{odds}}
=1-F_{N,t}\!\left(Q_{S,t}\!\left(1-\frac{q_S}{q_S+D_{\text{odds}}(1-q_S)}\right)\right).
$$

### 2.4.2 单调性与极限

- **对 $D$ 单调递减。** $D\uparrow\Rightarrow g\downarrow\Rightarrow 1-g\uparrow\Rightarrow Q_{S,t}\uparrow\Rightarrow F_{N,t}\uparrow\Rightarrow q_N\downarrow$。难度比越高，NOIP 比例越小。
- **对 $q_S$ 单调递增。** 固定 $D$ 时，$q_S\uparrow\Rightarrow q_S^{\text{eq}}\uparrow\Rightarrow c_N\downarrow\Rightarrow q_N\uparrow$。CSP-S 放宽，NOIP 也应放宽。
- **极限。** $D\to0^+$ 时 $q_S^{\text{eq}}\to1$，$c_N\to$ 分布下界，$q_N\to1$；$D\to\infty$ 时 $q_S^{\text{eq}}\to0$，$c_N\to$ 分布上界，$q_N\to0$。

### 2.4.3 特例：两个池子一样强

若 $N_t$ 是 $S_t$ 的随机样本（$F_{N,t}=F_{S,t}$），则

$$
q_N=1-F_{S,t}\!\left(Q_{S,t}(1-q_S^{\text{eq}})\right)=q_S^{\text{eq}}=g(q_S,D).
$$

即通过率口径下 $q_N=q_S/D_{\text{pass}}$，几率口径下 $q_N=q_S/[q_S+D_{\text{odds}}(1-q_S)]$。这就是 1.8 中 Q2 所说的“直接除以 1.2”的公式，它只在两池同分布时成立。

### 2.4.4 截断选择模型与边界

若 NOIP 是按 CSP-S 成绩硬截断选拔：

$$
N_t=\{i\in S_t: X_i\ge\tau_t\},
\qquad
s_t=1-F_{S,t}(\tau_t),
$$

则

$$
F_{N,t}(x)=\frac{F_{S,t}(x)-F_{S,t}(\tau_t)}{1-F_{S,t}(\tau_t)}
=\frac{F_{S,t}(x)-(1-s_t)}{s_t},
\qquad x\ge\tau_t.
$$

代入主公式：

$$
q_N=
\begin{cases}
\dfrac{1-F_{S,t}(c_N)}{s_t}=\dfrac{q_S^{\text{eq}}}{s_t}, & c_N\ge\tau_t,\\[6pt]
1, & c_N<\tau_t.
\end{cases}
$$

即

$$
\boxed{
q_N=\min\!\left(1,\ \frac{q_S^{\text{eq}}}{s_t}\right)
}
\quad\text{（纯截断模型）}.
$$

几个直接推论：

- **同百分比下的难度比。** 当 $q_N=q_S$ 时，$q_S^{\text{eq}}=s_t q_S$，故
  $$
  D_{\text{pass}}=\frac{q_S}{s_t q_S}=\frac{1}{s_t},
  \qquad
  D_{\text{odds}}=\frac{1/s_t-q_S}{1-q_S}.
  $$
  例如 $s_t=23\%$ 时，$D_{\text{pass}}\approx4.35$。这就是“NOIP 6/7 级远难于 CSP-S”的数量级来源。
- **难度持平的比例。** $D=1$ 时 $q_N=\min(1,q_S/s_t)$。若 $s_t>q_S$（NOIP 选拔率高于等级百分比），$q_N=q_S/s_t>q_S$；若 $s_t<q_S$，$q_N=1$（等级线低于 NOIP 入口线，人人达标）。
- **100% 边界。** 当 $q_S^{\text{eq}}\ge s_t$，即 $D_{\text{pass}}\le q_S/s_t$ 时，$q_N=1$。这不是计算错误，而是“NOIP 入口线已经高于 CSP-S 等级线”的必然结果。

### 2.4.5 省份异质性

各省名额和选拔线不同，$s_{p,t}$ 与 $F_{N,p,t}$ 也不同。全国 $q_N$ 是省际加权平均：

$$
q_N=\sum_p w_{p,t}\min\!\left(1,\frac{q_S^{\text{eq}}}{s_{p,t}}\right)
\quad\text{（纯截断近似）},
$$

或更一般地：

$$
q_N=\sum_p w_{p,t}\left[1-F_{N,p,t}\!\left(Q_{S,t}(1-q_S^{\text{eq}})\right)\right].
$$

强省 $s_{p,t}$ 小、池子强，$q_{N,p}$ 高；弱省相反。全国统一比例会掩盖这种差异，建议同时报告分省结果。

## 2.5 数据与估计

### 2.5.1 所需数据

| 数据表 | 字段 | 用途 |
|---|---|---|
| CSP-S 成绩表 | 年份、考号、省份、年级、成绩、轮次 | 估计 $F_{S,t}$、$Q_{S,t}$ |
| NOIP 成绩表 | 年份、考号、省份、成绩、奖项、类别（A/B/C/D） | 估计 $F_{N,t}$、$q_N^{\text{obs}}$ |
| 链接表 | 年份、CSP-S 考号、NOIP 考号、匹配置信度 | 构建 $N_t$ 的 $X_i$ |
| 分数线表 | 年份、级别、$q_S$、官方分数线 | 校准 $c_S$ |
| 名额表 | 年份、省份、$N_{N,p}$、$N_{S,p}$ | 估计 $s_t$、权重 $w_p$ |

> 若只有获奖名单而没有全体参赛成绩，主方法无法直接估计 $F_{S,t}$ 和 $F_{N,t}$；可用 2.5.6 的获奖率反推方案给出粗略区间，但应标注为近似估计。

### 2.5.2 路线 A：个体链接（首选）

若能把每个 NOIP 考生链接到其当年的 CSP-S 成绩 $X_i$，则

$$
\hat q_N=\frac{1}{N_N}\sum_{i\in N_t}\mathbf{1}\{X_i\ge \hat c_N\},
\qquad
\hat c_N=Q_{S,t}\!\left(1-g(q_S,D)\right).
$$

这是 $q_N$ 的直接估计，不需要分数等值，假设最少。若链接样本不是 $N_t$ 的随机子样本（匹配率依赖 $X$ 或省份），用逆概率加权：

$$
\hat q_N^{\text{IPW}}
=\frac{\sum_{i\in M} w_i\,\mathbf{1}\{X_i\ge \hat c_N\}}{\sum_{i\in M} w_i},
\qquad
w_i=\frac{1}{\hat\pi_i},
$$

其中 $M$ 是成功链接的样本，$\hat\pi_i=P(\text{链接}\mid X_i,\text{省份})$ 可由逻辑回归估计。报告匹配率 $\lambda=|M|/N_N$。

### 2.5.3 路线 B：分数等值

若只有 NOIP 成绩 $Y_i$ 和部分链接样本，先把 CSP-S 分数线等值到 NOIP 量表：

$$
c_N^{\text{eq}}=Q_{N,t}\!\left(F_{S,t}^{M}(c_N)\right),
$$

其中 $F_{S,t}^{M}$ 是链接样本 $M$ 的 CSP-S 成绩分布。然后

$$
\hat q_N=1-F_{N,t}(c_N^{\text{eq}}).
$$

等值方法：

- **等百分位等值（equipercentile equating）**：假设两量表存在单调关系，用平滑后的累积分布匹配百分位（Kolen & Brennan, 2014）。
- **线性等值**：假设两量表线性相关，$c_N^{\text{eq}}=a+b\,c_N$，$a,b$ 由链接样本的均值/标准差或分位数估计。
- **核平滑 / 对数线性平滑**：分数分布稀疏时，先平滑再等值，减少分位数抖动。

等值的标准误用 bootstrap 估计（重抽链接样本）。

### 2.5.4 路线 C：仅聚合数据（截断模型）

若没有个体链接，只有 CSP-S 成绩分布和 NOIP 人数，可用参数化截断模型：

1. 对 $F_{S,t}$ 拟合一个分布族（正态、偏正态、对数正态），或用经验分布；
2. 由 $s_t=N_{N,t}/N_{S,t}$ 反解选拔线 $\tau_t=Q_{S,t}(1-s_t)$；
3. 用 2.4.4 的公式计算 $q_N$。

若只有“当前百分比” $q_N^{\text{current}}$ 而没有 $\tau_t$，可把 $\tau_t$ 当作单参数，校准到 $q_N(\tau_t)=q_N^{\text{current}}$，再用校准后的模型预测其他 $D$。这是一参数校准，必须报告对分布族设定的敏感性。

### 2.5.5 链接误差、选择偏差与类别差异

- **匹配误差。** 优先用考号/学号精确匹配；否则用概率记录链接（Fellegi–Sunter），保留高置信匹配，报告匹配率与置信度分布。未匹配样本给出上下界：全部视为未达标（$q_N$ 下界）或全部视为达标（上界）。
- **选择偏差。** $N_t$ 本身就是按 $X$ 选出的，这不是偏差，而是目标人群的定义；只要链接样本在 $N_t$ 内随机，路线 A 就是一致的。若匹配率依赖 $X$，用 IPW。
- **C/D 类。** C 类（推荐名额）和 D 类（女生专项）的选拔机制与 A/B 类不同，$X$ 分布可能不同。主表用 A/B 类，附表给含 C/D 的结果。

### 2.5.6 只有获奖数据时的近似

若手头只有“获奖名单/获奖人数”，没有全体参赛成绩，主公式无法直接估计 $F_{S,t}$ 和 $F_{N,t}$。此时可用获奖率反推总人数，再用纯截断模型给出粗略区间：

1. **反推 NOIP 参赛人数。**
   $$
   \hat N_{N,t}=\frac{A_{N,t}}{r_{N,t}},
   $$
   其中 $A_{N,t}$ 是 NOIP 获奖总人数，$r_{N,t}$ 是当年总获奖率。2024 年起 NOIP 总获奖率 67%（一等 20%、二等 22%、三等 25%）；若只统计某一等奖，用对应获奖率。
2. **反推 CSP-S 参考人数。**
   $$
   \hat N_{S,t}=\frac{A_{S1,t}}{r_{S1,t}},
   $$
   其中 $A_{S1,t}$ 是 CSP-S 提高组第二轮一等人数，$r_{S1,t}$ 是一等比例（约 20%；2026 年提高组为 20.24%）。
3. **估计选拔率。**
   $$
   \hat s_t=\frac{\hat N_{N,t}}{\hat N_{S,t}}.
   $$
   若 CSP-S 总人数包含初中生/小学生，分母应换成高中生子集人数；否则 $\hat s_t$ 会被低估。
4. **用纯截断近似。**
   $$
   \hat q_N=\min\!\left(1,\frac{q_S^{\text{eq}}}{\hat s_t}\right).
   $$
5. **不确定性。** 对 $r_{N,t}$、$r_{S1,t}$ 和高中生占比做敏感性分析，报告 $q_N$ 的区间。获奖率随年份、省份变化时，不要把它当作精确常数。

更好的做法：用获奖分数线（如 CSP-S 一等线、NOIP 一等线）校准一个参数化分布（正态/偏正态），使模型同时匹配“分数线”和“获奖人数”，再计算 $q_N$。这比单纯用获奖率反推更稳，但仍不如个体链接。

注意：获奖数据只能反推“总人数”和“截断点”，不能恢复获奖者以下的成绩分布；因此结果对分布假设敏感，必须标注为近似估计。

## 2.6 年份 $t$ 的进入方式与可识别性

### 2.6.1 年份通过分布进入

主公式中，$t$ 通过 $F_{S,t}$、$Q_{S,t}$、$F_{N,t}$ 进入。即使 $q_S$ 和 $D$ 固定，不同年份的分数分布和 NOIP 池构成不同，$q_N$ 也会不同。这正是“输入 2025 就用 2025 年数据”的含义。

### 2.6.2 当年实际难度比的估计

若想从数据反推“当前规则下 NOIP 实际难多少倍”，需要先把当前 NOIP 等级线放到 CSP-S 量表上。

若有个体链接，直接使用 NOIP 考生链接到的 CSP-S 成绩分布 $F_{X\mid N,t}$，取其在当前 NOIP 百分比处的分位数：

$$
c_{X,t}^{\text{current}}=Q_{X\mid N,t}(1-q_N^{\text{current}}),
$$

其中 $Q_{X\mid N,t}$ 是“NOIP 考生的 CSP-S 成绩”分布的分位数函数。若只有 NOIP 成绩，先用 2.5.3 的等值映射把 NOIP 分数线 $Q_{N,t}(1-q_N^{\text{current}})$ 映射到 CSP-S 量表，得到 $c_{X,t}^{\text{current}}$。

然后把它放回全体 CSP-S 参照分布：

$$
q_S^{\text{eq},t}=1-F_{S,t}(c_{X,t}^{\text{current}}),
$$

于是

$$
D_t^{\text{pass}}=\frac{q_S}{q_S^{\text{eq},t}},
\qquad
D_t^{\text{odds}}
=\frac{\operatorname{odds}(q_S)}{\operatorname{odds}(q_S^{\text{eq},t})}.
$$

这是“当年、当前百分比”的观测难度比，可作为 2.6.3 模型的因变量，也可用来校验外部输入的 $D$。注意：$c_{X,t}^{\text{current}}$ 必须是 CSP-S 量表上的分数，不能直接把 NOIP 分数代入 $F_{S,t}$。

### 2.6.3 多年模型与预测

若有多年的 $D_t$（或 $q_S^{\text{eq},t}$），可建立模型：

$$
\ln D_{t,L}
=\alpha_L+\beta_L(t-t_0)+\gamma_L\operatorname{logit}(q_{S,t,L})
+\delta_L\ln s_{t,L}+u_{t,L},
\qquad
u_{t,L}\sim N(0,\tau_L^2),
$$

其中 $L\in\{6,7\}$ 表示级别。$\ln D$ 保证正值；$\operatorname{logit}(q_S)$ 捕捉百分比非线性；$\ln s_t$ 控制选拔率变化。用加权最小二乘（权重 $1/SE_t^2$）或贝叶斯层次模型估计；至少 3 年数据才拟合趋势，否则用最近一年 $D_t$ 并报告宽区间。

给定目标年份 $t^*$ 和 $q_S$，预测：

$$
\hat D_{t^*,L}
=\exp\!\left(\hat\alpha_L+\hat\beta_L(t^*-t_0)
+\hat\gamma_L\operatorname{logit}(q_S)
+\hat\delta_L\ln s_{t^*,L}\right),
$$

再代入主公式。预测方差：

$$
\operatorname{Var}(\ln \hat D_{t^*})
=\mathbf{x}_{t^*}'\hat\Sigma\,\mathbf{x}_{t^*}+\hat\tau_L^2,
$$

其中 $\mathbf{x}_{t^*}$ 是协变量向量，$\hat\Sigma$ 是系数协方差矩阵。

**稳健性替代：** 直接对 $q_S^{\text{eq},t}$ 建 beta 回归（因变量在 $(0,1)$），协变量为 $t$、$\operatorname{logit}(q_S)$、$\ln s_t$，再用 $q_N=1-F_N(Q_S(1-q_S^{\text{eq}}))$。当 $q_S^{\text{eq}}$ 接近 0 或 1 时，beta 回归比 $D$ 的比值模型更稳。

### 2.6.4 可识别性说明

在本文的定义下，$D$ 是通过 $q_S^{\text{eq}}$ 定义的：

$$
q_S^{\text{eq}}=g(q_S,D).
$$

因此给定 $q_S$ 和 $D$，$q_S^{\text{eq}}$ 就被唯一确定；年份 $t$ 不能再独立地改变 $q_N$，除非它改变 $F_{S,t}$ 或 $F_{N,t}$。这不是模型缺陷，而是“难度比”定义的必然结果。

如果希望年份在点估计中独立发挥作用，有两种做法：

1. **相对模式。** 把输入的 $D$ 解释为“相对当年基线的倍数”：
   $$
   D^{\text{abs}}=D^{\text{rel}}\times D_t^{\text{base}},
   $$
   其中 $D_t^{\text{base}}$ 是年份 $t$ 在当前规则下的基线难度比（由 2.6.2 估计）。然后
   $$
   q_N=1-F_{N,t}\!\left(Q_{S,t}(1-g(q_S,D^{\text{abs}}))\right).
   $$
   这样 $D^{\text{rel}}=1$ 表示“与当年现状持平”，$D^{\text{rel}}=1.2$ 表示“比当年现状再难 20%”。
2. **分数阈值模式。** 直接在分数尺度上定义难度比（见 2.6.5），年份通过 $F_{N,t}$ 的均值/标准差进入。

**不要**把 $q_N$ 直接对 $D$ 做回归：$D$ 本身是 $q_S$ 和 $q_N$（经由 $q_S^{\text{eq}}$）的函数，直接回归会产生循环关系，系数不可解释。应使用 2.4 的结构式，或对 $D_t$ 建模型。

### 2.6.5 分数阈值口径（补充）

若“难度比”被定义为“分数线的距离比”，可写：

$$
c_N=\mu_{N,t}+D_{\text{score}}\left(c_S-\mu_{S,t}\right),
\qquad
q_N=1-F_{N,t}(c_N),
$$

其中 $\mu_{S,t}$、$\mu_{N,t}$ 是两池的均值（或中位数），$c_S=Q_{S,t}(1-q_S)$。这一口径直接使用分数尺度，年份通过 $\mu$ 和 $F$ 进入，适合分数分布近似同尺度的情况。它与通过率/几率口径不保证等价，报告时需注明。

## 2.7 不确定性量化

### 2.7.1 Bootstrap

推荐两阶段整群 bootstrap：

1. 在省份层面有放回抽取省份（若省份数足够）；
2. 在省内抽取考生（或链接对）；
3. 对每个重抽样本重算 $F_{S,t}$、$F_{N,t}$、$\hat c_N$、$\hat q_N$；
4. 重复 $B=1000$ 次，取 2.5% 和 97.5% 分位数作为 95% 区间。

若 $D$ 来自 2.6.3 的模型，用参数 bootstrap：从 $\hat\Sigma$ 和 $\hat\tau^2$ 抽系数与随机效应，重新预测 $D$，再算 $q_N$。

### 2.7.2 Delta 法

设 $q_N=1-F_N(c_N)$，$c_N=Q_S(u)$，$u=1-g(D)$。由链式法则：

$$
\frac{dq_N}{dD}
=-f_N(c_N)\frac{dc_N}{du}\frac{du}{dD}
=\frac{f_N(c_N)}{f_S(c_N)}\,g'(D),
$$

其中 $f_S,f_N$ 是密度函数，$dc_N/du=1/f_S(c_N)$，$du/dD=-g'(D)$。

通过率口径（$g=q_S/D$，$g'=-q_S/D^2$）：

$$
\frac{dq_N}{dD_{\text{pass}}}
=-\frac{f_N(c_N)}{f_S(c_N)}\frac{q_S}{D_{\text{pass}}^2},
\qquad
SE(q_N)\approx \frac{f_N(c_N)}{f_S(c_N)}\frac{q_S^{\text{eq}}}{D_{\text{pass}}}\,SE(D_{\text{pass}}).
$$

在 log 尺度上（$D\,g'(D)=-q_S^{\text{eq}}$）：

$$
SE(q_N)\approx \frac{f_N(c_N)}{f_S(c_N)}\,q_S^{\text{eq}}\,SE(\ln D_{\text{pass}}).
$$

几率口径（$g=q_S/[q_S+D(1-q_S)]$，$g'=-q_S^{\text{eq}}(1-q_S^{\text{eq}})/D$）：

$$
SE(q_N)\approx \frac{f_N(c_N)}{f_S(c_N)}\,q_S^{\text{eq}}(1-q_S^{\text{eq}})\,SE(\ln D_{\text{odds}}).
$$

若 $f_N=f_S$（两池同分布），以上退化为常见的二项式 delta 法公式；若 $f_N>f_S$（NOIP 池在分数线附近更密集），标准误会被放大，提示 NOIP 的百分位对分数线更敏感。

### 2.7.3 报告方式

- 主表：点估计 + 95% 区间（bootstrap）；
- 附表：两种口径的对照；
- 若 $D$ 是政策给定值而非估计值，报告 $q_N(D)$ 曲线和 $D\pm\delta$ 的敏感性带，不把 $D$ 当作随机变量；
- 若 $q_S$ 是估计值，用同样的 delta 法传播其不确定性。

## 2.8 模型校验

### 2.8.1 留一年交叉验证（LOYO）

对每一年 $t$：

1. 用其余年份拟合 2.6.3 的 $D_t$ 模型（或截断模型参数）；
2. 预测 $t$ 年的 $q_N$；
3. 与 $t$ 年的观测 $q_N^{\text{obs}}$（由链接数据按 2.5.2 计算）比较。

指标：

- MAE、RMSE；
- 校准斜率：把观测值对预测值回归，理想斜率 1、截距 0；
- 95% 区间覆盖率：理想接近 95%；
- 若样本量允许，报告按省份/级别的分层误差。

### 2.8.2 区分度检查（AUC）

在链接样本中，用 CSP-S 成绩 $X$ 预测“是否达到 NOIP 等级线” $1\{Y\ge c_N^{\text{current}}\}$，计算 AUC：

- AUC 高（如 >0.9）：CSP-S 成绩是 NOIP 等级的良好代理，共同参照系可靠；
- AUC 低：两赛事测的能力差异大，百分位映射的解释力有限，应报告并谨慎使用。

### 2.8.3 分布族敏感性

对路线 C，分别用正态、偏正态、对数正态、经验分布拟合 $F_S$，比较 $q_N$ 的差异；若差异大，说明结果对分布假设敏感，应优先补充链接数据。

## 2.9 敏感性分析

建议至少做以下六组：

| 维度 | 处理 | 报告 |
|---|---|---|
| 链接匹配率 $\lambda$ | 未匹配全部视为未达标 / 全部达标 / IPW | $q_N$ 的上下界与主估计 |
| 零分与缺考 | 纳入（视为未达标）/ 剔除 | 两者差异 |
| C/D 类 | 仅 A/B / 含 C/D | 两者差异 |
| 等值方法 | 恒等 / 线性 / 等百分位 / 平滑 | $q_N$ 范围 |
| 省份权重 | 按人数加权 / 等权 | 全国与分省范围 |
| $F_S$ 分布族 | 正态 / 偏正态 / 经验 | 路线 C 的模型不确定性 |

用龙卷风图（tornado chart）展示各因素对 $q_N$ 的影响幅度，主文报告“主估计 + 区间 + 最关键的两个敏感性来源”。

## 2.10 政策反推与边界

### 2.10.1 由目标 $q_N$ 反推难度比

若政策目标是“NOIP 6 级定为 $q_N^{\text{target}}$”，先找该比例对应的等级线，并把它放到 CSP-S 量表上：

- 若有个体链接，取 NOIP 考生 CSP-S 成绩分布的 $(1-q_N^{\text{target}})$ 分位数：
  $$
  c_X=Q_{X\mid N,t}(1-q_N^{\text{target}}).
  $$
- 若只有 NOIP 成绩，先由 $Q_{N,t}(1-q_N^{\text{target}})$ 得到 NOIP 分数线，再用 2.5.3 的等值映射到 CSP-S 量表，得到 $c_X$。

然后：

$$
q_S^{\text{eq}}=1-F_{S,t}(c_X),
\qquad
D_{\text{pass}}=\frac{q_S}{q_S^{\text{eq}}},
\qquad
D_{\text{odds}}=\frac{\operatorname{odds}(q_S)}{\operatorname{odds}(q_S^{\text{eq}})}.
$$

这回答了“若把 NOIP 比例调到某个值，相当于难度比变成多少”。注意 $c_X$ 必须在 CSP-S 量表上，不能直接用 NOIP 分数代入 $F_{S,t}$。

### 2.10.2 由目标 $q_N$ 与 $D$ 反推所需名额

在纯截断模型下，$q_N=q_S^{\text{eq}}/s$，故

$$
s=\frac{q_S^{\text{eq}}}{q_N^{\text{target}}},
\qquad
N_N=s\,N_S.
$$

更一般地，若已知目标 $q_N$ 和等级线 $c_N$（这里 $c_N$ 是目标等级线在 CSP-S 量表上的位置，由链接样本或等值映射得到），需要选择选拔线 $\tau$ 使得

$$
\frac{1-F_{S,t}(c_N)}{1-F_{S,t}(\tau)}=q_N^{\text{target}}
\quad\Longrightarrow\quad
1-F_{S,t}(\tau)=\frac{1-F_{S,t}(c_N)}{q_N^{\text{target}}},
$$

$$
\boxed{
N_N=N_S\cdot\frac{1-F_{S,t}(c_N)}{q_N^{\text{target}}}
}.
$$

注意：扩大名额会改变 $N_t$ 的构成，进而改变 $F_{N,t}$ 和实际难度比；上式是“保持等级线不变”的一阶近似，需迭代或重新估计。

### 2.10.3 100% 边界的政策含义

当 $q_S^{\text{eq}}\ge s_t$（即 $D_{\text{pass}}\le q_S/s_t$）时，$q_N=1$。这意味着按 CSP-S 百分位标准，NOIP 池内人人达标，等级失去区分度。此时有三种政策选择：

1. **扩大 NOIP 名额**，提高 $s_t$，使等级线重新落在池内；
2. **改用分数带**（如 NOIP 前 300 名、前 10% 等绝对标准），而不是 CSP-S 百分位；
3. **重新定义参照池**（如以 NOIP 池自身为参照，或合并 CSP-S/NOIP 池）。

方法本身只给出数学边界，选择哪一种属于政策判断。

## 2.11 局限

1. **描述性而非因果。** $D$ 是当年数据的描述，不是“把百分比从 20% 调到 30% 会导致难度变化多少”的因果效应；后者需要考生行为、备赛投入等额外假设。
2. **分数可比性。** 跨年比较需要等值；等值误差会传播到 $q_N$。
3. **链接与缺失。** 匹配率低、匹配非随机时，路线 A 的估计会有偏；必须报告上下界。
4. **省份异质性。** 全国统一比例可能掩盖强省/弱省差异；建议分省报告。
5. **能力维度差异。** CSP-S 成绩不能完全代表 NOIP 表现；AUC 低时，百分位映射的解释力有限。
6. **政策价值判断。** “难度持平”本身是价值选择；本文提供技术映射，不替政策制定者做公平性判断。

# 第三部分 实施手册

## 3.1 数据字典

### 3.1.1 最小数据集

| 表名 | 字段 | 类型 | 说明 |
|---|---|---|---|
| `csp_scores` | `year` | int | 年份 |
| | `csp_id` | string | CSP-S 考号（脱敏后） |
| | `province` | string | 省份 |
| | `grade` | string | 年级（高一/高二/高三/初中） |
| | `score` | float | 提高组第二轮成绩 |
| | `round` | string | 固定为 `S2`（提高组第二轮） |
| `noip_scores` | `year` | int | 年份 |
| | `noip_id` | string | NOIP 考号（脱敏后） |
| | `province` | string | 省份 |
| | `score` | float | NOIP 成绩 |
| | `award` | string | 一等/二等/三等/无 |
| | `category` | string | A/B/C/D |
| `link_table` | `year` | int | 年份 |
| | `csp_id` | string | CSP-S 考号 |
| | `noip_id` | string | NOIP 考号 |
| | `match_prob` | float | 匹配置信度（0–1） |
| `cutoffs` | `year` | int | 年份 |
| | `level` | int | 6 或 7 |
| | `q_S` | float | CSP-S 百分比（0.20/0.10） |
| | `c_S` | float | 官方或推算分数线（可选） |
| `quotas` | `year` | int | 年份 |
| | `province` | string | 省份 |
| | `N_S` | int | CSP-S 高中生参考人数 |
| | `N_N` | int | NOIP 名额/参赛人数 |

### 3.1.2 数据质量要求

- CSP-S 成绩必须与 NOIP 同年；若使用最近一次 CSP-S 成绩，需在报告中注明并做敏感性分析。
- 年级字段用于构造高中生参照子集；若缺失，用“是否具备 NOIP 报名资格”替代。
- C/D 类单独标记，便于主表/附表切换。
- 所有个人标识在分析前脱敏，链接表只保留加密 ID。

## 3.2 算法伪代码

```text
算法：由 (q_S, D, t) 计算 q_N
输入：
  q_S        CSP-S 百分比（0<q_S<1）
  D          难度比（>0）
  t          年份
  measure    "pass" 或 "odds"
  data[t]    含 F_S,t、F_N,t（或链接样本）、s_t、省份权重
输出：
  q_N        点估计
  CI         bootstrap 95% 区间

1. 校验输入：0<q_S<1；D>0；measure ∈ {"pass","odds"}
2. 计算 q_S^eq：
   若 measure="pass"：
       q_S^eq = q_S / D
   若 measure="odds"：
       q_S^eq = q_S / (q_S + D*(1-q_S))
3. 计算 CSP-S 分数线：
   c_N = Quantile(F_S,t, 1 - q_S^eq)
4. 计算 NOIP 达标比例：
   若有个体链接：
       q_N = mean( X_i >= c_N for i in N_t )
   否则若只有 NOIP 成绩与等值映射：
       c_N_eq = Quantile(F_N,t, CDF_S,t^M(c_N))
       q_N = 1 - CDF_N,t(c_N_eq)
   否则（仅聚合数据）：
       q_N = min(1, q_S^eq / s_t)   # 纯截断近似
5. Bootstrap（B=1000）：
   重抽省份/考生，重复 2–4，记录 q_N^(b)
   CI = [quantile(q_N^(b), 0.025), quantile(q_N^(b), 0.975)]
6. 输出 q_N、CI、q_S^eq、c_N、measure、t、匹配率、敏感性摘要
```

## 3.3 Python 参考实现

以下代码是“路线 A（个体链接）”的最小实现，假设输入为 NumPy 数组；真实使用时替换为数据库查询。

```python
import numpy as np

def qs_eq(qS: float, D: float, measure: str = "pass") -> float:
    """把难度比 D 翻译成 CSP-S 参照系中的等价百分位 qS_eq。"""
    if not (0 < qS < 1):
        raise ValueError("qS must be in (0, 1)")
    if D <= 0:
        raise ValueError("D must be positive")
    if measure == "pass":
        return qS / D
    if measure == "odds":
        return qS / (qS + D * (1 - qS))
    raise ValueError("measure must be 'pass' or 'odds'")

def qn_from_linked(csp_scores: np.ndarray,
                   noip_csp_scores: np.ndarray,
                   qS: float,
                   D: float,
                   measure: str = "pass") -> dict:
    """
    csp_scores:       全体 CSP-S 参考人群的成绩
    noip_csp_scores:  NOIP 考生链接到的 CSP-S 成绩
    """
    qeq = qs_eq(qS, D, measure)
    cutoff = np.quantile(csp_scores, 1 - qeq)  # 经验分位数
    qN = float(np.mean(noip_csp_scores >= cutoff))
    return {"qS_eq": qeq, "cutoff": float(cutoff), "qN": qN}

def bootstrap_qn(csp_scores, noip_csp_scores, qS, D,
                 measure="pass", B=1000, seed=2026):
    """两阶段 bootstrap：先重抽 NOIP 考生，再重抽 CSP-S 参考人群。"""
    rng = np.random.default_rng(seed)
    nS, nN = len(csp_scores), len(noip_csp_scores)
    out = np.empty(B)
    for b in range(B):
        s = rng.choice(csp_scores, size=nS, replace=True)
        n = rng.choice(noip_csp_scores, size=nN, replace=True)
        out[b] = qn_from_linked(s, n, qS, D, measure)["qN"]
    return {
        "qN": qn_from_linked(csp_scores, noip_csp_scores, qS, D, measure)["qN"],
        "ci_low": float(np.quantile(out, 0.025)),
        "ci_high": float(np.quantile(out, 0.975)),
    }

def uniform_approx(qS: float, D: float, s: float,
                   measure: str = "pass") -> float:
    """纯截断模型的快速近似：qN = min(1, qS_eq / s)。"""
    return min(1.0, qs_eq(qS, D, measure) / s)

if __name__ == "__main__":
    # 示例（虚拟数据）
    rng = np.random.default_rng(0)
    csp = rng.normal(200, 60, 32643)          # 全体 CSP-S 成绩
    noip = rng.normal(320, 50, 7500)          # NOIP 考生的 CSP-S 成绩（更强）
    for level, qS in [(6, 0.20), (7, 0.10)]:
        for measure in ["pass", "odds"]:
            res = qn_from_linked(csp, noip, qS, 1.2, measure)
            print(level, measure, res)
```

> 说明：示例中的正态分布仅用于演示接口，真实数据应使用经验分布或平滑后的分布；若使用路线 B/C，替换 `qn_from_linked` 的实现即可。

## 3.4 输出模板

### 3.4.1 主表

| 年份 | 级别 | $q_S$ | 口径 | $D$ | $q_S^{\text{eq}}$ | 分数线 $c_N$ | $q_N$ | 95% CI | 匹配率 |
|---|---|---:|---|---:|---:|---:|---:|---|---:|
| 2025 | 6 | 20% | pass | 1.2 | 16.67% | … | … | [.., ..] | … |
| 2025 | 6 | 20% | odds | 1.2 | 17.24% | … | … | [.., ..] | … |
| 2025 | 7 | 10% | pass | 1.2 | 8.33% | … | … | [.., ..] | … |
| 2025 | 7 | 10% | odds | 1.2 | 8.47% | … | … | [.., ..] | … |

### 3.4.2 附图

- $q_N$ 随 $D$ 变化的曲线（6/7 级各一条，两种口径各一条）；
- $q_N$ 随年份变化的曲线（固定 $D$）；
- 分省 $q_N$ 的箱线图；
- 敏感性龙卷风图。

### 3.4.3 文字结论模板

> 在 2025 年数据、CSP-S 6 级百分比 20%、难度比 1.2（通过率口径）的设定下，NOIP 6 级比例估计为 X%（95% CI [Y, Z]）。若改用几率口径，结果为 X'%。主要不确定性来自链接匹配率与省份权重；详见敏感性分析。

## 3.5 质量检查清单

- [ ] $q_S$ 的定义人群（全体 CSP-S / 高中生子集）已写明；
- [ ] CSP-S 与 NOIP 年份一致，或已注明跨年映射；
- [ ] 链接匹配率 $\lambda$ 已报告，未匹配样本已做上下界；
- [ ] C/D 类是否纳入已说明；
- [ ] 零分/缺考处理已说明；
- [ ] 两种难度口径都已计算并对照；
- [ ] bootstrap 区间已报告（至少 1000 次）；
- [ ] 至少做了链接、类别、等值方法三组敏感性分析；
- [ ] 分省结果与全国加权结果一致或差异已解释；
- [ ] 结论中区分了“描述性难度比”与“政策建议”。

## 3.6 当前程序：边界局部中位数与截断校正

`calc_rating_matched.py` 使用全国 CSP-S 累计比例确定等级锚点，然后在该分数线附近使用严格同人配对，比较 ±1/2/3/5 个百分点的局部窗口。可见获奖者基线为非负斜率局部线性中位数；校正候选通过按省官方获奖门槛的条件截断似然拟合有界正态或厚尾 t(5) 分布，取其完整条件中位数。全国比例在分数线确定后直接用全国总人数计数，不使用省名额或省人数估算。

先留出五分之一学校作独立审计，其余学校内三折选择分布与带宽。人工遮挡提高训练集的可见门槛，再在原始未遮挡审计集上、按每名选手实际 CSP-S 分数和原门槛比较中位数预测 MAE；这只能检验已知部分的恢复能力，不能证明真实获奖线以下的分布。仅在预设验证与稳健性条件通过时采用校正，否则分别显示基线、候选及不采用理由。

程序区分官方获奖线与实际最低获奖分，保留零获奖省份进行门槛核验；缺失门槛不作零处理。未知、未参赛和未获奖状态不互相混淆。有效门槛以上的固定分数计数、同分范围、固定模型的学校重抽区间、同目标模型范围及人为设置的缺失π情景分别呈现，后两者不是95%置信区间。

GUI 包含结论、模型与验证、敏感性、数据与门槛、方法与限制、图形核对六页。旧纯截断/D 程序 `calc_rating_percentage.py` 仅作历史归档。

---

# 附录

## 附录 A 公式推导

### A.1 主公式

由定义：

$$
q_N=P_{N,t}(X\ge c_N)=1-F_{N,t}(c_N).
$$

NOIP 等级线 $c_N$ 在 CSP-S 参照系中的等价百分位为

$$
q_S^{\text{eq}}=P_{S,t}(X\ge c_N)=1-F_{S,t}(c_N),
$$

故

$$
c_N=Q_{S,t}(1-q_S^{\text{eq}}).
$$

代入 $q_S^{\text{eq}}=g(q_S,D)$，得

$$
q_N=1-F_{N,t}\!\left(Q_{S,t}(1-g(q_S,D))\right).
$$

### A.2 两种难度比的关系

$$
D_{\text{odds}}
=\frac{q_S/(1-q_S)}{q_S^{\text{eq}}/(1-q_S^{\text{eq}})}
=\frac{q_S}{q_S^{\text{eq}}}\cdot\frac{1-q_S^{\text{eq}}}{1-q_S}
=D_{\text{pass}}\cdot\frac{1-q_S^{\text{eq}}}{1-q_S}.
$$

代入 $q_S^{\text{eq}}=q_S/D_{\text{pass}}$：

$$
D_{\text{odds}}
=D_{\text{pass}}\cdot\frac{1-q_S/D_{\text{pass}}}{1-q_S}
=\frac{D_{\text{pass}}-q_S}{1-q_S}.
$$

逆变换：

$$
D_{\text{pass}}=q_S+D_{\text{odds}}(1-q_S).
$$

### A.3 Delta 法

设 $u=1-g(D)$，$c_N=Q_S(u)$，$q_N=1-F_N(c_N)$。则

$$
\frac{dc_N}{dD}
=\frac{dQ_S}{du}\cdot\frac{du}{dD}
=\frac{1}{f_S(c_N)}\cdot(-g'(D)),
$$

$$
\frac{dq_N}{dD}
=-f_N(c_N)\frac{dc_N}{dD}
=\frac{f_N(c_N)}{f_S(c_N)}g'(D).
$$

通过率：$g'=-q_S/D^2$，故

$$
\frac{dq_N}{dD}
=-\frac{f_N(c_N)}{f_S(c_N)}\frac{q_S}{D^2}.
$$

几率：$g'=-q_S^{\text{eq}}(1-q_S^{\text{eq}})/D$，故

$$
\frac{dq_N}{dD}
=-\frac{f_N(c_N)}{f_S(c_N)}\frac{q_S^{\text{eq}}(1-q_S^{\text{eq}})}{D}.
$$

### A.4 纯截断模型

$N=\{X\ge\tau\}$，$s=1-F_S(\tau)$。对 $x\ge\tau$：

$$
F_N(x)=\frac{F_S(x)-F_S(\tau)}{1-F_S(\tau)}
=\frac{F_S(x)-(1-s)}{s}.
$$

若 $c_N\ge\tau$：

$$
q_N=1-F_N(c_N)
=\frac{1-F_S(c_N)}{s}
=\frac{q_S^{\text{eq}}}{s}.
$$

若 $c_N<\tau$，则 $N$ 中所有人都在 $c_N$ 以上，$q_N=1$。故 $q_N=\min(1,q_S^{\text{eq}}/s)$。

### A.5 同百分比下的难度比

在纯截断模型下令 $q_N=q_S$，则 $q_S^{\text{eq}}=s q_S$，故

$$
D_{\text{pass}}=\frac{q_S}{s q_S}=\frac{1}{s},
\qquad
D_{\text{odds}}=\frac{1/s-q_S}{1-q_S}.
$$

例如 $s=0.23$、$q_S=0.20$：$D_{\text{pass}}=4.35$，$D_{\text{odds}}=5.18$。

## 附录 B 数值表

### B.1 $q_S^{\text{eq}}$ 对照表

**6 级（$q_S=20\%$）**

| $D$ | 通过率口径 $q_S^{\text{eq}}$ | 几率口径 $q_S^{\text{eq}}$ |
|---:|---:|---:|
| 1.0 | 20.00% | 20.00% |
| 1.1 | 18.18% | 18.52% |
| 1.2 | 16.67% | 17.24% |
| 1.3 | 15.38% | 16.13% |
| 1.5 | 13.33% | 14.29% |
| 2.0 | 10.00% | 11.11% |

**7 级（$q_S=10\%$）**

| $D$ | 通过率口径 $q_S^{\text{eq}}$ | 几率口径 $q_S^{\text{eq}}$ |
|---:|---:|---:|
| 1.0 | 10.00% | 10.00% |
| 1.1 | 9.09% | 9.17% |
| 1.2 | 8.33% | 8.47% |
| 1.3 | 7.69% | 7.87% |
| 1.5 | 6.67% | 6.90% |
| 2.0 | 5.00% | 5.26% |

### B.2 纯截断模型下的 $q_N$（$s=23\%$）

**6 级（$q_S=20\%$）**

| $D$ | 通过率口径 $q_N$ | 几率口径 $q_N$ |
|---:|---:|---:|
| 1.0 | 86.96% | 86.96% |
| 1.1 | 79.05% | 80.52% |
| 1.2 | 72.46% | 74.96% |
| 1.3 | 66.89% | 70.13% |
| 1.5 | 57.97% | 62.11% |
| 2.0 | 43.48% | 48.31% |

**7 级（$q_S=10\%$）**

| $D$ | 通过率口径 $q_N$ | 几率口径 $q_N$ |
|---:|---:|---:|
| 1.0 | 43.48% | 43.48% |
| 1.1 | 39.53% | 39.89% |
| 1.2 | 36.23% | 36.85% |
| 1.3 | 33.45% | 34.24% |
| 1.5 | 28.99% | 29.99% |
| 2.0 | 21.74% | 22.88% |

### B.3 $D=1$ 时 $q_N=q_S/s$ 随 $s$ 的变化

| $s$ | 6 级 $q_N$（$q_S=20\%$） | 7 级 $q_N$（$q_S=10\%$） |
|---:|---:|---:|
| 10% | 100%（封顶） | 100% |
| 15% | 100%（封顶） | 66.67% |
| 20% | 100% | 50.00% |
| 25% | 80.00% | 40.00% |
| 30% | 66.67% | 33.33% |
| 35% | 57.14% | 28.57% |
| 40% | 50.00% | 25.00% |

> 表 B.2/B.3 是纯截断模型的示例，不是真实估计；真实计算用 2.5 的路线 A/B/C。

## 附录 C 术语表

| 术语 | 含义 |
|---|---|
| 参照人群 | 用来做比较的基准人群，本文指 CSP-S 提高组第二轮考生（或其中高中生） |
| 等价百分位 $q_S^{\text{eq}}$ | NOIP 等级线在 CSP-S 参照系中对应的百分位 |
| 通过率比 | $D_{\text{pass}}=q_S/q_S^{\text{eq}}$，以通过率之比衡量难度 |
| 几率比 | $D_{\text{odds}}=\operatorname{odds}(q_S)/\operatorname{odds}(q_S^{\text{eq}})$，以几率之比衡量难度 |
| 几率 odds | $q/(1-q)$，达标与未达标之比 |
| logit | $\ln[q/(1-q)]$，几率的对数 |
| 分位数 | 使 $F(x)=u$ 的 $x$，记为 $Q(u)$ |
| 截断模型 | 假设 NOIP 池是 CSP-S 中成绩超过某条线 $\tau$ 的子集 |
| 等值（equating） | 把一套分数尺度映射到另一套尺度的方法 |
| 链接（linkage） | 把同一考生在 CSP-S 与 NOIP 的记录匹配起来 |
| IPW | 逆概率加权，用于修正非随机缺失/匹配 |
| Bootstrap | 重抽样估计不确定性的方法 |
| Delta 法 | 用一阶泰勒展开传播不确定性的方法 |
| LOYO | 留一年交叉验证（Leave-One-Year-Out） |
| AUC | ROC 曲线下面积，衡量二分类区分度 |
| 纯截断 | 只保留超过阈值 $\tau$ 的样本，阈值以下全部剔除 |

## 附录 D 数据来源与参考文献

### D.1 官方数据与规则

- [NOI 官网](https://www.noi.cn/)
- [NOI 系列活动简介](https://www.noi.cn/gynoi/jj/)
- [CSP-J/S 2026 第二轮评级规则](https://www.noi.cn/xw/2026-11-13/947969.shtml)
- [CCF 关于 NOIP 2026 报名的通知](https://www.noi.cn/xw/2026-10-12/938849.shtml)
- [NOIP 2026 参赛名额分配方案](https://www.noi.cn/xw/2026-10-12/938438.shtml)
- [NOIP 评奖规则](https://www.noi.cn/gynoi/tlgd/2024-11-26/834964.shtml)
- [NOIP 2026 广东赛区报名实施细则](https://www.noi.cn/gs/xw/gd/2026-11-04/945759.shtml)
- [CCF 中学生计算机程序设计能力等级评价标准（2019-09-21 重发版）](https://www.sohu.com/a/342526766_821349)
- [CCF 关于开展中学生计算机程序设计能力等级评价的通知（2019-08-26 初版）](https://www.sohu.com/a/336441924_120132276)

### D.2 方法参考文献

- Kolen, M. J., & Brennan, R. L. (2014). *Test Equating, Scaling, and Linking: Methods and Practices* (3rd ed.). Springer.
- Efron, B., & Tibshirani, R. J. (1993). *An Introduction to the Bootstrap*. Chapman & Hall.
- Fellegi, I. P., & Sunter, A. B. (1969). A theory for record linkage. *Journal of the American Statistical Association*, 64(328), 1183–1210.
- Holland, P. W., & Wainer, H. (Eds.). (1993). *Differential Item Functioning*. Lawrence Erlbaum.
- Little, R. J. A., & Rubin, D. B. (2019). *Statistical Analysis with Missing Data* (3rd ed.). Wiley.

## 附录 E 版本记录

| 版本 | 日期 | 变更 |
|---|---|---|
| v1.0 | 2026-11-14 | 初稿：共同参照框架、通过率/几率两种口径、年份模型、不确定性、实施手册 |