"""Optionaler ElevenLabs-Sprachdienst.

Nur mit einem bewusst eingetragenen API-Schlüssel aktiv.
Der Standard ist die vorhandene Hermes-Spracherkennung und -Sprachausgabe.
Zugangsdaten bleiben serverseitig.
"""

import json
import os
import urllib.error
import urllib.request

# Standardstimme des optionalen Dienstes, über ELEVENLABS_VOICE_ID änderbar.
DEFAULT_VOICE = "21m00Tcm4TlvDq8ikWAM"
MODEL = os.environ.get("ELEVENLABS_MODEL", "eleven_turbo_v2_5")


def available():
    return bool(os.environ.get("ELEVENLABS_API_KEY"))


def voice_id():
    return os.environ.get("ELEVENLABS_VOICE_ID", DEFAULT_VOICE)


def speak(text):
    """MP3-Audiodaten ausgeben oder einen Fehler melden."""
    if not available():
        raise RuntimeError("ElevenLabs-API-Schlüssel ist nicht eingerichtet.")
    text = (text or "").strip()
    if not text:
        raise ValueError("Kein Text für die Sprachausgabe.")

    req = urllib.request.Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id()}",
        data=json.dumps({
            "text": text[:2500],
            "model_id": MODEL,
            "voice_settings": {
                "stability": 0.42,          # Natürliche Sprechvariation
                "similarity_boost": 0.85,
                "style": 0.25,
                "use_speaker_boost": True,
            },
        }).encode(),
        method="POST",
        headers={
            "content-type": "application/json",
            "accept": "audio/mpeg",
            "xi-api-key": os.environ["ELEVENLABS_API_KEY"],
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def transcribe(audio, mime="audio/webm"):
    """Deutsche Spracheingabe über den optionalen ElevenLabs-Scribe-Dienst."""
    if not available():
        raise RuntimeError("ElevenLabs-API-Schlüssel ist nicht eingerichtet.")
    if not audio:
        raise ValueError("Leere Audioaufnahme.")

    ext = {"audio/webm": "webm", "audio/ogg": "ogg", "audio/mp4": "mp4",
           "audio/mpeg": "mp3", "audio/wav": "wav"}.get(mime.split(";")[0], "webm")
    boundary = "----jarvis" + os.urandom(8).hex()
    b = boundary.encode()

    body = b"".join([
        b"--", b, b"\r\n",
        b'Content-Disposition: form-data; name="model_id"\r\n\r\nscribe_v2\r\n',
        b"--", b, b"\r\n",
        b'Content-Disposition: form-data; name="language_code"\r\n\r\nde\r\n',
        b"--", b, b"\r\n",
        f'Content-Disposition: form-data; name="file"; filename="turn.{ext}"\r\n'.encode(),
        f"Content-Type: {mime}\r\n\r\n".encode(),
        audio, b"\r\n",
        b"--", b, b"--\r\n",
    ])

    req = urllib.request.Request(
        "https://api.elevenlabs.io/v1/speech-to-text",
        data=body, method="POST",
        headers={
            "content-type": f"multipart/form-data; boundary={boundary}",
            "xi-api-key": os.environ["ELEVENLABS_API_KEY"],
        },
    )
    with urllib.request.urlopen(req, timeout=45) as r:
        return (json.loads(r.read()).get("text") or "").strip()


def voices():
    """Verfügbare Stimmen des optionalen ElevenLabs-Kontos abrufen."""
    if not available():
        return []
    req = urllib.request.Request(
        "https://api.elevenlabs.io/v2/voices",
        headers={"xi-api-key": os.environ["ELEVENLABS_API_KEY"]},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            body = json.loads(r.read())
    except Exception:                                  # noqa: BLE001
        return []
    return [dict(id=v.get("voice_id"), name=v.get("name"),
                 labels=v.get("labels", {}))
            for v in body.get("voices", [])]
