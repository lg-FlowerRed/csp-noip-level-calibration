#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Native, offline local-calibration workbench. Numerical work stays off Tk."""
from __future__ import annotations

from collections import Counter
import math
from pathlib import Path
import queue
import sys
import threading

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except ImportError as exc:
    print(f"缺少 tkinter/Tcl-Tk，请安装包含 Tcl/Tk 组件的官方 Python。\n{exc}", file=sys.stderr)
    raise SystemExit(1)

try:
    import calc_rating_matched as model
except ImportError as exc:
    print(f"程序文件缺失：请保留 calc_rating_matched.py、rating_records.py、rating_local.py。\n{exc}", file=sys.stderr)
    raise SystemExit(1)

DATA_DIR = model.DATA_DIR
analyze_year = model.analyze_year

# Study-notebook visual system: observed evidence and model assumptions stay
# side by side. Colors identify grades, not "good/bad" results.
SURFACE = "#fcfcfb"
INK = "#243746"
MUTED = "#52657a"
GRID = "#d8e2ee"
GRADE_COLORS = {6: "#2a78d6", 7: "#eb6834"}  # palette validator: all checks pass


class MatchedRatingApp(tk.Tk):
    def __init__(self, data_dir=DATA_DIR):
        super().__init__()
        self.data_dir = Path(data_dir)
        self.title("CSP-S / NOIP  边界成绩标定")
        self.geometry("1200x850")
        self.minsize(940, 680)
        self._report = None
        self._cache = {}
        self._full_report_text = ""
        self._worker = None
        self._run_id = 0
        self._poll_id = None
        self._result_queue = queue.Queue()
        self._cancel_event = threading.Event()
        self._closed = False
        self._hover_points = []
        self._input_widgets = []
        self._progress_value = 0
        try:
            self.contests = model.load_contests(self.data_dir)
            self.years = model.available_years(self.contests)
            if not self.years:
                raise ValueError("没有同时具备两赛数据和全国参赛人数的年份。")
        except (OSError, ValueError) as exc:
            self.destroy()
            raise RuntimeError(f"数据读取失败：{exc}") from exc
        self._setup_style()
        self._build_ui()
        self._show_welcome()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<Return>", lambda event: self.calculate())

    def _setup_style(self):
        import tkinter.font as font
        for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
            font.nametofont(name).configure(family="Microsoft YaHei UI", size=10)
        style = ttk.Style(self)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("Title.TLabel", font=("Microsoft YaHei UI", 18, "bold"), foreground=INK)
        style.configure("Muted.TLabel", foreground=MUTED)
        style.configure("Strong.TButton", font=("Microsoft YaHei UI", 10, "bold"))
        style.configure("Treeview", rowheight=28, font=("Microsoft YaHei UI", 9))

    def _field(self, parent, label, variable, col, width=8, choices=None):
        ttk.Label(parent, text=label).grid(row=0, column=col, sticky="w", padx=(0, 4), pady=3)
        if choices:
            widget = ttk.Combobox(parent, textvariable=variable, values=choices, width=width, state="readonly")
            self._input_widgets.append((widget, "readonly"))
        else:
            widget = ttk.Entry(parent, textvariable=variable, width=width)
            self._input_widgets.append((widget, "normal"))
        widget.grid(row=0, column=col + 1, sticky="w", padx=(0, 18), pady=3)
        return widget

    def _build_ui(self):
        outer = ttk.Frame(self, padding=16)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="CSP-S / NOIP  边界成绩标定", style="Title.TLabel").pack(anchor="w")
        ttk.Label(outer, text="先看真实配对，再检验校正。全国统一等级线；不使用名额或省人数估算作分母。",
                  style="Muted.TLabel").pack(anchor="w", pady=(5, 12))
        inputs = ttk.LabelFrame(outer, text="同一年，两个等级", padding=10)
        inputs.pack(fill="x")
        self.year_var = tk.StringVar(value=str(model.default_year(self.contests)))
        self.qs6_var, self.qs7_var = tk.StringVar(value="20"), tk.StringVar(value="10")
        self.bootstrap_var, self.seed_var = tk.StringVar(value="1000"), tk.StringVar(value="2026")
        self.fuzzy_var = tk.BooleanVar(value=False)
        first = ttk.Frame(inputs); first.pack(fill="x")
        self._field(first, "年份", self.year_var, 0, choices=[str(y) for y in self.years])
        self._field(first, "CSP-S 6级比例（%）", self.qs6_var, 2)
        self._field(first, "CSP-S 7级比例（%）", self.qs7_var, 4)
        second = ttk.Frame(inputs); second.pack(fill="x", pady=(3, 0))
        self._field(second, "重抽次数", self.bootstrap_var, 0)
        self._field(second, "随机种子", self.seed_var, 2)
        extra = ttk.Checkbutton(second, text="附加模糊匹配敏感性（不进入主样本）", variable=self.fuzzy_var)
        extra.grid(row=0, column=4, sticky="w")
        self._input_widgets.append((extra, "normal"))
        ttk.Label(inputs, text="0次只跳过区间，仍进行回测；默认1000次。正式分析可能需要几分钟，可随时取消。",
                  style="Muted.TLabel").pack(anchor="w", pady=(5, 0))
        actions = ttk.Frame(outer); actions.pack(fill="x", pady=(10, 8))
        self.calculate_button = ttk.Button(actions, text="开始标定", style="Strong.TButton", command=self.calculate)
        self.calculate_button.pack(side="left")
        self.cancel_button = ttk.Button(actions, text="取消计算", command=self.cancel, state="disabled")
        self.cancel_button.pack(side="left", padx=6)
        self.reset_button = ttk.Button(actions, text="重置输入", command=self.reset)
        self.reset_button.pack(side="left")
        self.copy_button = ttk.Button(actions, text="复制完整报告", command=self.copy_result, state="disabled")
        self.copy_button.pack(side="left", padx=6)
        self.export_button = ttk.Button(actions, text="导出报告", command=self.export_result, state="disabled")
        self.export_button.pack(side="left")
        self.progress = ttk.Progressbar(actions, mode="indeterminate", length=110)
        self.progress.pack(side="right")
        self.status_var = tk.StringVar(value="就绪：只读使用本地数据")
        ttk.Label(outer, textvariable=self.status_var, style="Muted.TLabel", wraplength=1050).pack(anchor="w", pady=(0, 8))

        overview = ttk.Frame(outer); overview.pack(fill="x", pady=(0, 8))
        overview.columnconfigure(0, weight=1); overview.columnconfigure(1, weight=1)
        self.overview_vars = {}
        for col, k in enumerate((6, 7)):
            box = ttk.LabelFrame(overview, text=f"{k}级：已观测 / 模型校正", padding=8)
            box.grid(row=0, column=col, sticky="nsew", padx=(0, 8) if col == 0 else (0, 0))
            self.overview_vars[k] = tk.StringVar(value="尚未计算")
            ttk.Label(box, textvariable=self.overview_vars[k], foreground=INK, wraplength=490, justify="left").pack(anchor="w")

        self.notebook = ttk.Notebook(outer); self.notebook.pack(fill="both", expand=True)
        self.section_texts = {}
        for title in ("结论", "模型与验证", "敏感性", "数据与门槛", "方法与限制"):
            tab = ttk.Frame(self.notebook, padding=6)
            self.notebook.add(tab, text=title)
            self.section_texts[title] = self._make_text(tab)
        self.summary_text = self.section_texts["结论"]
        self.data_text = self.section_texts["数据与门槛"]
        self.chart_tab = ttk.Frame(self.notebook, padding=6)
        self.notebook.add(self.chart_tab, text="图形核对")
        chart_controls = ttk.Frame(self.chart_tab); chart_controls.pack(fill="x", pady=(0, 6))
        self.chart_mode_var = tk.StringVar(value="边界成绩配对")
        self.chart_level_var = tk.StringVar(value="6级")
        for variable, values in ((self.chart_mode_var, ("边界成绩配对", "缺失比例假设情景")),
                                 (self.chart_level_var, ("6级", "7级"))):
            widget = ttk.Combobox(chart_controls, textvariable=variable, values=values, state="readonly", width=20)
            widget.pack(side="left", padx=(0, 8))
            widget.bind("<<ComboboxSelected>>", lambda event: self._draw_chart())
        ttk.Label(chart_controls, text="悬停查看数值；完整数字见对应文字页", style="Muted.TLabel").pack(side="left")
        self.canvas = tk.Canvas(self.chart_tab, background=SURFACE, highlightthickness=1, highlightbackground=GRID)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda event: self._draw_chart())
        self.canvas.bind("<Motion>", self._on_hover)
        self.canvas.bind("<Leave>", lambda event: self.canvas.delete("hover"))
        self.chart_caption = tk.StringVar(value="")
        ttk.Label(self.chart_tab, textvariable=self.chart_caption, wraplength=1040, justify="left", style="Muted.TLabel").pack(anchor="w", pady=(5, 0))
        for variable in (self.year_var, self.qs6_var, self.qs7_var, self.bootstrap_var, self.seed_var, self.fuzzy_var):
            variable.trace_add("write", self._input_changed)

    def _make_text(self, parent):
        text = tk.Text(parent, wrap="word", font=("Microsoft YaHei UI", 10), background=SURFACE,
                       foreground=INK, borderwidth=0, padx=12, pady=10, spacing1=2, spacing3=4,
                       highlightthickness=1, highlightbackground=GRID, undo=False)
        scroll = ttk.Scrollbar(parent, orient="vertical", command=text.yview)
        scroll.pack(side="right", fill="y")
        text.configure(yscrollcommand=scroll.set)
        text.pack(fill="both", expand=True)
        text.tag_configure("heading", font=("Microsoft YaHei UI", 12, "bold"), spacing1=10, spacing3=5)
        text.tag_configure("note", foreground=MUTED)
        text.configure(state="disabled")
        return text

    def _set_text(self, widget, text):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        for i, line in enumerate(text.splitlines()):
            tag = "heading" if i == 0 or line.startswith(("6级 |", "7级 |")) else "note" if line.startswith(("提示", "风险", "以上重抽")) else ""
            widget.insert("end", line + "\n", (tag,) if tag else ())
        widget.configure(state="disabled")
        widget.yview_moveto(0)

    def _show_welcome(self):
        self._set_text(self.summary_text, "边界成绩标定\n\n输入同一年 CSP-S 的6级、7级累计比例，点击“开始标定”。\n\n可见基线和截断校正会分别展示；仅在回测和稳定性门槛通过时采用校正。\n\n缺少官方最低获奖线的年份仍可计算可见基线，不会猜测门槛或制造总体结论。")
        for key, widget in self.section_texts.items():
            if key != "结论":
                self._set_text(widget, "计算完成后显示。所有内容均可复制或导出。")
        self._draw_chart()

    def _input_changed(self, *args):
        if self._report is not None and self._worker is None:
            self.status_var.set("输入已改变：当前展示的仍是上一组设置，请重新标定。")

    def _read_inputs(self):
        year = int(self.year_var.get())
        q6, q7 = float(self.qs6_var.get()), float(self.qs7_var.get())
        if not all(math.isfinite(q) and 0 < q < 100 for q in (q6, q7)) or q7 >= q6:
            raise ValueError("比例须满足 0 < 7级 < 6级 < 100（输入单位为%）。")
        reps, seed = int(self.bootstrap_var.get()), int(self.seed_var.get())
        if not 0 <= reps <= 10000 or seed < 0:
            raise ValueError("重抽次数为0～10000的整数，随机种子为非负整数。")
        if year not in self.years:
            raise ValueError("年份没有同年两场赛事数据。")
        return year, {6: q6 / 100, 7: q7 / 100}, reps, seed, "fuzzy" if self.fuzzy_var.get() else "strict"

    def _busy(self, busy):
        for widget, normal_state in self._input_widgets:
            widget.configure(state="disabled" if busy else normal_state)
        for widget in (self.calculate_button, self.reset_button):
            widget.configure(state="disabled" if busy else "normal")
        for widget in (self.copy_button, self.export_button):
            widget.configure(state="normal" if not busy and self._report else "disabled")
        self.cancel_button.configure(state="normal" if busy else "disabled")
        if busy:
            self.progress.start(20)
        else:
            self.progress.stop()

    def calculate(self):
        # A finished thread may still have a result waiting in the queue.
        if self._worker is not None or self._closed:
            return
        try:
            model.require_dependencies()
            year, qs, reps, seed, match_mode = self._read_inputs()
            fingerprint = model.dataset_fingerprint(self.data_dir)
        except (ValueError, RuntimeError, OSError) as exc:
            messagebox.showerror("无法开始", str(exc), parent=self)
            return
        key = (fingerprint, year, qs[6], qs[7], reps, seed, match_mode)
        if key in self._cache:
            self._render_report(self._cache[key])
            self.status_var.set("已载入相同数据与设置的缓存报告")
            return
        self._run_id += 1
        run_id = self._run_id
        self._cancel_event = threading.Event()
        self._busy(True)
        self.status_var.set("正在核对官方门槛…")
        self._worker = threading.Thread(target=self._worker_main, args=(run_id, key, year, qs, reps, seed, match_mode), daemon=True)
        self._worker.start()
        self._poll_id = self.after(80, lambda: self._poll_worker(run_id))

    def _worker_main(self, run_id, key, year, qs, reps, seed, match_mode):
        try:
            report = analyze_year(self.data_dir, year, qs, reps, seed, match_mode,
                                  lambda text: self._result_queue.put(("progress", run_id, text)),
                                  self._cancel_event.is_set)
            if self._cancel_event.is_set():
                self._result_queue.put(("cancelled", run_id, "计算已取消，未替换上一份报告。"))
            else:
                self._result_queue.put(("result", run_id, key, report))
        except BaseException as exc:
            kind = "cancelled" if self._cancel_event.is_set() or type(exc).__name__ == "AnalysisCancelled" else "error"
            self._result_queue.put((kind, run_id, str(exc)))

    def _poll_worker(self, run_id):
        if self._closed or run_id != self._run_id:
            return
        finished = False
        try:
            while True:
                try:
                    event = self._result_queue.get_nowait()
                except queue.Empty:
                    break
                if event[1] != run_id:
                    continue
                if event[0] == "progress":
                    self.status_var.set(event[2])
                elif event[0] == "result":
                    self._cache[event[2]] = event[3]
                    if len(self._cache) > 6:
                        self._cache.pop(next(iter(self._cache)))
                    self._render_report(event[3])
                    finished = True
                elif event[0] in ("error", "cancelled"):
                    self.status_var.set("已取消" if event[0] == "cancelled" else "计算失败；上一份报告未替换")
                    if event[0] == "error":
                        messagebox.showerror("计算失败", event[2], parent=self)
                    finished = True
        except Exception as exc:
            finished = True
            self.status_var.set("报告显示失败")
            messagebox.showerror("显示失败", str(exc), parent=self)
        if finished:
            self._worker = None
            self._poll_id = None
            self._busy(False)
        else:
            self._poll_id = self.after(80, lambda: self._poll_worker(run_id))

    def cancel(self):
        if self._worker is not None:
            self._cancel_event.set()
            self.cancel_button.configure(state="disabled")
            self.status_var.set("正在取消：等待当前一次拟合结束…")

    def _render_report(self, report):
        self._report = report
        self._full_report_text = model.report_to_text(report)
        for name, text in report.sections.items():
            self._set_text(self.section_texts[name], text)
        for k, variable in self.overview_vars.items():
            level = report.levels[k]
            if not level.available:
                variable.set(level.reason)
                continue
            base = model.fmt_pct(level.baseline.q) if level.baseline.complete else "全国比例仅有计数范围"
            corrected = model.fmt_pct(level.corrected.q) if level.corrected and level.corrected.complete else "未能完整计数/未拟合"
            adopted = "模型条件推荐" if level.selected_method == "corrected" else "未采用校正；仅供可见基线参考"
            variable.set(f"可见基线  {base}   /   校正候选  {corrected}\n{adopted}")
        self.status_var.set(f"{report.year}年完成；详见每级采用理由、回测误差与缺失敏感性")
        self._draw_chart()
        if self._worker is None:
            self._busy(False)

    def _draw_chart(self):
        if not hasattr(self, "canvas"):
            return
        c = self.canvas; c.delete("all"); self._hover_points = []
        w, h = max(c.winfo_width(), 700), max(c.winfo_height(), 320)
        if self._report is None:
            c.create_text(w / 2, h / 2, text="计算后查看边界配对与缺失假设情景", fill=MUTED,
                          font=("Microsoft YaHei UI", 11))
            self.chart_caption.set("图表数值与文字报告来自同一份计算结果。")
            return
        if self.chart_mode_var.get() == "缺失比例假设情景":
            self._draw_scenarios(w, h)
        else:
            self._draw_pairs(int(self.chart_level_var.get()[0]), w, h)

    def _axes(self, w, h, xmin, xmax, ymin, ymax, xlabel, ylabel, percent_x=False, percent_y=False):
        c = self.canvas
        left, right, top, bottom = 68, w - 35, 64, h - 46
        def xp(value): return left + (value - xmin) / (xmax - xmin) * (right - left)
        def yp(value): return bottom - (value - ymin) / (ymax - ymin) * (bottom - top)
        for i in range(6):
            xv = xmin + (xmax - xmin) * i / 5
            yv = ymin + (ymax - ymin) * i / 5
            x, y = xp(xv), yp(yv)
            c.create_line(x, top, x, bottom, fill=GRID)
            c.create_line(left, y, right, y, fill=GRID)
            c.create_text(x, bottom + 12, text=f"{xv * 100:.0f}%" if percent_x else f"{xv:.0f}", fill=MUTED, font=("Microsoft YaHei UI", 8))
            c.create_text(left - 8, y, text=f"{yv * 100:.0f}%" if percent_y else f"{yv:.0f}", anchor="e", fill=MUTED, font=("Microsoft YaHei UI", 8))
        c.create_line(left, top, left, bottom, right, bottom, fill=MUTED)
        c.create_text((left + right) / 2, h - 9, text=xlabel, fill=INK, font=("Microsoft YaHei UI", 9))
        c.create_text(16, (top + bottom) / 2, text=ylabel, angle=90, fill=INK, font=("Microsoft YaHei UI", 9))
        return xp, yp, (left, right, top, bottom)

    def _draw_pairs(self, k, w, h):
        c = self.canvas; level = self._report.levels[k]
        if not level.available or not level.local_points:
            c.create_text(w / 2, h / 2, text=level.reason or "边界样本不足", fill=MUTED)
            return
        xs = [p[0] for p in level.local_points]
        ys = [p[1] for p in level.local_points]
        spread = max(10, max(xs) - min(xs))
        ymax = max(100, math.ceil(max(ys) / 50) * 50)
        xp, yp, box = self._axes(w, h, min(xs) - spread * .05, max(xs) + spread * .05, 0, ymax,
                                 "CSP-S 分数", "NOIP 分数")
        left, right, top, bottom = box
        c.create_text(left, 14, text=f"{k}级边界附近的真实成绩配对", anchor="w", fill=INK, font=("Microsoft YaHei UI", 11, "bold"))
        c.create_text(left, 39, text="灰点：严格配对   虚线：可见基线   彩色线：截断校正候选（不代表已采用）",
                      anchor="w", fill=MUTED, font=("Microsoft YaHei UI", 9))
        for (x, y), count in Counter(tuple(point) for point in level.local_points).items():
            xx, yy = xp(x), yp(y)
            radius = min(7, 4 + math.log2(count) / 2)
            c.create_oval(xx - radius, yy - radius, xx + radius, yy + radius, fill="#b2bfce", outline=SURFACE, width=1)
            self._hover_points.append((xx, yy, f"CSP-S {model.fmt_score(x)}分\nNOIP {model.fmt_score(y)}分\n重合配对 {count}人"))
        base_y = yp(level.baseline.score)
        c.create_line(left, base_y, right, base_y, fill=INK, dash=(6, 4), width=2)
        x0 = xp(level.csp_score)
        c.create_line(x0, top, x0, bottom, fill=MUTED, dash=(2, 4))
        c.create_rectangle(x0 - 5, base_y - 5, x0 + 5, base_y + 5, fill=INK, outline=SURFACE, width=2)
        self._hover_points.append((x0, base_y, "可见基线\n" + model.describe_tail(level.baseline)))
        if level.model_curve:
            coords = [v for x, y in level.model_curve for v in (xp(x), yp(y))]
            c.create_line(*coords, width=2, fill=GRADE_COLORS[k])  # no smoothing that changes fitted geometry
        if level.corrected:
            yy = yp(level.corrected.score)
            c.create_oval(x0 - 6, yy - 6, x0 + 6, yy + 6, fill=GRADE_COLORS[k], outline=SURFACE, width=2)
            self._hover_points.append((x0, yy, "校正候选\n" + model.describe_tail(level.corrected)))
        self.chart_caption.set(f"可见基线 {model.fmt_score(level.baseline.score)}分；校正候选 {model.fmt_score(level.corrected.score) if level.corrected else '—'}分。"
                               f"结论：{model.METHODS[level.selected_method]}。配对中低于全国可计数线的真实分数没有被额外删去。")

    def _draw_scenarios(self, w, h):
        c = self.canvas
        xp, yp, (left, right, top, bottom) = self._axes(w, h, 0, .5, 0, 1,
            "假设的低分缺失比例 π（不是实测）", "候选线对应全国比例", True, True)
        c.create_text(left, 14, text="未知尾部会怎样改变结果？", anchor="w", fill=INK, font=("Microsoft YaHei UI", 11, "bold"))
        for col, k in enumerate((6, 7)):
            color = GRADE_COLORS[k]
            lx = left + col * 150
            c.create_line(lx, 39, lx + 25, 39, fill=color, width=2, dash=() if k == 6 else (5, 3))
            c.create_text(lx + 32, 39, text=f"{k}级假设情景", anchor="w", fill=INK, font=("Microsoft YaHei UI", 9))
            points = [row for row in self._report.levels[k].scenarios if row['q'] is not None]
            if not points:
                continue
            coords = [v for row in points for v in (xp(row['assumed_missing_mass']), yp(row['q']))]
            if len(coords) > 2:
                c.create_line(*coords, fill=color, width=2, dash=() if k == 6 else (5, 3))
            for row in points:
                x, y = xp(row['assumed_missing_mass']), yp(row['q'])
                shape = c.create_oval if k == 6 else c.create_rectangle
                shape(x - 5, y - 5, x + 5, y + 5, fill=color, outline=SURFACE, width=2)
                self._hover_points.append((x, y, f"{k}级，假设π={model.fmt_pct(row['assumed_missing_mass'])}\n"
                                           f"{model.fmt_score(row['score'])}分 / {model.fmt_pct(row['q'])}\n非实测、非置信区间"))
            last = points[-1]
            c.create_text(xp(last['assumed_missing_mass']) + 10, yp(last['q']) + (-9 if k == 6 else 9),
                          text=f"{k}级 {model.fmt_pct(last['q'])}", anchor="w", fill=INK, font=("Microsoft YaHei UI", 9))
        self.chart_caption.set("π由人为设定，不是全国未获奖率或未匹配率。π≥50%时中位数进入未知区，不画出虚构结果。"
                               "情景使用窗口内经验分布，π=0可能与局部线性基线不同；详见“敏感性”。")

    def _on_hover(self, event):
        c = self.canvas; c.delete("hover")
        if not self._hover_points:
            return
        point = min(self._hover_points, key=lambda p: (p[0] - event.x) ** 2 + (p[1] - event.y) ** 2)
        if (point[0] - event.x) ** 2 + (point[1] - event.y) ** 2 > 144:
            return
        x = min(event.x + 14, max(10, c.winfo_width() - 280))
        y = min(event.y + 14, max(10, c.winfo_height() - 90))
        text = c.create_text(x + 8, y + 6, text=point[2], anchor="nw", fill=INK,
                             font=("Microsoft YaHei UI", 9), tags="hover", width=260)
        bounds = c.bbox(text)
        rect = c.create_rectangle(bounds[0] - 6, bounds[1] - 4, bounds[2] + 6, bounds[3] + 4,
                                  fill="white", outline=GRID, tags="hover")
        c.tag_lower(rect, text)

    def copy_result(self):
        if self._report is not None:
            self.clipboard_clear(); self.clipboard_append(self._full_report_text)
            self.status_var.set("完整报告已复制（包含方法、门槛、验证与敏感性）")

    def export_result(self):
        if self._report is None:
            return
        path = filedialog.asksaveasfilename(parent=self, title="导出完整标定报告",
            initialfile=f"NOIP局部标定_{self._report.year}.txt", defaultextension=".txt",
            filetypes=(("中文文本报告", "*.txt"), ("结构化JSON", "*.json")))
        if not path:
            return
        try:
            text = model.report_to_json(self._report) if Path(path).suffix.lower() == ".json" else self._full_report_text
            Path(path).write_text(text, encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("导出失败", str(exc), parent=self)
            return
        self.status_var.set(f"已导出：{Path(path).name}")

    def reset(self):
        if self._worker is not None:
            return
        self._report = None; self._full_report_text = ""
        self.year_var.set(str(model.default_year(self.contests)))
        self.qs6_var.set("20"); self.qs7_var.set("10")
        self.bootstrap_var.set("1000"); self.seed_var.set("2026"); self.fuzzy_var.set(False)
        for variable in self.overview_vars.values():
            variable.set("尚未计算")
        self.status_var.set("已重置输入；尚未重新计算")
        self._show_welcome(); self._busy(False)

    def _on_close(self):
        self._closed = True
        self._cancel_event.set()
        if self._poll_id is not None:
            self.after_cancel(self._poll_id)
        self.destroy()


def main():
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        pass
    try:
        model.require_dependencies()
        app = MatchedRatingApp()
    except (RuntimeError, tk.TclError) as exc:
        print(f"无法启动：{exc}", file=sys.stderr)
        return 1
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
