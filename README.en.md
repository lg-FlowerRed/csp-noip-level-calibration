# English summary

**CSP-S / NOIP Boundary Calibration** is an independent, offline research tool for estimating the typical NOIP performance of students near a CSP-S grade boundary.

It is **not an official CCF/NOI project**. Results are statistical estimates, not grading rules, eligibility decisions, or predictions about individuals.

## Key ideas

- Strict same-person linkage across CSP-S and NOIP.
- Local median calibration around a CSP-S percentile boundary.
- Provincial award-threshold truncation models (bounded normal and Student-t).
- School-group cross-validation and independent masking audits.
- Separate reporting of observed-award baselines, model-based candidates, resampling intervals, and missing-tail sensitivity.

## Quick start

```bash
py -m pip install -r requirements.txt
py calc_rating_matched.py --year 2025 --q-s-6 15 --q-s-7 7.5 --bootstrap 1000
```

Windows GUI:

```bash
py calc_rating_gui.py
```

The public repository intentionally excludes identifiable award lists (`data/raw.txt`) and upstream school-alias data. See [README.md](README.md) and [data/README.md](data/README.md) for setup, methodology, data format, limitations, and licensing.

## Contributors

- [lg-FlowerRed](https://github.com/lg-FlowerRed) — project initiator, research direction, data collection, review, and maintenance.
- **Claude Code** — implementation, statistical verification, tests, UI, and documentation.
- **GPT** — early methodology discussion and analytical assistance.

GPT has no personal GitHub account to which commits can be mapped, so it is credited explicitly rather than impersonating an unrelated bot account.
