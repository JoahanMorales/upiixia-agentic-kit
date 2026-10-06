# Stack · FastAPI + React

Setup for the first task (HACK-001) and structure reference. Day-to-day conventions live in the `stack-backend` and `stack-frontend` skills: setup is read once, conventions on every task.

Check first that event rules allow prior boilerplate; if not, run these steps after the official start (prior code may be restricted, see .uak/PROJECT.md).

## Structure

```text
app/                       # FastAPI backend (skill stack-backend)
  main.py                  # auto-discovers routers, serves web/dist; nobody edits it after setup
  config.py · schemas/ · fixtures/ · routers/<f>.py · services/<f>.py · tests/test_<f>.py
web/                       # Vite + React + TS + Tailwind v4 + Motion frontend (skill stack-frontend)
  DESIGN.md · src/App.tsx · src/index.css · src/lib/api.ts · src/features/<f>/index.tsx
pyproject.toml / uv.lock · web/package.json / web/package-lock.json   # single owner (setup)
```

A vertical task reserves `app/routers/<f>.py, app/services/<f>.py, app/tests/test_<f>.py, web/src/features/<f>/`: disjoint Paths allow simultaneous claims.

## Backend setup (~5 min)

```bash
uv init --bare --name app --python 3.12 --pin-python .   # pyproject.toml only; --app in uv 0.12 creates src/ and a build
uv add fastapi "uvicorn[standard]" pydantic-settings httpx
uv add --dev pytest ruff httpx2 playwright   # httpx2 avoids the TestClient warning; playwright for webapp-testing
mkdir -p app/routers app/services app/schemas app/fixtures app/tests
touch app/__init__.py app/routers/__init__.py app/services/__init__.py app/schemas/__init__.py
cat >> pyproject.toml <<'TOML'

[tool.pytest.ini_options]
testpaths = ["app/tests"]
pythonpath = ["."]
addopts = "-q --tb=short"
TOML
cat > app/.uak/tests/test_health.py <<'PY'
from fastapi.testclient import TestClient

from app.main import app


def test_health() -> None:
    assert TestClient(app).get("/api/health").json() == {"status": "ok"}
PY
# + app/main.py (below)
```

### app/main.py

```python
import importlib
import pkgutil
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app import routers

app = FastAPI(title="Hack")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


# `routers` (not `app.routers`): the `app` variable shadows the package of the same name.
for module in pkgutil.iter_modules(routers.__path__):
    router = getattr(importlib.import_module(f"{routers.__name__}.{module.name}"), "router", None)
    if router is not None:
        app.include_router(router)

# The frontend build is mounted last: /api/* always wins over static files.
WEB_DIST = Path(__file__).resolve().parent.parent / "web" / "dist"
if WEB_DIST.is_dir():
    app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="web")
```

Adding an endpoint = creating `app/routers/<f>.py`; `main.py` never becomes a conflict point.

## Frontend setup (~5 min)

```bash
CI=1 npm create vite@latest web -- --template react-ts --no-interactive
npm --prefix web install --no-audit --no-fund --loglevel=error
npm --prefix web install --no-audit --no-fund --loglevel=error tailwindcss @tailwindcss/vite motion @phosphor-icons/react @fontsource-variable/geist
rm -rf web/src/App.css web/src/assets web/public/vite.svg
mkdir -p web/src/features web/src/lib
sed -i.bak 's#<title>.*</title>#<title>hacknation</title>#; /vite.svg/d' web/index.html && rm web/index.html.bak
# + the five files below; then web/DESIGN.md with the design-taste-frontend skill
```

### web/vite.config.ts

```ts
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// /api goes to FastAPI in dev; in the demo FastAPI serves web/dist (one process).
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { proxy: { "/api": "http://127.0.0.1:8000" } },
});
```

### web/src/index.css

```css
@import "tailwindcss";
@import "@fontsource-variable/geist";

@theme {
  --font-sans: "Geist Variable", ui-sans-serif, system-ui, sans-serif;
}
```

### web/src/lib/api.ts

```ts
// The only door to the backend: every route lives under /api.
export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return (await response.json()) as T;
}
```

### web/src/App.tsx

```tsx
import type { ComponentType } from "react";

// Each feature is web/src/features/<name>/index.tsx with `export default` and `order`.
// Adding a feature = creating its folder; App.tsx never becomes a conflict point.
type FeatureModule = { default: ComponentType; order?: number };

const features = Object.entries(
  import.meta.glob<FeatureModule>("./features/*/index.tsx", { eager: true }),
)
  .map(([path, module]) => ({ path, ...module }))
  .sort((a, b) => (a.order ?? 100) - (b.order ?? 100));

export default function App() {
  return (
    <main className="mx-auto min-h-[100dvh] max-w-7xl px-4 py-12 font-sans text-zinc-900 dark:text-zinc-100">
      {features.map(({ path, default: Feature }) => (
        <Feature key={path} />
      ))}
    </main>
  );
}
```

### web/src/main.tsx

```tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App";
import "./index.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
```

## Product smoke

```bash
uv run playwright install chromium   # once per machine (~100 MB), for webapp-testing
bash .uak/bin/uak init-smoke --command "uv run ruff check app && uv run pytest && npm --prefix web ci --prefer-offline --no-audit --no-fund --loglevel=error && npm --prefix web run lint && npm --prefix web run build"
```

`uak merge` re-runs this smoke in a clean clone, hence `npm ci`: a merge must test the whole product, not just Python.

## Run

| Mode | Command |
|---|---|
| Development | `uv run uvicorn app.main:app --reload --port 8000` + `npm --prefix web run dev` (open :5173) |
| Demo (one process) | `npm --prefix web run build && uv run uvicorn app.main:app --port 8000` (open :8000) |
