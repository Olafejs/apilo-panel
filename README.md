# Apilo Panel

Nowoczesny panel WWW do zarządzania stanami magazynowymi produktów z Apilo.  
Projekt jest lekki, szybki i prosty w utrzymaniu: `Flask + SQLite + requests`.

## Dlaczego ten projekt?
- Jeden proces, jedna baza, zero zbędnej infrastruktury.
- Konfiguracja API i tokenów bezpośrednio z poziomu panelu.
- Raporty sprzedaży i sugestie stanów magazynowych w tym samym miejscu.
- Działa na macOS, Linux i Windows (Python 3.10+).

## Kluczowe funkcje
- Logowanie i first-run setup hasła.
- Synchronizacja produktów z Apilo.
- Edycja stanów magazynowych z natychmiastowym push do API.
- Raport sprzedaży (z eksportem CSV).
- Sugestie stanów na podstawie historii sprzedaży.
- Podgląd wartości magazynu (cena sklepowa / Allegro).
- Cache miniatur produktów (`static/thumbs`).

## Technologie
- Python 3.10+
- Flask
- SQLite
- `requests`
- `python-dotenv`

## Szybki start

### Linux / macOS
1. Sprawdź wersję Pythona (wymagany Python 3.10+):
```bash
python3 --version
```

2. Utwórz i aktywuj virtualenv:
```bash
python3 -m venv .venv
source .venv/bin/activate
```

3. Zainstaluj zależności:
```bash
python -m pip install -r requirements.txt
```

4. Utwórz lokalną konfigurację:
```bash
cp .env.example .env
```

5. Uruchom aplikację:
```bash
python app.py
```

### Windows (PowerShell)
1. Sprawdź wersję Pythona (wymagany Python 3.10+):
```powershell
py -3 --version
```

2. Utwórz i aktywuj virtualenv:
```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Jeśli aktywacja jest blokowana polityką systemu:
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

3. Zainstaluj zależności:
```powershell
python -m pip install -r requirements.txt
```

4. Utwórz lokalną konfigurację:
```powershell
Copy-Item .env.example .env
```

5. Uruchom aplikację:
```powershell
python app.py
```

### Otwórz panel
- [http://127.0.0.1:5000](http://127.0.0.1:5000)

### Najczęstszy błąd: `No module named venv`
Jeśli widzisz:
`/Library/.../Python 2.7 ... No module named venv`,
to znaczy, że komenda `python` wskazuje na Python 2.7.

Użyj:
```bash
python3 -m venv .venv
source .venv/bin/activate
```

## Konfiguracja
Przykładowy `.env`:

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

Jeśli konfigurujesz API z poziomu panelu (`Ustawienia -> Dane API Apilo`), zostaw pola `APILO_*` puste w `.env`.  
Wartości z `.env` mają priorytet nad ustawieniami zapisanymi w panelu.

Najważniejsze zmienne:
- `FLASK_SECRET_KEY`: klucz sesji Flask (ustaw silny i unikalny w środowisku produkcyjnym).
- `APP_PASSWORD`: gdy puste, hasło jest ustawiane przy pierwszym wejściu do panelu.
- `APILO_BASE_URL`, `APILO_CLIENT_ID`, `APILO_CLIENT_SECRET`: dane dostępu do API.
- `APILO_DB_PATH`: ścieżka lokalnej bazy SQLite.
- `THUMB_TTL_SECONDS`: czas życia cache miniatur.
- `REFRESH_INTERVAL_SECONDS`: interwał automatycznego odświeżania w tle.

## Skąd wziąć dane API Apilo
1. Zaloguj się do swojego panelu Apilo i wejdź na:
```text
https://twoje-konto.apilo.com/admin/rest-api/
```
Każde konto ma własny adres (subdomenę), np. `twoje-konto.apilo.com`.

2. Przejdź do zakładki **Klucze API Apilo** i kliknij **Nowa aplikacja REST API**.

3. Po utworzeniu aplikacji przepisz dane do panelu:
- `Adres API (endpoint)` z Apilo -> pole `Adres API (endpoint)` w ustawieniach.
- `Client ID` z Apilo -> pole `Client ID`.
- `Client Secret` z Apilo -> pole `Client Secret`.
- `Kod autoryzacji` z Apilo -> pole `Kod autoryzacji`.

4. Pole `Ważność do` z Apilo jest informacyjne (pokazuje termin ważności kodu/tokenu) i nie wymaga osobnego pola w panelu.

## Deployment (opcjonalnie)
Repo zawiera szablon usługi `systemd`: `apilo-panel.service`.

1. Dostosuj `WorkingDirectory` i `ExecStart`.
2. Skopiuj plik:
```bash
sudo cp apilo-panel.service /etc/systemd/system/apilo-panel.service
```
3. Włącz usługę:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now apilo-panel
sudo systemctl status apilo-panel
```

## Struktura projektu
```text
.
├── app.py                  # Flask app, routing, CSRF, background refresh
├── apilo.py                # Klient API Apilo i obsługa tokenów
├── db.py                   # Schemat SQLite i operacje na danych
├── templates/              # Widoki Jinja2
├── static/style.css        # Style UI
├── apilo-panel.service     # Opcjonalny szablon usługi Linux/systemd
├── swagger.json            # Referencja endpointów Apilo
├── VERSION                 # Aktualna wersja aplikacji
├── CHANGELOG.md            # Historia zmian
└── docs/                   # Dodatkowa dokumentacja
```

## Bezpieczeństwo
- Nie commituj: `.env`, `apilo.sqlite3`, `logs/`, `static/thumbs/`.
- Nie loguj sekretów API i haseł.
- Każdy `POST` jest zabezpieczony tokenem CSRF.

## Wersjonowanie
- Aktualna wersja: `VERSION`
- Historia zmian: `CHANGELOG.md`
- Workflow wydania: `docs/VERSIONING.md`

## Współpraca
Zasady współpracy i PR znajdziesz w [CONTRIBUTING.md](CONTRIBUTING.md).

## Licencja
Projekt jest udostępniony na licencji MIT. Zobacz [LICENSE](LICENSE).
