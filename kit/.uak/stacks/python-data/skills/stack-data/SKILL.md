---
name: stack-data
description: Conventions for the Python data / ML stack (package, analysis/<f>/run.py, reports/<f>/ CSVs, Streamlit pages, pytest). Use when writing an analysis, a model, a report README, a dashboard page or a test in this repo.
---
# Data / ML stack
Initial setup: `.uak/stacks/python-data/STACK.md`.

| Rule | Why (from a 10-day hackathon on the kit) |
|---|---|
| Every number in a README, memo, paper or deck is copied from a CSV in `reports/`; generate the README from the CSV when you can | 4 rejects were numbers that did not match their CSV |
| Raw data never leaves `data/raw/` (git-ignored): reports hold aggregates only, no row-level IDs | event rule: results may be shown, data may not |
| Label exploratory work: `exploratory`, `demo_data: true`, "transductive" when features were fit on all rows | reviewers rejected unlabeled claims |
| Validate out of sample (group k-fold by entity, season and park holdouts) and beat a null baseline on the same target | the rubric scored robustness; every model task reported skill vs baseline |
| Keep identifiers stable across environments (don't key on a label that shifts with the effect you measure) | a label that moved with altitude contaminated 3 tasks |
| Long runs: `--fast` while iterating; final numbers from the full run, stated as such | |
| One analysis = `analysis/<f>/run.py` + `reports/<f>/`; a dashboard page reads only `reports/` CSVs | pages stay fast and never touch raw data |
| New dependencies: ask the owner of `requirements.txt`/`pyproject.toml`; a conflicting extra goes in its own optional file | one extra needed an older scikit-learn |

```bash
bash .uak/bin/q python -m pytest -q --tb=short -x tests/test_<f>.py
python -m analysis.<f>.run --fast && git diff --stat reports/<f>/
```
