# Jak Uruchomic Apilo Panel

To jest najprostsza instrukcja dla osoby, ktora pierwszy raz uruchamia projekt.

## Najprostszy start na macOS

1. Rozpakuj projekt.
2. Otworz `Terminal`.
3. Wejdz do folderu projektu:

```bash
cd "/sciezka/do/apilo-panel"
```

4. Wklej to:

```bash
xattr -dr com.apple.quarantine . && ./Start-Apilo.command
```

5. Poczekaj, az projekt:
   - utworzy `.venv`,
   - zainstaluje zaleznosci,
   - uruchomi panel,
   - otworzy przegladarke.

Panel otworzy sie pod adresem:

```text
http://127.0.0.1:5000
```

## Jesli chcesz potem uruchamiac aplikacje z ikona

Po pierwszym uruchomieniu mozesz zbudowac lokalna aplikacje:

```bash
./Build-Start-Apilo-App.command
open "Start Apilo.app"
```

Potem mozesz uruchamiac `Start Apilo.app` dwuklikiem.

## Jesli pojawi sie blad "Permission denied"

Wklej:

```bash
chmod +x Start-Apilo.command Build-Start-Apilo-App.command
```

Potem uruchom ponownie:

```bash
xattr -dr com.apple.quarantine . && ./Start-Apilo.command
```

## Windows (najprostszy start)

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

## Linux (najprostszy start)

1. Otworz terminal.
2. Wejdz do folderu projektu:

```bash
cd "/sciezka/do/apilo-panel"
```

3. Wklej po kolei:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
python app.py
```

4. Otworz w przegladarce:

```text
http://127.0.0.1:5000
```
