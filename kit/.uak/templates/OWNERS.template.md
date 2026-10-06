# Shared-file owners

One writer per shared file. Others ask the owner with `uak msg ID --kind request`. Patterns are relative, with no spaces; directories end in `/`.
An owner is not a prerequisite for everyone: consumers work on published contracts and mocks. To transfer ownership, open a PR to main.

| Pattern | Owner task |
|---|---|
| pyproject.toml | HACK-001 |
| uv.lock | HACK-001 |
| package.json | HACK-001 |
| package-lock.json | HACK-001 |
| web/package.json | HACK-001 |
| web/package-lock.json | HACK-001 |
| app/main.py | HACK-001 |
| web/src/App.tsx | HACK-001 |
| app/schemas/ | HACK-002 |
| web/DESIGN.md | HACK-002 |
| .github/workflows/ | HACK-001 |
| .uak/PROJECT.md | HACK-001 |

Delete rows for technologies you don't use. `/uak-plan` creates HACK-001 (setup) and HACK-002 (contract).
