# Apilo Panel

Prosty panel WWW do pracy na stanach magazynowych z Apilo.

Stack:
- `Flask`
- `SQLite`
- `requests`

## Start lokalny

macOS / Linux:

```bash
bash start.sh
```

Windows PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe app.py
```

Panel lokalnie:

```text
http://127.0.0.1:5000
```

## Docker

```bash
docker compose up -d --build
```

Panel w Dockerze:

```text
http://127.0.0.1:5080
```

Kontener startuje przez `gunicorn` i wystawia healthcheck pod `http://127.0.0.1:5080/healthz`.

W tym repo build i runtime kontenera uzywaja sieci hosta, bo na tym serwerze zwykly Docker `bridge` nie ma stabilnego wyjscia do internetu i API Apilo.

Dane runtime:
- `data/db`
- `data/logs`
- `data/thumbs`

Zatrzymanie:

```bash
docker compose down
```

## Pierwsze uruchomienie

- najlepiej ustaw `APP_PASSWORD` od razu w `.env`
- jesli `APP_PASSWORD` jest puste, pierwsze ustawienie hasla bez `APP_SETUP_TOKEN` zadziala tylko lokalnie
- jesli chcesz ustawic haslo zdalnie, tymczasowo ustaw `APP_SETUP_TOKEN`
- sekrety w SQLite sa szyfrowane; jesli nie podasz `SETTINGS_ENCRYPTION_KEY`, aplikacja utworzy lokalny plik klucza obok bazy (`settings.key`)
- przy backupie lub przenoszeniu instancji zachowaj razem baze i plik `settings.key`, albo ustaw stale `SETTINGS_ENCRYPTION_KEY` w `.env`

## Konfiguracja Apilo

W panelu wejdz w `Ustawienia` i uzupelnij:
- `Adres API`
- `Client ID`
- `Client Secret`
- `Kod autoryzacji`

Te dane znajdziesz w Apilo pod:

```text
https://twoje-konto.apilo.com/admin/rest-api/
```

Jesli konfigurujesz API z panelu, zostaw pola `APILO_*` puste w `.env`.

## Najwazniejsze zmienne `.env`

```ini
FLASK_SECRET_KEY=change-me
SETTINGS_ENCRYPTION_KEY=
SETTINGS_ENCRYPTION_KEY_PATH=
APP_PASSWORD=
APP_SETUP_TOKEN=
APILO_DB_PATH=apilo.sqlite3

APILO_BASE_URL=
APILO_CLIENT_ID=
APILO_CLIENT_SECRET=

THUMB_TTL_SECONDS=86400
REFRESH_INTERVAL_SECONDS=600
SALES_CACHE_REFRESH_INTERVAL_SECONDS=1800
SALES_YEAR_REFRESH_INTERVAL_SECONDS=21600
APP_THREADS=4
APP_TIMEOUT=120
SESSION_COOKIE_SECURE=0
```
