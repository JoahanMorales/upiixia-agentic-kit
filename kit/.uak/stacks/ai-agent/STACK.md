# Stack · AI agent: MCP server + evals (Python)

Setup for the first task and structure reference. Conventions: the `stack-ai-agent` skill (+ `mcp-builder` with `--skills ai`).

## Structure

```text
server/main.py              # owner: setup; FastMCP server that registers every tools/<f>.py
server/tools/<f>.py         # one tool module per task: def register(mcp) adds its tools
evals/cases/<f>.jsonl       # its eval cases: {"input": ..., "expect": ...} one per line
evals/run.py                # owner: setup; runs every case file, prints pass rate, exit 1 under the threshold
tests/test_<f>.py           # unit tests of the tool functions (no model calls)
pyproject.toml · uv.lock    # single owner (setup)
```
A task reserves `server/tools/<f>.py, evals/cases/<f>.jsonl, tests/test_<f>.py`.

## Setup (~5 min)

```bash
uv init --bare --name agent --python 3.12 --pin-python .
uv add "mcp[cli]" httpx && uv add --dev pytest ruff
mkdir -p server/tools evals/cases tests && touch server/__init__.py server/tools/__init__.py
```

`server/main.py`:

```python
import importlib
import pkgutil

from mcp.server.fastmcp import FastMCP

from server import tools

mcp = FastMCP("agent")
for module in pkgutil.iter_modules(tools.__path__):
    getattr(importlib.import_module(f"{tools.__name__}.{module.name}"), "register")(mcp)

if __name__ == "__main__":
    mcp.run()
```

## Product smoke

```bash
bash .uak/bin/uak init-smoke --command "uv run ruff check . && uv run pytest -q && uv run python evals/run.py --offline"
```
`--offline` runs the deterministic cases (tool functions on fixtures); model-graded cases run by hand, with keys, never in the gate.

## Run
`uv run mcp dev server/main.py` (inspector) · `uv run python server/main.py` (stdio)
