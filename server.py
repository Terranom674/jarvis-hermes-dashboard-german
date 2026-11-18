"""JARVIS-Kommandozentrale für den bestehenden Hermes Agent.

Verwendet das vorhandene Hermes-Profil mit Gedächtnis, Skills und Werkzeugen.
Die Sprachdienste werden bevorzugt direkt aus der Hermes-Konfiguration geladen.
"""

import json
import mimetypes
import os
import pathlib
import secrets
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

ROOT = pathlib.Path(__file__).resolve().parent
UI = ROOT / "ui"

# Lokale Konfiguration vor dem Import der Komponenten einlesen.
_env = ROOT / ".env"
if _env.exists():
    for line in _env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

import commands         # noqa: E402
import runtime          # noqa: E402
import voice            # noqa: E402
import hermes_audio     # noqa: E402

PORT = int(os.environ.get("JARVIS_PORT", "8730"))
# Hermes-STT/TTS bevorzugen; Browser/ElevenLabs bleiben optionale Alternativen.
AUDIO_BACKEND = os.environ.get("JARVIS_AUDIO_BACKEND", "auto").strip().lower()
if AUDIO_BACKEND not in ("auto", "hermes", "browser", "elevenlabs"):
    raise ValueError("Ungültiges JARVIS_AUDIO_BACKEND: auto, hermes, browser oder elevenlabs auswählen.")
HERMES_AUDIO = AUDIO_BACKEND in ("auto", "hermes") and hermes_audio.available()
if AUDIO_BACKEND == "hermes" and not HERMES_AUDIO:
    raise RuntimeError("Hermes-Sprachumgebung nicht gefunden. "
                       "JARVIS_HERMES_SOURCE oder JARVIS_HERMES_PYTHON prüfen.")
SPEECH_BACKEND = ("hermes" if HERMES_AUDIO else
                  "browser" if AUDIO_BACKEND == "browser" else
                  "elevenlabs" if voice.available() and AUDIO_BACKEND in ("auto", "elevenlabs") else
                  "browser")
API_TOKEN = secrets.token_urlsafe(32)
RUN_LOCK = threading.Lock()
MAX_JSON_BODY = 1024 * 1024
MAX_AUDIO_BODY = 12 * 1024 * 1024

# Sprachstil nur als Ergänzung des vorhandenen Hermes-Profils.
_PERSONA_FILE = ROOT / "persona.md"


def persona():
    try:
        base = _PERSONA_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        base = ""
    extra = commands.context_block()      # profile / goal / personality / queue
    return "\n\n".join(x for x in (base, extra) if x)
# Fortlaufendes Gespräch bis /neu beziehungsweise /new.
SESSION = {"id": None}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        if os.environ.get("JARVIS_VERBOSE"):
            sys.stderr.write("  " + (fmt % args) + "\n")

    # ── helpers ──────────────────────────────────────────────
    def _json(self, body, code=200):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _bytes(self, data, ctype, code=200):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _read(self, limit):
        n = int(self.headers.get("Content-Length", 0))
        if n < 0 or n > limit:
            raise ValueError(f"Anfrage überschreitet {limit} Byte.")
        return self.rfile.read(n) if n else b""

    def _host_ok(self):
        host = self.headers.get("Host", "")
        return host in {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}

    def _origin_ok(self):
        origin = self.headers.get("Origin")
        return origin in {
            f"http://127.0.0.1:{PORT}", f"http://localhost:{PORT}"
        }

    def _token_ok(self):
        supplied = self.headers.get("X-Jarvis-Token", "")
        return bool(supplied) and secrets.compare_digest(supplied, API_TOKEN)

    # ── GET ──────────────────────────────────────────────────
    def do_GET(self):
        if not self._host_ok():
            return self._json({"error": "Ungültiger Hostname."}, 403)
        p = urlparse(self.path).path
        if p == "/api/status":
            return self._json(dict(
                runtime=runtime.runtime_kind(),
                permission=runtime.PERMISSION,
                profile=runtime.PROFILE,
                source=runtime.SOURCE,
                workdir=runtime.WORKDIR,
                model=runtime.MODEL or "Hermes-Standardmodell",
                tools=runtime.hermes_tools_snapshot(),
                browser_stt=True,
                browser_tts=True,
                voice_mode=SPEECH_BACKEND,
                voice_id="Hermes-Konfiguration" if HERMES_AUDIO else (voice.voice_id() if voice.available() else "browser"),
                stt=SPEECH_BACKEND,
                tts=SPEECH_BACKEND,
                session=SESSION["id"]))
        if p == "/api/jobs":
            if not self._token_ok():
                return self._json({"error": "Keine Berechtigung."}, 401)
            # finished background missions, reported once each
            return self._json(dict(done=commands.take_finished(),
                                   running=[j for j in commands.jobs_snapshot()
                                            if j["status"] == "running"]))

        rel = "index.html" if p == "/" else p.lstrip("/")
        f = (UI / rel).resolve()
        if not str(f).startswith(str(UI.resolve())) or not f.is_file():
            return self._bytes("Nicht gefunden".encode("utf-8"), "text/plain; charset=utf-8", 404)
        ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
        data = f.read_bytes()
        if rel == "index.html":
            data = data.replace(b"__JARVIS_TOKEN__", API_TOKEN.encode())
        return self._bytes(data, ctype)

    # ── POST ─────────────────────────────────────────────────
    def do_POST(self):
        p = urlparse(self.path).path
        if not self._host_ok() or not self._origin_ok():
            return self._json({"error": "Anfrageursprung abgewiesen."}, 403)
        if not self._token_ok():
            return self._json({"error": "unauthorized"}, 401)
        ctype = self.headers.get("Content-Type", "").split(";", 1)[0].lower()
        if p in {"/api/run", "/api/speak", "/api/new", "/api/cancel"} and ctype != "application/json":
            return self._json({"error": "JSON-Daten werden benötigt."}, 415)
        if p == "/api/listen" and not ctype.startswith("audio/"):
            return self._json({"error": "Eine Audioaufnahme wird benötigt."}, 415)
        try:
            raw = self._read(MAX_AUDIO_BODY if p == "/api/listen" else MAX_JSON_BODY)
        except (TypeError, ValueError):
            return self._json({"error": "Die Anfrage ist zu groß."}, 413)

        if p == "/api/speak":
            try:
                text = (json.loads(raw or b"{}").get("text") or "").strip()
                if SPEECH_BACKEND == "browser":
                    return self._json({"error": "Browser-Sprachausgabe erfolgt lokal im Browser."}, 400)
                if HERMES_AUDIO:
                    audio, mime = hermes_audio.speak(text)
                    return self._bytes(audio, mime)
                return self._bytes(voice.speak(text), "audio/mpeg")
            except Exception as e:                        # noqa: BLE001
                return self._json({"error": str(e)[:200]}, 503)

        if p == "/api/listen":
            try:
                mime = self.headers.get("Content-Type", "audio/webm")
                if SPEECH_BACKEND == "browser":
                    return self._json({"error": "Browser-Spracherkennung erfolgt lokal im Browser."}, 400)
                transcript = hermes_audio.transcribe(raw, mime) if HERMES_AUDIO else voice.transcribe(raw, mime)
                return self._json({"text": transcript})
            except Exception as e:                        # noqa: BLE001
                return self._json({"error": str(e)[:300], "text": ""}, 503)

        if p == "/api/new":
            runtime.cancel_active()
            SESSION["id"] = None
            return self._json({"ok": True})

        if p == "/api/cancel":
            stopped = runtime.cancel_active()
            SESSION["id"] = None
            return self._json({"ok": True, "stopped": stopped})

        if p == "/api/run":
            if not RUN_LOCK.acquire(blocking=False):
                return self._json({"error": "JARVIS bearbeitet bereits einen anderen Auftrag."}, 409)
            try:
                return self._stream_run(raw)
            finally:
                RUN_LOCK.release()

        return self._json({"error": "Unbekannte Schnittstelle."}, 404)

    # ── the run: NDJSON stream of events ─────────────────────
    def _stream_run(self, raw):
        try:
            payload = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            return self._json({"error": "Ungültige JSON-Daten."}, 400)
        message = (payload.get("message") or "").strip()
        extra = (payload.get("system") or "").strip()
        system = "\n\n".join(x for x in (persona(), extra) if x) or None
        fresh = bool(payload.get("fresh"))
        if not message:
            return self._json({"error": "Die Anweisung ist leer."}, 400)
        if fresh:
            SESSION["id"] = None

        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()

        def emit(ev):
            self.wfile.write((json.dumps(ev) + "\n").encode())
            self.wfile.flush()

        # ── the command matrix: /new /profile /goal /personality /kanban /mission /background /tools /status /browser
        cmd = commands.handle(
            message,
            runner=lambda m: runtime.run(m, None, persona()))
        if cmd:
            if cmd.get("note"):
                emit(dict(t="note", message=cmd["note"]))
            if cmd.get("fresh"):
                SESSION["id"] = None
            if cmd.get("message") is None:
                # answered locally — no model call needed
                emit(dict(t="delta", text=cmd.get("reply", "Erledigt.")))
                emit(dict(t="complete", ms=0))
                return
            message = cmd["message"]
            system = "\n\n".join(x for x in (persona(), extra) if x) or None

        try:
            for ev in runtime.run(message, SESSION["id"], system):
                # Only remember a real Hermes session, never demo/mock identifiers.
                sid = ev.get("session_id")
                # Only remember a session that actually COMPLETED. Storing it from
                # `status` (which fires at init) means one broken run poisons every
                # run after it with --resume <half-born session>.
                if ev.get("t") == "complete" and runtime.valid_session(sid):
                    SESSION["id"] = sid
                if ev.get("t") == "error":
                    SESSION["id"] = None       # drop a bad/stale session so the next run is fresh
                emit(ev)
        except (BrokenPipeError, ConnectionResetError):
            pass                                          # client navigated away
        except Exception as e:                            # noqa: BLE001
            try:
                emit(dict(t="error", message=str(e)[:300]))
            except OSError:
                pass


def main():
    kind = runtime.runtime_kind()
    brain = ("Hermes Agent mit dem vorhandenen Profil verbunden."
             if kind == "hermes" else "Hermes-CLI nicht erreichbar.")
    voice_name = ("Hermes-Sprachdienste" if HERMES_AUDIO else
                  "ElevenLabs" if SPEECH_BACKEND == "elevenlabs"
                  else "Browser-Spracherkennung und Browserstimme")
    print(f"""
  JARVIS · Hermes-Kommandozentrale
  -------------------------------------------
  KI-Kern:        {brain}
  Profil:         {runtime.PROFILE}
  Arbeitsordner:  {runtime.WORKDIR}
  Sprachmodus:    {voice_name}
  Zugang:         http://127.0.0.1:{PORT}
  Netzwerk:       Nur localhost (kein öffentlicher Zugriff)
""", flush=True)

    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    if os.environ.get("JARVIS_OPEN", "0") != "0":
        webbrowser.open(f"http://127.0.0.1:{PORT}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nJARVIS wurde beendet.")
        srv.shutdown()


if __name__ == "__main__":
    main()
