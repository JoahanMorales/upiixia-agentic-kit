# Stack · Django (+ pytest-django)

Setup for the first task and structure reference. Conventions: the `stack-django` skill.

## Structure

```text
config/settings.py · config/urls.py   # owner: setup; urls.py includes every app that has urls.py (below)
<f>/                                  # one Django app per task: models, views, urls.py, templates/<f>/, tests.py
<f>/migrations/                       # the merge gate sends migrations to a human (shared schema)
pyproject.toml · uv.lock              # single owner (setup)
```
A task reserves its app folder `<f>/`. Model changes create migrations, which a human merges: keep model tasks few
and early (wave 1), and views/templates tasks after them.

## Setup (~5 min)

```bash
uv init --bare --name site --python 3.12 --pin-python .
uv add django && uv add --dev pytest pytest-django ruff
uv run django-admin startproject config .
printf '[tool.pytest.ini_options]\nDJANGO_SETTINGS_MODULE = "config.settings"\naddopts = "-q --tb=short"\n' >> pyproject.toml
```

`config/urls.py`, so adding an app never edits it:

```python
from importlib import util

from django.apps import apps
from django.contrib import admin
from django.urls import include, path

urlpatterns = [path("admin/", admin.site.urls)]
for app in apps.get_app_configs():
    if app.name.startswith("django.") or util.find_spec(f"{app.name}.urls") is None:
        continue
    urlpatterns.append(path(f"{app.label}/", include(f"{app.name}.urls")))
```
New apps still go in `INSTALLED_APPS` (owner: setup): batch them in the setup task from the plan.

## Product smoke

```bash
bash .uak/bin/uak init-smoke --command "uv run python manage.py check && uv run python manage.py makemigrations --check --dry-run && uv run pytest"
```

## Run
`uv run python manage.py runserver 127.0.0.1:$UAK_PORT`
