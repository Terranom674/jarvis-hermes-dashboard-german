"""Bridge to Hermes' already-configured STT and TTS providers.

Runs a short-lived worker in the officially supported Hermes Python environment.
No extra cloud credentials, model downloads, or duplicate configuration are required.
"""
import base64
import json
import mimetypes
import os
from pathlib import Path
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parent
WORKER = ROOT / "hermes_audio_worker.py"
MIME_SUFFIXES = {
    "audio/webm": ".webm", "audio/ogg": ".ogg", "audio/mp4": ".m4a",
    "audio/mpeg": ".mp3", "audio/wav": ".wav", "video/webm": ".webm",
}


def source_dir():
    return Path(os.environ.get("JARVIS_HERMES_SOURCE", "~/.hermes/hermes-agent")).expanduser()


def launcher():
    override = os.environ.get("JARVIS_HERMES_RUNNER", "").strip()
    return (Path(override).expanduser() if override
            else source_dir() / "scripts" / "run-in-hermes-env")


def available():
    return launcher().is_file() and WORKER.is_file()


def _run(action, payload, timeout):
    if not available():
        raise RuntimeError("Hermes-Sprachumgebung nicht gefunden. JARVIS_HERMES_SOURCE pruefen.")
    # No shell interpolation: speech text is sent over stdin, never shell arguments.
    command = ["bash", str(launcher()), "python", str(WORKER), action]
    try:
        proc = subprocess.run(
            command, cwd=str(source_dir()), input=payload, text=True,
            capture_output=True, timeout=timeout, check=False
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Hermes-Sprachverarbeitung hat das Zeitlimit erreicht.") from exc
    except OSError as exc:
        raise RuntimeError("Hermes-Sprachumgebung konnte nicht gestartet werden.") from exc
    if proc.returncode != 0:
        # Never include raw stderr: provider errors can contain confidential data.
        raise RuntimeError("Hermes-Sprachdienst fehlgeschlagen (Exitcode %d)." % proc.returncode)
    try:
        # A provider may log during startup; the final stdout line belongs to our worker.
        answer = json.loads(proc.stdout.strip().splitlines()[-1])
    except (IndexError, ValueError) as exc:
        raise RuntimeError("Ungueltige Antwort des Hermes-Sprachdienstes.") from exc
    if not answer.get("ok"):
        raise RuntimeError(str(answer.get("error") or "Hermes-Sprachdienst fehlgeschlagen.")[:200])
    return answer


def transcribe(audio, mime="audio/webm"):
    if not audio:
        raise ValueError("Leere Audioaufnahme")
    suffix = MIME_SUFFIXES.get(mime.split(";", 1)[0].lower(), ".webm")
    with tempfile.NamedTemporaryFile(prefix="jarvis-hermes-stt-", suffix=suffix) as recording:
        recording.write(audio)
        recording.flush()
        result = _run("stt", str(recording.name), timeout=180)
    return str(result.get("text") or "").strip()


def speak(text):
    text = (text or "").strip()
    if not text:
        raise ValueError("Leerer Text")
    result = _run("tts", text[:2500], timeout=120)
    data = base64.b64decode(result["audio"], validate=True)
    if not data:
        raise RuntimeError("Hermes hat keine Audiodaten erzeugt.")
    mime = result.get("mime") or "audio/mpeg"
    if not mime.startswith("audio/"):
        raise RuntimeError("Hermes hat ein unerwartetes Audioformat geliefert.")
    return data, mime
