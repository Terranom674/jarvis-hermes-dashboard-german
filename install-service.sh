#!/usr/bin/env bash
# Einmalige Einrichtung des vorhandenen deutschen JARVIS-Dashboards als Benutzerdienst.
# Keine Aktualisierung oder Installation von Hermes, keine GitHub Actions.
set -euo pipefail
cd "$(dirname "$0")"
umask 077

if [ ! -f .env ]; then
  cp .env.example .env
fi

# Die IP ist ausschließlich die bekannte LAN-Adresse des Jarvis-LXC 102.
if ! grep -q '^JARVIS_BIND=' .env; then
  printf '\nJARVIS_BIND=192.168.51.102\n' >> .env
fi
if ! grep -q '^JARVIS_PUBLIC_URL=' .env; then
  printf 'JARVIS_PUBLIC_URL=http://192.168.51.102:8730\n' >> .env
fi
if ! grep -q '^JARVIS_ACCESS_USER=' .env; then
  printf 'JARVIS_ACCESS_USER=jarvis\n' >> .env
fi
if ! grep -q '^JARVIS_ACCESS_PASSWORD=' .env; then
  password="$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')"
  printf 'JARVIS_ACCESS_PASSWORD=%s\n' "$password" >> .env
fi
chmod 600 .env

mkdir -p "$HOME/.config/systemd/user"
cp jarvis-dashboard.service "$HOME/.config/systemd/user/jarvis-dashboard.service"
systemctl --user daemon-reload
systemctl --user enable --now jarvis-dashboard.service

printf '\nJARVIS ist als Benutzerdienst eingerichtet.\n'
printf 'Browser im Heimnetz: http://192.168.51.102:8730\n'
printf 'Benutzer: jarvis\n'
printf 'Passwort (nur für dich, nicht im Chat teilen): '
sed -n 's/^JARVIS_ACCESS_PASSWORD=//p' .env | head -n 1
printf '\nWichtig: Außerhalb des Heimnetzes nur über HTTPS und einen geschützten Reverse Proxy bereitstellen.\n'
