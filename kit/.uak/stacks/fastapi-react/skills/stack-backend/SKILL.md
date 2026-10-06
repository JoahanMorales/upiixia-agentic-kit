---
name: stack-backend
description: Backend conventions for the FastAPI + React stack (app/, Python 3.12, FastAPI, uv, pytest). Use when creating or changing endpoints, services, schemas, tests or Python dependencies.
---
# Backend · FastAPI + React stack
Initial setup: `.uak/stacks/fastapi-react/STACK.md`. This file holds only the conventions for parallel work.

```text
app/main.py             # auto-discovers routers, serves web/dist; nobody edits it after setup
app/config.py           # settings from env (pydantic-settings); owner: setup
app/schemas/            # shared Pydantic contracts; single owner (contract task)
app/fixtures/           # labeled demo data
app/routers/<f>.py      # router = APIRouter(prefix="/api/<f>", tags=["<f>"])
app/services/<f>.py     # logic; external calls with timeout + mock fallback
app/tests/test_<f>.py   # TestClient: happy path + one error
```

| Rule | Why |
|---|---|
| Every route lives under `/api/...` | One prefix for the frontend; FastAPI serves the web at `/`. |
| A task reserves `app/routers/<f>.py, app/services/<f>.py, app/tests/test_<f>.py` (+ `web/src/features/<f>/`) | Disjoint claims. |
| Read schemas from `app/schemas/`; ask their owner for changes (`--kind request`) | One writer per contract. |
| External calls only in `services/`, with `httpx` and a `timeout=`; fall back to a mock on `DEMO_MODE=true` or failure | The demo survives a dead API. |
| Mocks carry `"demo_data": true` | Mocks are always labeled. |
| New deps: ask the owner of `pyproject.toml`/`uv.lock` | Auto-merge rejects lockfile changes. |
| Secrets come only from env via `app/config.py` | The pre-commit scanner blocks them. |

```bash
bash .uak/bin/q uv run pytest -q --tb=short -x app/tests/test_<f>.py
bash .uak/bin/q uv run ruff check app
uv run uvicorn app.main:app --reload --port "${UAK_PORT:-8000}"
```
