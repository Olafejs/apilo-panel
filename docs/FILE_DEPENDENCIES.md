# File Inventory and Dependencies

## Core runtime flow

`app.py` -> imports `apilo.py` and `db.py` -> renders files from `templates/` -> serves CSS from `static/style.css`.

External runtime dependencies:
- Python 3.10+
- Flask
- python-dotenv
- requests
- SQLite (stdlib `sqlite3`)

## File-by-file map

| File | Required for app run | Purpose | Depends on | Used by |
|---|---|---|---|---|
| `.env.example` | No (template only) | Example environment variables for first setup | None | Developer/operator |
| `.gitignore` | No | Keeps local secrets/data/cache out of VCS | Git | Developer workflow |
| `LICENSE` | No (legal) | Open-source license terms for repository distribution | None | Users/contributors |
| `CONTRIBUTING.md` | No (docs) | Contribution and PR workflow | Manual updates | Contributors |
| `VERSION` | Yes | Current app version shown in UI footer | File read in `app.py` | `app.py` |
| `CHANGELOG.md` | No (ops/docs) | Human change history per release | Manual updates | Developer/operator |
| `README.md` | No (docs) | Setup, run, and usage instructions | Manual updates | Developer/operator |
| `requirements.txt` | Yes for install | Python package lock list for this app | pip | Environment setup |
| `app.py` | Yes | Flask app entrypoint, routes, CSRF, background refresh, rendering | `apilo.py`, `db.py`, Flask, dotenv, requests | Process start (`python app.py`) |
| `apilo.py` | Yes | API client, token refresh, pagination for Apilo endpoints | `requests`, `db.py` (`get_tokens`, `save_tokens`) | `app.py` |
| `db.py` | Yes | SQLite schema, migrations, queries, settings/tokens/cache persistence | `sqlite3`, `datetime` | `app.py`, `apilo.py` |
| `swagger.json` | No (reference) | API schema reference for Apilo endpoints | None | Developer/operator |
| `apilo-panel.service` | Optional | systemd unit template for Linux service mode | systemd | Operator |
| `docs/VERSIONING.md` | No (docs) | Versioning and release workflow | Git workflow | Developer/operator |
| `docs/FILE_DEPENDENCIES.md` | No (docs) | This dependency and file map | Repository state | Developer/operator |
| `static/style.css` | Yes (UI styling) | Shared styles for all Jinja templates | Browser CSS | `templates/*.html` |
| `templates/index.html` | Yes | Main product list view and actions | Jinja context from `app.py` | Route `/` |
| `templates/settings.html` | Yes | API/SMTP/password/suggestion/inventory settings UI | Jinja context from `app.py` | Route `/settings` |
| `templates/login.html` | Yes | Login form UI | Jinja + CSRF token | Route `/login` |
| `templates/setup_password.html` | Yes | First-run password setup UI | Jinja + CSRF token | Route `/setup-password` |
| `templates/sales_report.html` | Yes | Sales report and CSV export UI | Jinja context from `app.py` | Route `/sales-report` |

## Generated/ephemeral paths (not tracked)

- `.env` - local secrets/config.
- `.venv/` - local virtual environment.
- `apilo.sqlite3` - local app database.
- `logs/` - runtime logs (`logs/app.log`).
- `static/thumbs/` - thumbnail cache.
- `__pycache__/`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/` - local build/cache artifacts.
