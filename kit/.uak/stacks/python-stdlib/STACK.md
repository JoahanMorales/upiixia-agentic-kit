# Stack · Plain Python web app (standard library, no framework)

Setup for the first task and structure reference. Conventions: the `stack-python-stdlib` skill.
For a small API or a demo with no dependencies: `http.server` serves JSON and the static page. Need routing, validation
or a database layer? Use `fastapi-react` instead.

## Structure

```text
app/server.py          # owner: setup; the HTTP handler; mounts each feature's routes from ROUTES, nobody edits it after
app/routes.py          # owner: setup; ROUTES = {} that features fill with register("GET", "/api/<f>", fn)
app/<f>.py             # one module per task: logic + its register(...) calls
web/                   # optional static files (index.html, app.js) served by server.py
tests/test_<f>.py      # unittest or pytest, no network
requirements.txt       # only if a task really needs a package; single owner (setup)
```
A task reserves `app/<f>.py, tests/test_<f>.py`. `server.py` imports every `app/<f>` named in the plan once.

## Setup (~3 min)

```bash
mkdir -p app tests && touch app/__init__.py tests/__init__.py
printf '__pycache__/\n.venv/\n' >> .gitignore
```

`app/server.py` must end with:

```python
def main():
    port = int(os.environ.get("PORT") or os.environ.get("UAK_PORT") or 8000)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
```
Serve `GET /api/health` → `{"ok": true}`: the deploy health check uses it.

## Product smoke

```bash
bash .uak/bin/uak init-smoke --command "python3 -m unittest discover -s tests -t ."
```

## Run
`UAK_PORT=$UAK_PORT python3 -m app.server`

## Deploy
`bash .uak/bin/uak deploy --write` recognises `server.py` or `<pkg>/server.py` (a file that imports `http.server`,
`wsgiref` or `socketserver` and has `if __name__ == "__main__"`), and writes a Dockerfile (`COPY . .`, installs
`requirements.txt` only when it exists, `CMD ["python3", "-m", "app.server"]`) and `render.yaml`. Never hand-write them.
