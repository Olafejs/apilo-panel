#!/bin/bash

set -u

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR" || exit 1

echo "== Apilo Panel =="
echo "Folder projektu: $PROJECT_DIR"
echo

find_python() {
  if command -v python3 >/dev/null 2>&1; then
    command -v python3
    return 0
  fi
  if command -v python >/dev/null 2>&1; then
    command -v python
    return 0
  fi
  return 1
}

PYTHON_BIN="$(find_python)"
if [ -z "${PYTHON_BIN:-}" ]; then
  echo "Nie znaleziono Pythona."
  echo "Zainstaluj Python 3.10+ i uruchom plik ponownie."
  read -r -p "Nacisnij Enter, aby zamknac..."
  exit 1
fi

if ! "$PYTHON_BIN" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'; then
  echo "Wykryty Python jest za stary: $("$PYTHON_BIN" --version 2>&1)"
  echo "Wymagany jest Python 3.10 lub nowszy."
  read -r -p "Nacisnij Enter, aby zamknac..."
  exit 1
fi

if [ ! -x ".venv/bin/python" ]; then
  echo "Tworze srodowisko .venv..."
  if ! "$PYTHON_BIN" -m venv .venv; then
    echo "Nie udalo sie utworzyc .venv."
    read -r -p "Nacisnij Enter, aby zamknac..."
    exit 1
  fi
fi

VENV_PYTHON="$PROJECT_DIR/.venv/bin/python"

if [ ! -f ".env" ] && [ -f ".env.example" ]; then
  echo "Tworze lokalny plik .env na podstawie .env.example..."
  cp .env.example .env
fi

REQ_HASH_FILE=".venv/.requirements.sha1"
if [ -f "requirements.txt" ]; then
  CURRENT_HASH="$(shasum requirements.txt | awk '{print $1}')"
  STORED_HASH=""
  if [ -f "$REQ_HASH_FILE" ]; then
    STORED_HASH="$(cat "$REQ_HASH_FILE")"
  fi
  if [ ! -x ".venv/bin/pip" ] || [ "$CURRENT_HASH" != "$STORED_HASH" ]; then
    echo "Instaluje lub aktualizuje zaleznosci..."
    if ! "$VENV_PYTHON" -m pip install --upgrade pip; then
      echo "Nie udalo sie zaktualizowac pip."
      read -r -p "Nacisnij Enter, aby zamknac..."
      exit 1
    fi
    if ! "$VENV_PYTHON" -m pip install -r requirements.txt; then
      echo "Nie udalo sie zainstalowac zaleznosci."
      read -r -p "Nacisnij Enter, aby zamknac..."
      exit 1
    fi
    printf "%s" "$CURRENT_HASH" > "$REQ_HASH_FILE"
  fi
fi

echo
echo "Uruchamiam panel na: http://127.0.0.1:5000"
echo "Aby zatrzymac, wcisnij Ctrl+C w tym oknie."
echo

( sleep 2; open "http://127.0.0.1:5000" >/dev/null 2>&1 ) &

"$VENV_PYTHON" app.py
EXIT_CODE=$?

echo
echo "Proces zakonczyl sie z kodem: $EXIT_CODE"
read -r -p "Nacisnij Enter, aby zamknac..."
exit "$EXIT_CODE"
