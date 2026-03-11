# GitHub Public Release Notes

## Suggested repository description

Lekki panel WWW do pracy na stanach magazynowych z Apilo.

## Suggested topics

- `apilo`
- `flask`
- `inventory`
- `warehouse`
- `sqlite`
- `allegro`
- `docker`
- `python`

## Suggested release title

`v1.0.37`

## Suggested release notes

```md
## Apilo Panel v1.0.37

Public release of the project with refreshed repository metadata and contributor-facing GitHub setup.

### Included

- modularized application structure (`app_auth`, `app_sync`, `app_reporting`, `app_alerts`, `app_admin`)
- Docker and `gunicorn` production runtime
- encrypted secret storage in SQLite
- sync status, sales report, CSV export, alerts, and audit history
- pytest suite and GitHub Actions CI
- refreshed `README`, `CONTRIBUTING`, `SECURITY`, issue templates, and release config

### Validation

- `33 passed`
- `/healthz` returns `ok`
- API connectivity smoke test passes
```
