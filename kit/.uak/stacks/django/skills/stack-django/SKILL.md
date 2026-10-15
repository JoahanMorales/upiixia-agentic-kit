---
name: stack-django
description: Conventions for the Django stack (one app per task, auto-included urls, pytest-django, migrations through a human). Use when adding an app, model, view, template, admin or test in this repo.
---
# Django stack
Setup: `.uak/stacks/django/STACK.md`.

| Rule | Why |
|---|---|
| One task = one app folder `<f>/` with its own `urls.py`, `templates/<f>/` and `tests.py` | disjoint claims; `config/urls.py` includes it by itself |
| Migrations are shared schema: the merge gate sends them to a human. Generate them once per model task, never edit old ones | two branches with migrations collide |
| Settings belong to the setup owner; read config from env (`os.environ`) with safe defaults | one writer, secrets out of git |
| Cross-app access only through the other app's public functions or models, never its views | contracts stay small |
| Tests with `pytest-django` (`@pytest.mark.django_db`), one happy path and one error per view | reviewers run them |

```bash
bash .uak/bin/q uv run pytest <f>/tests.py && uv run python manage.py makemigrations --check --dry-run
```
