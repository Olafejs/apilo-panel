# Contributing

Dziękuję za chęć współtworzenia projektu.

## Zasady ogólne
- Twórz małe, konkretne zmiany.
- Używaj czytelnych commitów (`feat:`, `fix:`, `chore:`).
- Zachowuj zgodność z istniejącym stylem kodu (Python 3.10, PEP8, 4 spacje).
- Nie commituj danych lokalnych i sekretów (`.env`, bazy SQLite, logi, cache).

## Setup developerski
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python app.py
```

## Pull Request checklist
- Opisz problem i uzasadnij zmianę.
- Dodaj kroki weryfikacji (co kliknąć / uruchomić).
- Uzupełnij `CHANGELOG.md` (sekcja `Unreleased`) dla zmian user-facing.
- Jeśli zmiana dotyczy konfiguracji, opisz wpływ na `.env` i migrację danych.

## Standard jakości
- Route Flask powinny być cienkie, logika biznesowa w `apilo.py` / `db.py`.
- Obsługuj błędy bez ujawniania sekretów.
- Preferuj funkcje możliwe do testowania w izolacji.
