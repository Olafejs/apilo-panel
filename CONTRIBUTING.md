# Contributing

Projekt jest mały, więc zmiany powinny też być małe i konkretne.

## Zasady

- nie commituj lokalnych danych, sekretów i cache (`.env`, `data/`, logi, SQLite),
- trzymaj route Flask cienkie, logikę przenoś do modułów pomocniczych,
- nie psuj kompatybilności istniejących ustawień i migracji danych bez wyraźnego powodu,
- dodawaj testy tam, gdzie zmiana dotyka logiki albo bezpieczeństwa.

## Setup developerski

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
cp .env.example .env
pytest -q
python app.py
```

## Checklista przed push

- `python3 -m py_compile app.py apilo.py db.py`
- `pytest -q`
- jeśli zmiana dotyczy deployu: `docker compose up -d --build`
- jeśli zmiana jest user-facing: uzupełnij `CHANGELOG.md`
- jeśli zmiana dotyczy konfiguracji: uzupełnij `README.md` i `.env.example`

## Wersjonowanie

- `VERSION` pokazuje bieżącą wersję aplikacji,
- `CHANGELOG.md` opisuje zmiany per release,
- tag Git powinien odpowiadać wersji z `VERSION`.
