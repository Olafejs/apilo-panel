# Apilo Panel

Panel WWW do zarzadzania stanami magazynowymi produktow z Apilo.  
Projekt jest prosty: `Flask + SQLite + requests`.

## Kluczowe funkcje
- logowanie do panelu,
- synchronizacja produktow z Apilo,
- szybka edycja stanow magazynowych,
- raport sprzedazy,
- sugestie stanow na podstawie historii sprzedazy,
- podglad wartosci magazynu.

## Szybki start

### macOS
1. Otworz `Terminal`.
2. Wejdz do folderu projektu:

```bash
cd "/sciezka/do/apilo-panel"
```

3. Uruchom:

```bash
bash start.sh
```

4. Otworz w przegladarce:

```text
http://127.0.0.1:5000
```

Skrypt sam:
- utworzy `.venv`, jesli go nie ma,
- zainstaluje zaleznosci,
- utworzy `.env`, jesli go nie ma,
- uruchomi aplikacje,
- sprobuje automatycznie otworzyc domyslna przegladarke.

### Windows (PowerShell)
1. Otworz `PowerShell`.
2. Wejdz do folderu projektu:

```powershell
cd "C:\sciezka\do\apilo-panel"
```

3. Wklej po kolei:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe app.py
```

4. Otworz w przegladarce:

```text
http://127.0.0.1:5000
```

Skrypt sprobuje automatycznie otworzyc domyslna przegladarke.

### Linux
1. Otworz terminal.
2. Wejdz do folderu projektu:

```bash
cd "/sciezka/do/apilo-panel"
```

3. Uruchom:

```bash
bash start.sh
```

4. Otworz w przegladarce:

```text
http://127.0.0.1:5000
```

### Docker Compose
1. Wejdz do folderu projektu:

```bash
cd "/sciezka/do/apilo-panel"
```

2. Zbuduj i uruchom kontener:

```bash
docker compose up -d --build
```

Build i runtime kontenera w tym repo uzywaja sieci hosta, bo na tym serwerze zwykly Docker `bridge` nie ma stabilnego wyjscia do PyPI i API Apilo, mimo ze host ma internet.

3. Otworz w przegladarce:

```text
http://127.0.0.1:5080
```

Poniewaz kontener dziala z `network_mode: host`, aplikacja nasluchuje bezposrednio na porcie hosta `5080`.

4. Dane runtime sa zapisywane lokalnie w:
   - `data/db`
   - `data/logs`
   - `data/thumbs`

Zatrzymanie:

```bash
docker compose down
```

Jesli chcesz zbudowac obraz recznie poza Compose, uzyj:

```bash
docker build --network host -t apilo-panel .
```

## Konfiguracja

Przykladowy `.env`:

```ini
FLASK_SECRET_KEY=change-me
APP_PASSWORD=
APILO_DB_PATH=apilo.sqlite3

APILO_BASE_URL=
APILO_CLIENT_ID=
APILO_CLIENT_SECRET=
APP_SETUP_TOKEN=

THUMB_TTL_SECONDS=86400
REFRESH_INTERVAL_SECONDS=600
SESSION_COOKIE_SECURE=0
SESSION_LIFETIME_MINUTES=480
LOGIN_RATE_LIMIT_MAX_ATTEMPTS=5
LOGIN_RATE_LIMIT_WINDOW_SECONDS=600
TRUST_X_FORWARDED_FOR=0
```

Jesli konfigurujesz API z poziomu panelu (`Ustawienia -> Dane API Apilo`), zostaw pola `APILO_*` puste w `.env`.  
Wartosci z `.env` maja priorytet nad ustawieniami zapisanymi w panelu.

## Bezpieczenstwo pierwszego uruchomienia
- Najbezpieczniej ustawic `APP_PASSWORD` od razu w `.env`.
- Jesli `APP_PASSWORD` jest puste, pierwsze ustawienie hasla bez `APP_SETUP_TOKEN` jest dozwolone tylko przez `localhost`.
- Jesli chcesz ustawic haslo zdalnie, ustaw tymczasowo `APP_SETUP_TOKEN`, uzyj go na ekranie pierwszej konfiguracji, a potem usun z `.env`.

## Skad wziac dane API Apilo
1. Zaloguj sie do swojego panelu Apilo i wejdz na:

```text
https://twoje-konto.apilo.com/admin/rest-api/
```

2. Przejdz do zakladki **Klucze API Apilo** i kliknij **Nowa aplikacja REST API**.
3. Po utworzeniu aplikacji przepisz do panelu:
   - `Adres API (endpoint)`
   - `Client ID`
   - `Client Secret`
   - `Kod autoryzacji`

4. Pole `Waznosc do` jest informacyjne i nie wymaga osobnego pola w panelu.

## ID cennika w Apilo (dla cen Allegro)
- To unikalny identyfikator cennika w Apilo.
- Panel uzywa go do pobrania cen Allegro przez:
  `GET /rest/api/warehouse/price-calculated/?price=<ID>`.
- Pobrane ceny sa potem uzywane do porownania ceny sklepowej z cena Allegro oraz do wyceny magazynu.
- Ten identyfikator znajdziesz na liscie cennikow w Apilo albo przez:
  `GET /rest/api/warehouse/price/`.
