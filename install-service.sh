#!/usr/bin/env bash
# Einrichtung des vorhandenen deutschen JARVIS-Dashboards als Systemdienst.
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
if ! grep -q '^JARVIS_ACCESS_PASSWORD=' .env; then
  password="$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')"
  printf 'JARVIS_ACCESS_PASSWORD=%s\n' "$password" >> .env
fi
chmod 600 .env

# Den fehlerhaften Versuch eines Benutzer-Dienstes aufraeumen.
rm -f "$HOME/.config/systemd/user/jarvis-dashboard.service"

# Regulärer Systemdienst: funktioniert auch ohne DBUS_SESSION_BUS_ADDRESS.
# Der eigentliche Jarvis-Prozess läuft ausdrücklich als Benutzer jarvis.
sudo install -m 0644 jarvis-dashboard.service /etc/systemd/system/jarvis-dashboard.service
sudo systemctl daemon-reload
sudo systemctl enable jarvis-dashboard.service
sudo systemctl restart jarvis-dashboard.service

printf '\nJARVIS ist als Systemdienst unter dem Benutzer jarvis eingerichtet.\n'
printf 'Browser im Heimnetz: http://192.168.51.102:8730\n'
printf 'Einmaliges Zugangspasswort für die JARVIS-Anmeldeseite (nicht im Chat teilen): '
sed -n 's/^JARVIS_ACCESS_PASSWORD=//p' .env | head -n 1
printf '\nEin Benutzername ist nicht mehr nötig. Der Browser bleibt 30 Tage angemeldet.\n'
printf 'Für das Mikrofon muss JARVIS über HTTPS geöffnet werden (Nginx Proxy Manager).\n'
