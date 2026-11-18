#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
export PATH="$HOME/.local/bin:/usr/local/bin:$PATH"

if ! command -v python3 >/dev/null 2>&1; then
  printf 'Python 3 wurde nicht gefunden.\n' >&2
  exit 1
fi

# Sensible Zugangsdaten sollen nicht in einer allgemein lesbaren Datei landen.
umask 077
if [ ! -f .env ]; then
  cp .env.example .env
  printf 'Lokale Konfiguration .env wurde aus der Vorlage angelegt.\n'
fi

# Nur prüfen, nicht die bestehende Hermes-Installation verändern.
configured_hermes="${HERMES_CMD:-}"
if [ -z "$configured_hermes" ]; then
  while IFS='=' read -r key value; do
    if [ "${key#\#}" = "$key" ] && [ "$key" = "HERMES_CMD" ]; then
      configured_hermes="${value%\"}"; configured_hermes="${configured_hermes#\"}"
      configured_hermes="${configured_hermes%\'}"; configured_hermes="${configured_hermes#\'}"
      break
    fi
  done < .env
fi

if ! command -v hermes >/dev/null 2>&1 && [ -z "$configured_hermes" ]; then
  printf 'Hermes Agent wurde nicht gefunden. Bitte die vorhandene Installation oder HERMES_CMD prüfen.\n' >&2
  exit 1
fi

chmod +x start.sh install.sh
printf '\nJARVIS-Kommandozentrale wird mit dem bestehenden Hermes-Profil gestartet.\n'
printf 'Lokaler Zugang: http://127.0.0.1:8730\n\n'
exec ./start.sh
