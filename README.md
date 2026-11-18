# JARVIS · Hermes Mission Control (Deutsch)

Deutsche Weiterentwicklung des [JARVIS Hermes Dashboards](https://github.com/Itsme23476/jarvis-hermes-dashboard) (MIT-Lizenz). Dieses Dashboard ist **eine Oberfläche für den bestehenden Hermes Agent**, keine zweite KI-Installation.

## Änderungen dieser Version

- Deutschsprachige Bedienoberfläche, Meldungen und Sprachsteuerung
- Deutsche Browser-Spracherkennung (`de-DE`) als Ausweichmöglichkeit
- Direkter Zugriff auf die **bereits eingerichteten Hermes-STT/TTS-Provider**, wenn die Hermes-Quellumgebung vorhanden ist
- Beispiel: lokales Faster-Whisper für Spracheingabe und Edge TTS mit der in Hermes eingestellten Stimme
- Kein ElevenLabs-Konto und kein gesonderter API-Schlüssel erforderlich, sofern Hermes-Sprachdienste funktionieren
- Bestehende Hermes-CLI, Werkzeuge, Profile, Erinnerungen und Skills bleiben erhalten
- Die Originaloberfläche (rotierende JARVIS-Kernanzeige) bleibt erhalten

## Voraussetzungen

- Linux oder macOS mit Python 3, Bash und Git
- Ein bereits eingerichteter [Hermes Agent](https://github.com/NousResearch/hermes-agent) und funktionierendes `hermes chat`
- Für Hermes-STT/TTS die offizielle Hermes-Quellinstallation mit `scripts/run-in-hermes-env`
- Für Mikrofonbetrieb ein Browser mit `MediaRecorder`/AudioContext und ein sicherer Browserkontext (`localhost` oder HTTPS)
- Für lokale Faster-Whisper-Spracherkennung: in Hermes installierter Whisper-Zusatz und konfiguriertes `stt.provider=local`
- Für Edge-TTS: korrekt eingerichtete Hermes-TTS-Konfiguration

## Installation (erst nach Sicherung und Prüfung)

```bash
git clone https://github.com/Terranom674/jarvis-hermes-dashboard-german.git
cd jarvis-hermes-dashboard-german
./install.sh
```

Der Installer erzeugt `.env` aus `.env.example` und startet das Dashboard auf **127.0.0.1:8730**. Der Browser öffnet sich auf dem Server nicht automatisch (`JARVIS_OPEN=0`).

Für eine lokale SSH-Verbindung vom gewünschten Endgerät aus kann der Port per SSH-Tunnel weitergeleitet werden:

```bash
ssh -N -L 8730:127.0.0.1:8730 jarvis@192.168.51.102
```

Anschließend im Browser auf dem Endgerät `http://127.0.0.1:8730` aufrufen. **Nicht direkt ins Internet stellen.** Der HTTP-Server akzeptiert absichtlich nur localhost und besitzt keine vollständige Benutzeranmeldung; Reverse-Proxy-Zugriff erfordert eine separate, abgesicherte Planung und entsprechende Anpassungen.

## Sprache

Die Sprachauswahl erfolgt auf dem Server in `.env`:

| Option | Wirkung |
|---|---|
| `JARVIS_AUDIO_BACKEND=auto` | Bevorzugt Hermes-STT/TTS, wenn die Hermes-Quellumgebung gefunden wird |
| `JARVIS_AUDIO_BACKEND=hermes` | Verwende Hermes, sofern verfügbar; sonst wird auf ElevenLabs/Browser zurückgegriffen |
| `JARVIS_AUDIO_BACKEND=browser` | Browser-Spracherkennung und Browserstimmen |
| `JARVIS_AUDIO_BACKEND=elevenlabs` | ElevenLabs mit gesondertem API-Schlüssel, andernfalls Browser |

Der Standardpfad zum vorhandenen Hermes-Quellcode lautet:

```ini
JARVIS_HERMES_SOURCE=~/.hermes/hermes-agent
```

Eine abweichende Laufzeit kann über `JARVIS_HERMES_RUNNER` angegeben werden. Die Hermes-Audiobrücke verwendet dieselben Providerfunktionen wie die offizielle Hermes-Audio-API: `tools.voice_mode.transcribe_recording` und `tools.tts_tool.text_to_speech_tool`. Sie verändert **keine** Hermes-Konfigurationsdateien.

**Wichtig:** Das Vorhandensein der Hermes-Quellumgebung bedeutet noch nicht, dass das STT/TTS-Backend einsatzbereit ist. Erst der Sprachtest auf dem konkreten Server bestätigt, dass die installierten Modelle, Python-Pakete und Audioformate funktionieren.

Wenn Hermes-Audio verwendet wird, wird der Ton als HTTP-Antwort an den Browser übertragen und dort abgespielt. Eine Tonausgabe am Server ist dafür nicht erforderlich. Wird die Browser-Sprachfunktion verwendet, hängt die Verfügbarkeit von Browser und dort installierten Stimmen ab.

## Sicherheit und Grenzen

- HTTP auf `127.0.0.1:8730` beschränkt; keine öffentlich erreichbare Portfreigabe
- API-Token wird pro Serverstart erstellt; **kein** Ersatz für einen vorgeschalteten sicheren Login
- Keine automatische Änderung von Berechtigungen, Tools oder Hermes-Gedächtnis
- Keine verifizierte native Mobilansicht: Die originale Drei-Spalten-Darstellung ist für große Bildschirme optimiert
- Bisher kein fertiger systemd-Dienst enthalten
- Der zusätzliche Hermes-Audio-Worker wird pro Sprachauftrag gestartet; das kann die erste Antwort verzögern
- Vor Veröffentlichung müssen Sprachintegration und Hermes-CLI-Parameter im Zielsystem geprüft werden

## Wesentliche Dateien

- `ui/index.html`, `ui/app.js`, `ui/styles.css`: Oberfläche, Browserdialog und Darstellung
- `server.py`: Dashboard-HTTP-Server mit eigenen Endpunkten
- `runtime.py`: Übergibt Aufträge an die vorhandene Hermes-CLI
- `hermes_audio.py`: Brücke zur vorhandenen Hermes-Sprachumgebung
- `hermes_audio_worker.py`: STT/TTS-Ausführung mit Hermes-Providerfunktionen
- `voice.py`: optionaler ElevenLabs-Provider
- `persona.md`: ergänzender JARVIS-Tonfall

## Lizenz und Herkunft

Projektbasis: [Itsme23476/jarvis-hermes-dashboard](https://github.com/Itsme23476/jarvis-hermes-dashboard), MIT-Lizenz. Die Lizenzdatei bleibt erhalten.
