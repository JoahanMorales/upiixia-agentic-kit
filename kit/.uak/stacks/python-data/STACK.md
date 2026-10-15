# Stack · Python data / ML (package + analyses + Streamlit)

Setup for the first task and structure reference. Conventions for every task live in the `stack-data` skill.
Taken from a 10-day analytics hackathon run on the kit (4 Windows laptops, 32 tasks integrated): what worked is kept,
what cost reviews is a rule.

## Structure

```text
<pkg>/                     # the library: models, features, physics, io (one module per task)
  io.py · config.py        # data paths; owner: setup (worktrees read the main checkout's data/raw)
analysis/<f>/run.py        # one folder per analysis task: reads data, writes reports/<f>/ (aggregates only)
reports/<f>/               # CSV + README.md + figures; every number in a README comes from a CSV here
app/Home.py · app/pages/N_<f>.py   # Streamlit multipage: a page per task, auto-discovered
tests/test_<f>.py          # pytest on a small synthetic fixture (no raw data in CI)
data/raw/                  # git-ignored; never committed, never in reports
pyproject.toml · requirements.txt  # single owner (setup)
```

A task reserves `<pkg>/<f>.py, analysis/<f>/, reports/<f>/, tests/test_<f>.py` (+ `app/pages/N_<f>.py`).
Streamlit finds `app/pages/*.py` by itself, so no task edits `Home.py`.

## Setup (~5 min)

```bash
python -m venv .venv                     # in the MAIN checkout: the merge gate and every worktree use it
. .venv/bin/activate || . .venv/Scripts/activate   # Windows Git Bash: Scripts
python -m pip install -U pip pandas numpy scikit-learn pytest streamlit
python -m pip freeze > requirements.txt
mkdir -p <pkg> analysis reports app/pages tests data/raw && touch <pkg>/__init__.py
printf 'data/raw/\n*.parquet\n.venv/\n__pycache__/\nartifacts/\n' >> .gitignore
```

`<pkg>/config.py` resolves data from the main checkout, so a fresh worktree needs no copy:

```python
import os
import subprocess
from pathlib import Path


def main_checkout() -> Path:
    env = os.environ.get("UAK_MAIN_CHECKOUT")   # set by the uak merge gate
    if env:
        return Path(env)
    common = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                            capture_output=True, text=True, check=True).stdout.strip()
    return Path(common).parent


def data_path(*parts: str) -> Path:
    return main_checkout().joinpath("data", "raw", *parts)
```

## Product smoke

```bash
bash .uak/bin/uak init-smoke --command 'for p in .venv/Scripts/python .venv/bin/python "$UAK_MAIN_CHECKOUT/.venv/Scripts/python" "$UAK_MAIN_CHECKOUT/.venv/bin/python"; do [ -x "$p" ] && exec "$p" -m pytest -q --tb=short -x; done; exec python -m pytest -q --tb=short -x'
```

The merge gate runs it in a clean clone with the `.venv` of the worktree or the main checkout first on PATH.

## Run

| Mode | Command |
|---|---|
| An analysis | `python -m analysis.<f>.run` (add `--fast` for a sample; the final run without it) |
| Dashboard | `streamlit run app/Home.py --server.port $UAK_PORT` |
