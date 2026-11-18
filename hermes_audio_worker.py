"""Run STT/TTS inside the official Hermes Python environment.

Entrypoints are the same provider functions that Hermes' own web audio API uses.
This worker intentionally never changes Hermes settings.
"""
import base64
import json
import mimetypes
from pathlib import Path
import sys


def _print(result):
    print(json.dumps(result, ensure_ascii=False), flush=True)


def main():
    if len(sys.argv) < 3 or sys.argv[1] not in ("stt", "tts"):
        _print({"ok": False, "error": "Ungültiger Audioauftrag"})
        return 2
    mode, value = sys.argv[1], sys.argv[2]
    try:
        if mode == "stt":
            from tools.voice_mode import transcribe_recording
            result = transcribe_recording(value)
            if not result.get("success"):
                _print({"ok": False, "error": result.get("error", "Transkription fehlgeschlagen")})
                return 1
            _print({"ok": True, "text": str(result.get("transcript") or "")})
            return 0

        from tools.tts_tool import text_to_speech_tool
        result = text_to_speech_tool(value)
        if isinstance(result, str):
            result = json.loads(result)
        if not result.get("success"):
            _print({"ok": False, "error": result.get("error", "Sprachausgabe fehlgeschlagen")})
            return 1
        file_path = result.get("file_path")
        if not file_path:
            raise RuntimeError("Hermes hat keinen Audiopfad geliefert")
        path = Path(file_path)
        try:
            audio = path.read_bytes()
        finally:
            # Hermes creates a temporary TTS file; discard it after reading.
            path.unlink(missing_ok=True)
        mime = mimetypes.guess_type(str(path))[0] or "audio/mpeg"
        _print({"ok": True, "audio": base64.b64encode(audio).decode("ascii"), "mime": mime})
        return 0
    except Exception as exc:
        # Deliberately avoid traceback/details that might contain user secrets.
        _print({"ok": False, "error": type(exc).__name__})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
