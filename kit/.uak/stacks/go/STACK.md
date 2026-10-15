# Stack · Go HTTP service

Setup for the first task and structure reference. Conventions: the `stack-go` skill.

## Structure

```text
cmd/server/main.go           # owner: setup; mounts every registered feature, nobody edits it after
internal/httpx/registry.go   # owner: setup; features call Register in init()
internal/<f>/                # one package per task: handler.go, service.go, <f>_test.go
go.mod · go.sum              # single owner (setup); go.sum changes go to the human queue
```
A task reserves `internal/<f>/`. `cmd/server/main.go` imports features with blank imports listed by setup.

## Setup (~3 min)

```bash
go mod init example.com/app && mkdir -p cmd/server internal/httpx
```

`internal/httpx/registry.go`:

```go
package httpx

import "net/http"

var routes = map[string]http.HandlerFunc{}

// Register is called from each feature's init(); main mounts them all.
func Register(pattern string, h http.HandlerFunc) { routes[pattern] = h }

func Mux() *http.ServeMux {
	mux := http.NewServeMux()
	for p, h := range routes {
		mux.HandleFunc(p, h)
	}
	return mux
}
```

`cmd/server/main.go` serves `httpx.Mux()` on `":" + os.Getenv("UAK_PORT")` (default 8080) and blank-imports each
`internal/<f>` package named in the plan.

## Product smoke

```bash
bash .uak/bin/uak init-smoke --command "go vet ./... && go test ./..."
```

## Run
`UAK_PORT=$UAK_PORT go run ./cmd/server`
