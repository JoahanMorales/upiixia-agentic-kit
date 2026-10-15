---
name: stack-go
description: Conventions for the Go HTTP service stack (internal/<f> packages, init() registry, go test). Use when adding a handler, service, package or test in this repo.
---
# Go stack
Setup: `.uak/stacks/go/STACK.md`.

| Rule | Why |
|---|---|
| One task = one package `internal/<f>/` that registers its routes with `httpx.Register` in `init()` | disjoint claims; main never changes |
| Go 1.22+ patterns: `"GET /api/<f>/{id}"`, read with `r.PathValue("id")` | no router dependency |
| Table-driven tests with `httptest` in `<f>_test.go` | reviewers run `go test ./internal/<f>/` |
| External calls with `context.WithTimeout` and a labeled fallback (`"demo_data": true`) | the demo survives a dead API |
| New modules: ask the owner of `go.mod`; never commit `go.sum` from a feature task | lockfiles go to the human queue |

```bash
bash .uak/bin/q go test ./internal/<f>/ && go vet ./internal/<f>/
```
