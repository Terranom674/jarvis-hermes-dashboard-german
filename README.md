# JARVIS · Hermes-Kommandozentrale (Deutsch)

Deutschsprachige Weiterentwicklung von [JARVIS Hermes Dashboard](https://github.com/Itsme23476/jarvis-hermes-dashboard) unter der MIT-Lizenz. Der originale animierte JARVIS-Reaktor und die Hermes-Anbindung bleiben erhalten. Die Benutzeroberfläche, Statusmeldungen und die lokalen Befehle sind auf Deutsch umgestellt.

> **Wichtig:** Dies ist eine **Oberfläche für einen bereits installierten Hermes Agent** – kein neuer Assistent und kein Ersatz für dein Hermes-Profil. Die deutschsprachige Version wurde im Repository angepasst; ein Funktionstest am konkreten Hermes-Server steht noch aus.

## Funktionen

- Animierte, türkisfarbene JARVIS-Kommandozentrale im Browser
- Deutschsprachige Beschriftungen, Meldungen und Bedienelemente
- Browser-Spracherkennung mit Spracheinstellung **de-DE**
- Bevorzugte Nutzung der **vorhandenen Hermes-Spracherkennung und -Sprachausgabe**
- Für bestehende Setups geeignet: **lokales Faster-Whisper** und die in Hermes eingerichtete **Edge-TTS-Stimme** (z. B. `de-DE-FlorianMultilingualNeural`)
- Rückfallmöglichkeit auf deutsche Browserstimmen; ElevenLabs ist optional
- Deutsche Kurzbefehle zusätzlich zu den bisherigen englischen Befehlen
- Anpassungen für Desktop, Tablet und Smartphone
- Keine zweite KI, keine getrennten Hermes-Zugangsdaten
- **Keine GitHub Actions, keine automatischen Prüfungen, keine CI/CD-Konfiguration**

## Aufbau

```text
Browser / Mikrofon / JARVIS-HUD
        |
        | HTTP im lokalen, abgesicherten Zugriff
        v
JARVIS-Python-Server
        |                     |
        | Nachricht           | Audioaufnahme / Antworttext
        v                     v
Bestehende Hermes-CLI     Bestehende Hermes-Sprachumgebung
(Gedächtnis, Modell,      (lokales STT / konfigurierte TTS-Stimme)
 Skills, Werkzeuge)
```

Das Dashboard ruft **Hermes über die vorhandene CLI** auf. Es verbindet sich nicht direkt mit dem bereits laufenden Hermes-Gateway. Die Gesprächssitzung im Dashboard ist deshalb eine eigene Sitzung, die das eingestellte Hermes-Profil nutzt.

## Voraussetzungen

1. Linux mit Python 3, Bash und Git (macOS ist möglich, aber **nicht erforderlich**).
2. Ein bereits installierter und funktionsfähiger **Hermes Agent**.
3. Für die Hermes-Sprachfunktionen: vorhandene offizielle Hermes-Quellinstallation und installierte STT-/TTS-Komponenten.
4. Ein moderner Browser mit Mikrofonzugriff in einem **sicheren Kontext** (`localhost` oder HTTPS).

Diese Version benötigt **keine neue Hermes-Installation** und verändert keine vorhandenen Hermes-Konfigurationsdateien.

## Installation

Erst nach Prüfung der bestehenden Hermes-Installation auf dem Zielserver:

```bash
git clone https://github.com/Terranom674/jarvis-hermes-dashboard-german.git
cd jarvis-hermes-dashboard-german
./install.sh
```

Das Startskript erzeugt eine private `.env`-Datei aus `.env.example`, sofern sie noch nicht existiert. Anschließend startet es den Python-Server. **Der Standardzugang ist lokal:** `http://127.0.0.1:8730`.

Falls das Repository bereits ausgecheckt ist, bestehende lokale Einstellungen sichern und vor Aktualisierungen prüfen. `.env` wird nicht im Repository gespeichert.

### Browserzugang über einen SSH-Tunnel

Wenn die Oberfläche auf einem entfernten Linux-Server läuft, kann der Browser eines beliebigen Endgeräts über einen SSH-Tunnel zugreifen:

```bash
ssh -N -L 8730:127.0.0.1:8730 benutzer@SERVER-IP
```

Danach im Browser **auf dem Gerät mit dem SSH-Tunnel** `http://127.0.0.1:8730` aufrufen.

**Nicht direkt über einen öffentlichen Port bereitstellen.** Der Server lauscht absichtlich nur auf `127.0.0.1`. Eine spätere Bereitstellung über einen Reverse Proxy benötigt ein separates, sicher konfiguriertes Zugriffs- und Authentifizierungskonzept. Das Dashboard enthält **keine vollständige Benutzerverwaltung**. Ein API-Token im Quelltext der angezeigten Webseite ist kein Ersatz für eine Anmeldung.

## Deutsche Sprachfunktionen

Die vorhandene Sprachkonfiguration von Hermes wird im Standardmodus bevorzugt:

```ini
JARVIS_AUDIO_BACKEND=auto
JARVIS_HERMES_SOURCE=~/.hermes/hermes-agent
```

| Wert | Bedeutung |
|---|---|
| `auto` | Bereits installierte Hermes-Sprachdienste bevorzugen; andernfalls Browser – **niemals automatisch zu ElevenLabs wechseln** |
| `hermes` | Hermes zwingend verwenden; bei fehlender Umgebung verständlichen Fehler anzeigen |
| `browser` | Spracheingabe im Browser (`de-DE`) und deutsche Browserstimme, soweit verfügbar |
| `elevenlabs` | Optionaler externer Dienst; benötigt separat eingerichteten API-Schlüssel |

**Faster-Whisper und Florian:** Das Dashboard verwendet die vorhandenen Hermes-Funktionen `tools.voice_mode.transcribe_recording` und `tools.tts_tool.text_to_speech_tool`. Damit gilt die bereits konfigurierte Hermes-Sprache einschließlich der dort ausgewählten TTS-Stimme. Es wird keine zweite Whisper-Installation und keine zweite TTS-Konfiguration angelegt.

Für einen abweichenden Installationsort oder eine ungewöhnliche Hermes-Laufzeit sind folgende Einstellungen verfügbar:

```ini
JARVIS_HERMES_SOURCE=/absoluter/pfad/zu/hermes-agent
# Nur falls die bestehende Python-Umgebung nicht gefunden wird:
JARVIS_HERMES_PYTHON=/absoluter/pfad/zum/hermes-python
```

Die Hermes-Python-Umgebung wird nur **gelesen und verwendet**. Der Audio-Adapter startet **keinen Hermes-Installer, kein Update und keine Paketinstallation**. Die erste lokale Transkription kann durch das Laden des Whisper-Modells verzögert sein.

Das Mikrofon bleibt **am Endgerät**. Der Browser überträgt die Aufnahme bei Verwendung des Hermes-Backends zur serverseitigen Transkription; der Server liefert Audio zur Wiedergabe im Browser zurück. Es sind keine Lautsprecher am Proxmox-Server erforderlich.

**Datenschutz:** Die lokale Hermes-STT-Konfiguration kann Audio lokal verarbeiten. Edge TTS ist dagegen ein kostenloser externer Online-Sprachdienst. Browser-Spracherkennung kann ebenfalls von einem externen Anbieter abhängen.

## Deutsche Befehle

Die Schaltflächen verwenden deutsche Kurzbefehle. Die bisherigen englischen Namen bleiben kompatibel.

| Deutsch | Funktion |
|---|---|
| `/neu` | Neues Gespräch beginnen |
| `/ziel` | Dauerhaftes Ziel verwalten |
| `/profil` | Zusätzliche lokale Profilnotiz |
| `/tonfall` | Gesprächston ändern |
| `/aufgaben` / `/auftrag` | Lokale Aufgabenliste |
| `/hintergrund` | Auftrag an Hermes im Hintergrund |
| `/werkzeuge` / `/werkzeugsaetze` | Hermes-Werkzeuge abfragen |
| `/verbindungen` / `/verbinden` | Hermes-Anbindungen erläutern |
| `/browser` | Browser-Auftrag |
| `/status` | Status |
| `/leeren` | Antwortfenster leeren |
| `/hilfe` / `/befehle` | Übersicht |

Fachliche Werkzeugnamen und technische Schnittstellennamen bleiben gegebenenfalls im Original, damit die bestehenden Hermes-Aufrufe weiter funktionieren.

## Dateien

| Datei | Aufgabe |
|---|---|
| `ui/index.html` | Deutsche Bedienoberfläche |
| `ui/app.js` | Deutscher Browserdialog und Sprachbedienung |
| `ui/styles.css` | HUD und kleinere Bildschirmgrößen |
| `server.py` | Lokaler JARVIS-Webserver, Sprachendpunkte |
| `runtime.py` | Hermes-CLI-Anbindung und Sitzungsführung |
| `commands.py` | Deutschsprachige Befehle und Aufträge |
| `hermes_audio.py` | Verbindung zur vorhandenen Hermes-Python-Umgebung |
| `hermes_audio_worker.py` | Aufruf der Hermes-STT-/TTS-Provider |
| `voice.py` | Optionales ElevenLabs-Backend |
| `persona.md` | Deutsche Ergänzung zum Hermes-Profil |
| `.env.example` | Beispiel für lokale Einstellungen |
| `install.sh`, `start.sh` | Start unter Linux |

## Noch am Zielserver zu überprüfen

Die eigentliche Funktion kann erst mit der dort installierten Hermes-Version bestätigt werden. Insbesondere: Erkennung der vorhandenen Python-Umgebung, Faster-Whisper für deutschsprachige Audioaufnahmen, Edge-TTS-Ausgabe mit der eingestellten Stimme, Hermes-CLI-Sitzungen und der Zugriff über einen sicheren Browserkontext.

Die Sprachsteuerung wird über eine Taste im HUD gestartet; ein permanent aktives lokales Wake-Word wird vom ursprünglichen Projekt nicht bereitgestellt. Hintergrundaufträge werden vom Dashboard nicht ausfallsicher fortgesetzt, wenn sein Python-Prozess beendet wird.

## Lizenz

Die Originaldatei [LICENSE](LICENSE) bleibt erhalten. Projektbasis: [Itsme23476/jarvis-hermes-dashboard](https://github.com/Itsme23476/jarvis-hermes-dashboard). MIT-Lizenz.
