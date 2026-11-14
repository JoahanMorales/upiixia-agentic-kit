---
name: stack-python-stdlib
description: Conventions for a plain Python web app on the standard library (http.server, app/<f>.py modules, unittest). Use when adding a route, module, test or deploy file in this repo.
---
# Plain Python stack
Setup: `.uak/stacks/python-stdlib/STACK.md`.

| Rule | Why |
|---|---|
| One task = one module `app/<f>.py` that registers its routes; `server.py` never changes after setup | disjoint claims |
| Run it as `python3 -m app.server`; imports are absolute (`from app.<f> import ...`) | the same command works in a worktree, the gate and the image |
| The server listens on `0.0.0.0` and reads `PORT` (then `UAK_PORT`) | the host sends traffic to `$PORT` |
| Tests import the real modules and start the real server on a free port at least once | a fake store hid an ImportError until deploy (QA round C) |
| Deploy files come from `uak deploy --write`, never by hand | a hand-written Dockerfile copied a folder the repo did not have |

```bash
bash .uak/bin/q python3 -m unittest discover -s tests -t .
```
