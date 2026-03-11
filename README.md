# Apilo Panel

Lekki panel WWW do pracy na stanach magazynowych z Apilo.

Najważniejsze funkcje:
- podgląd i filtrowanie produktów,
- synchronizacja z Apilo i status auto-sync,
- raport sprzedaży z eksportem CSV,
- alerty niskich stanów,
- historia zmian i audyt operacji,
- szyfrowanie sekretów zapisanych w SQLite.

Stack:
- `Flask`
- `SQLite`
- `requests`
- `gunicorn`

## Szybki start

Docker:

```bash
docker compose up -d --build
```

Panel:

```text
http://127.0.0.1:5080
```

Local:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python app.py
```

Panel lokalnie:

```text
http://127.0.0.1:5000
```

Healthcheck:

```text
http://127.0.0.1:5080/healthz
```

## Pierwsze uruchomienie

- ustaw `APP_PASSWORD` w `.env`, jeśli chcesz pominąć ekran pierwszego hasła,
- jeśli `APP_PASSWORD` jest puste, pierwsze ustawienie hasła bez `APP_SETUP_TOKEN` jest dozwolone tylko lokalnie,
- jeśli chcesz wykonać pierwszy setup zdalnie, ustaw tymczasowo `APP_SETUP_TOKEN`,
- jeśli nie podasz `SETTINGS_ENCRYPTION_KEY`, aplikacja utworzy lokalny plik `settings.key` obok bazy.

Przy backupie albo migracji instancji zachowaj razem:
- bazę SQLite,
- plik `settings.key`,
- katalog `data/thumbs`, jeśli chcesz zachować cache miniaturek.

## Konfiguracja Apilo

W panelu przejdź do `Ustawienia` i uzupełnij:
- `Adres API`
- `Client ID`
- `Client Secret`
- `Kod autoryzacji`

Jeśli konfigurujesz API z panelu, zostaw pola `APILO_*` puste w `.env`.
Wartości z `.env` mają priorytet nad ustawieniami zapisanymi w panelu.

## Docker

Repo domyślnie używa `network_mode: host`, bo na tej instancji zwykły Docker `bridge` nie miał stabilnego wyjścia do internetu i API Apilo.

Dane runtime:
- `data/db`
- `data/logs`
- `data/thumbs`

Zatrzymanie:

```bash
docker compose down
```

## Testy

Lokalnie:

```bash
pip install -r requirements-dev.txt
pytest -q
```

W Dockerze:

```bash
docker exec apilo-panel python -m pip install --no-cache-dir -r /app/requirements-dev.txt
docker exec apilo-panel pytest -q
```

## Ważne zmienne `.env`

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
THUMB_DOWNLOAD_TIMEOUT_SECONDS=10
THUMB_MAX_DOWNLOAD_BYTES=2000000

REFRESH_INTERVAL_SECONDS=600
SALES_CACHE_REFRESH_INTERVAL_SECONDS=1800
SALES_YEAR_REFRESH_INTERVAL_SECONDS=21600

SESSION_COOKIE_SECURE=0
SESSION_LIFETIME_MINUTES=480
LOGIN_RATE_LIMIT_MAX_ATTEMPTS=5
LOGIN_RATE_LIMIT_WINDOW_SECONDS=600
TRUST_X_FORWARDED_FOR=0
```

## Struktura

- `app.py` - entrypoint Flask i trasy,
- `app_auth.py` - auth, CSRF, helpery bezpieczeństwa,
- `app_sync.py` - runtime syncu i harmonogram,
- `app_reporting.py` - raport sprzedaży,
- `app_alerts.py` - alerty niskich stanów,
- `app_admin.py` - audit i snapshoty ustawień,
- `db.py` - SQLite i trwałość danych,
- `apilo.py` - klient API Apilo.
