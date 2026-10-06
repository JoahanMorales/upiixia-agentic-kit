# TASKS · "DocTalk": chat with any PDF, with cited answers (24 h hackathon, 3 humans × 2 agents)

## HACK-001 · Setup: FastAPI + React skeleton, deps, smoke
- **Type:** setup
- **Priority:** P0
- **Estimate:** 40 min
- **Paths:** pyproject.toml, uv.lock, app/main.py, app/config.py, web/package.json, web/package-lock.json, web/vite.config.ts, web/src/App.tsx, web/src/lib/
- **Depends on:** None
- **Verify:** bash .uak/bin/smoke

## HACK-002 · Contract: schemas, fixtures and mocks for upload, ask and citations
- **Type:** contract
- **Priority:** P0
- **Estimate:** 30 min
- **Paths:** app/schemas/, app/fixtures/
- **Depends on:** None
- **Verify:** uv run pytest -q app/tests/test_schemas.py

## HACK-003 · Spike: embeddings + vector store on 3 sample PDFs (recorded fallback)
- **Type:** spike
- **Priority:** P0
- **Estimate:** 30 min
- **Paths:** spikes/rag/
- **Depends on:** None
- **Verify:** uv run python spikes/rag/spike.py --check

## HACK-004 · Design lock: 3 directions, DESIGN.md, tokens
- **Type:** contract
- **Priority:** P0
- **Estimate:** 45 min
- **Paths:** web/DESIGN.md, web/src/index.css, web/public/design-lock/
- **Depends on:** None
- **Verify:** test -s web/DESIGN.md

## HACK-005 · Upload API: PDF → chunks → index (mock store until HACK-003)
- **Type:** feature
- **Priority:** P0
- **Estimate:** 60 min
- **Paths:** app/routers/upload.py, app/services/ingest.py, app/tests/test_upload.py
- **Depends on:** None
- **Uses contract:** HACK-002, HACK-003
- **Verify:** uv run pytest -q app/tests/test_upload.py

## HACK-006 · Ask API: answer with citations, schema-validated LLM output
- **Type:** feature
- **Priority:** P0
- **Estimate:** 60 min
- **Paths:** app/routers/ask.py, app/services/answer.py, app/tests/test_ask.py
- **Depends on:** None
- **Uses contract:** HACK-002
- **Verify:** uv run pytest -q app/tests/test_ask.py

## HACK-007 · Chat UI: the wow moment — answer streams in with clickable citations
- **Type:** feature
- **Priority:** P0
- **Estimate:** 60 min
- **Paths:** web/src/features/chat/
- **Depends on:** None
- **Uses contract:** HACK-002, HACK-004
- **Verify:** npm --prefix web run build

## HACK-008 · Real retrieval: swap the mock store for the spike's vector store
- **Type:** integration
- **Priority:** P0
- **Estimate:** 45 min
- **Paths:** app/services/store.py, app/tests/test_store.py
- **Depends on:** HACK-003, HACK-005
- **Verify:** uv run pytest -q app/tests/test_store.py

## HACK-009 · Eval: 20 questions with known answers, report citation accuracy
- **Type:** feature
- **Priority:** P1
- **Estimate:** 45 min
- **Paths:** evals/
- **Depends on:** HACK-008, HACK-006
- **Verify:** uv run python evals/run.py --min-accuracy 0.7

## HACK-010 · Demo + submission: rehearsal, plan-B video, README
- **Type:** demo
- **Priority:** P0
- **Estimate:** 60 min
- **Paths:** README.md, docs/demo/
- **Depends on:** HACK-007, HACK-008
- **Freeze-Allowed:** yes
- **Verify:** test -s docs/demo/script.md
