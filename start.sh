#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# Für einen Linux-/Proxmox-Dienst ohne grafische Serveroberfläche.
export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
export JARVIS_RUNTIME="${JARVIS_RUNTIME:-auto}"
export JARVIS_OPEN="${JARVIS_OPEN:-0}"

if ! command -v python3 >/dev/null 2>&1; then
  printf 'JARVIS benötigt Python 3. Bitte die vorhandene Python-Installation prüfen.\n' >&2
  exit 1
fi

exec python3 server.py
