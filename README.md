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

## Konfiguracja

Przykladowy `.env`:

```ini
FLASK_SECRET_KEY=change-me
APP_PASSWORD=
APILO_DB_PATH=apilo.sqlite3

APILO_BASE_URL=
APILO_CLIENT_ID=
APILO_CLIENT_SECRET=

THUMB_TTL_SECONDS=86400
REFRESH_INTERVAL_SECONDS=600
```

Jesli konfigurujesz API z poziomu panelu (`Ustawienia -> Dane API Apilo`), zostaw pola `APILO_*` puste w `.env`.  
Wartosci z `.env` maja priorytet nad ustawieniami zapisanymi w panelu.

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
