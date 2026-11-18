"""Anbindung der vorhandenen Hermes-Sprachdienste ohne neue Installation.

Das Dashboard benutzt Hermeses bereits eingerichtete Python-Umgebung,
STT-Konfiguration (z. B. lokales Faster-Whisper) und TTS-Stimme (z. B. Florian).
Die Laufzeit wird nur gelesen: KEIN Setup, Update oder automatisches Nachinstallieren.
"""
import base64
from functools import lru_cache
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent
WORKER = ROOT / "hermes_audio_worker.py"
MIME_SUFFIXES = {
    "audio/webm": ".webm",
    "video/webm": ".webm",
    "audio/ogg": ".ogg",
    "audio/mp4": ".m4a",
    "audio/mpeg": ".mp3",
    "audio/wav": ".wav",
}


def source_dir():
    return Path(
        os.environ.get("JARVIS_HERMES_SOURCE", "~/.hermes/hermes-agent")
    ).expanduser().resolve()


@lru_cache(maxsize=1)
def interpreter():
    """Hermes-Interpreter nur ermitteln, keine Pakete installieren.

    Zuerst eine explizite Vorgabe, dann den von Hermeses Paketverwaltung
    bereits ausgewählten Interpreter lesen, zuletzt vorhandene virtuelle Umgebungen.
    """
    manual = os.environ.get("JARVIS_HERMES_PYTHON", "").strip()
    if manual:
        candidate = Path(manual).expanduser()
        return candidate if candidate.is_file() and os.access(candidate, os.X_OK) else None

    source = source_dir()
    if not source.is_dir():
        return None

    # Hermeses PM liefert den bereits installierten Interpreter; diese Abfrage
    # ist nur lesend. Anders als run-in-hermes-env wird kein Setup gestartet.
    env = dict(os.environ)
    env["PYTHONPATH"] = str(source) + (
        os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
    )
    try:
        probe = subprocess.run(
            ["python3", "-c",
             "from pathlib import Path; from pm.environments import project_python; "
             "print(project_python(Path.cwd()))"],
            cwd=str(source), env=env, capture_output=True, text=True,
            timeout=8, check=False,
        )
        if probe.returncode == 0:
            candidate = Path(probe.stdout.strip().splitlines()[-1])
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return candidate
    except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
        pass

    for candidate in (
        source / ".venv/bin/python",
        source / "venv/bin/python",
    ):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    return None


def available():
    return source_dir().is_dir() and WORKER.is_file() and interpreter() is not None


def _run(action, payload, timeout):
    py = interpreter()
    source = source_dir()
    if py is None or not WORKER.is_file() or not source.is_dir():
        raise RuntimeError(
            "Hermes-Sprachumgebung nicht gefunden: "
            "JARVIS_HERMES_SOURCE und JARVIS_HERMES_PYTHON prüfen."
        )
    env = dict(os.environ)
    env["PYTHONPATH"] = str(source) + (
        os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
    )
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    # Kein Shell-Aufruf und kein Sprachtext als Prozessargument.
    try:
        proc = subprocess.run(
            [str(py), str(WORKER), action],
            cwd=str(source), env=env, input=payload, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=timeout, check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Hermes-Sprachdienst hat das Zeitlimit überschritten.") from exc
    except OSError as exc:
        raise RuntimeError("Hermes-Sprachdienst konnte nicht gestartet werden.") from exc
    if proc.returncode != 0:
        # stderr kann sensible Konfiguration enthalten und wird nie weitergereicht.
        raise RuntimeError(f"Hermes-Sprachdienst fehlgeschlagen (Code {proc.returncode}).")
    try:
        answer = json.loads(proc.stdout.strip().splitlines()[-1])
    except (IndexError, ValueError) as exc:
        raise RuntimeError("Hermes-Sprachdienst hat kein gültiges Ergebnis geliefert.") from exc
    if not answer.get("ok"):
        raise RuntimeError(str(answer.get("error") or "Hermes-Sprachdienst fehlgeschlagen.")[:200])
    return answer


def transcribe(audio, mime="audio/webm"):
    if not audio:
        raise ValueError("Die Audioaufnahme ist leer.")
    suffix = MIME_SUFFIXES.get(mime.split(";", 1)[0].lower(), ".webm")
    with tempfile.NamedTemporaryFile(prefix="jarvis-hermes-stt-", suffix=suffix) as recording:
        recording.write(audio)
        recording.flush()
        result = _run("stt", str(recording.name), timeout=180)
    return str(result.get("text") or "").strip()


def speak(text):
    text = (text or "").strip()
    if not text:
        raise ValueError("Kein Text für die Sprachausgabe vorhanden.")
    result = _run("tts", text[:2500], timeout=120)
    try:
        audio = base64.b64decode(result["audio"], validate=True)
    except (KeyError, ValueError) as exc:
        raise RuntimeError("Ungültige Audiodaten des Hermes-Sprachdienstes.") from exc
    if not audio:
        raise RuntimeError("Hermes hat keine Audiodaten erzeugt.")
    mime = str(result.get("mime") or "audio/mpeg")
    if not mime.startswith("audio/"):
        raise RuntimeError("Hermes hat ein unbekanntes Audioformat erzeugt.")
    return audio, mime
