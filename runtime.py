"""Hermes-Laufzeit für die deutschsprachige JARVIS-Oberfläche.

Verwendet die installierte Hermes-CLI mit dem bestehenden Profil, Gedächtnis
und denselben Werkzeugen. Es wird kein zweiter Agent eingerichtet.
"""

import collections
import json
import os
import re
import shlex
import shutil
import subprocess
import threading
import time

_SESSION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{7,127}$")
_ANSI = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))")
_CLI_NOISE = re.compile(
    r"^(?:Query:|Initializing agent|Resume this session with:|hermes --resume\b|"
    r"Session:|Duration:|Messages:|─+|=+|[-─ ]*⚕\s*Hermes\b)", re.I)

MODEL = os.environ.get("JARVIS_MODEL", "").strip()
PROFILE = os.environ.get("HERMES_PROFILE", os.environ.get("JARVIS_PROFILE", "default")).strip() or "default"
# Hermes akzeptiert bei session.create nur definierte Quellen.
# Das Dashboard ist ein vom Nutzer bedienter lokaler Client: Quelle "cli".
# Ein frei erfundenes "--source jarvis-dashboard" führt zu "invalid params".
SOURCE = "cli"
WORKDIR = os.path.expanduser(os.environ.get("JARVIS_WORKDIR", os.getcwd()))
PERMISSION = os.environ.get("JARVIS_PERMISSION", os.environ.get("HERMES_PERMISSION", "normal")).strip().lower()
RUNTIME = os.environ.get("JARVIS_RUNTIME", "auto").strip().lower()  # auto|hermes|mock
IDLE_TIMEOUT = int(os.environ.get("JARVIS_TIMEOUT", "120"))
# Raw transcripts can contain private prompts. Logging is off by default.
RAW_LOG = os.environ.get("JARVIS_RAW_LOG", "").strip()
TOOLSETS = os.environ.get("HERMES_TOOLSETS", "").strip()

# One Hermes subprocess at a time. Hermes session state and profile resources are
# shared, so foreground runs and /background missions must not overlap. The active
# process handle lets the browser Escape key stop the backend work, not just the
# frontend fetch.
EXECUTION_LOCK = threading.RLock()
_ACTIVE_PROC = None
_ACTIVE_LOCK = threading.Lock()


def cancel_active():
    """Laufenden Hermes-Prozess bei Nutzerabbruch beenden."""
    with _ACTIVE_LOCK:
        proc = _ACTIVE_PROC
    if proc is None or proc.poll() is not None:
        return False
    try:
        proc.terminate()
        return True
    except Exception:
        return False


def valid_session(sid):
    # Hermes emits timestamp-based IDs such as 20260808_031038_0ecb14.
    return bool(sid) and bool(_SESSION_ID.match(str(sid)))


def _mono_ms():
    return int(time.monotonic() * 1000)


def _hermes_base():
    configured = os.environ.get("HERMES_CMD", "").strip()
    if configured:
        return shlex.split(configured)
    exe = shutil.which("hermes")
    if exe:
        return [exe]
    # Last-resort module invocation; start.sh prepends common Python bin dirs.
    return ["python3", "-m", "hermes_cli.main"]


def _can_launch_hermes():
    try:
        base = _hermes_base()
        proc = subprocess.run(base + ["--version"], cwd=WORKDIR, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=12)
        return proc.returncode == 0, (proc.stdout or proc.stderr).strip()
    except Exception as e:  # noqa: BLE001
        return False, str(e)


def runtime_kind():
    if RUNTIME == "mock":
        return "mock"
    if RUNTIME == "hermes":
        return "hermes"
    ok, _ = _can_launch_hermes()
    return "hermes" if ok else "mock"


def build_command(message, session_id=None, system=None):
    # Hermes chat has no separate --system flag. Put the voice persona and the
    # current request into one explicit turn so the model answers as JARVIS
    # instead of narrating its CLI/runtime. Quiet mode removes the Hermes banner.
    prompt = message
    if system and not valid_session(session_id):
        prompt = (f"{system}\n\n## Aktuelle Nutzeranfrage\n{message}\n\n"
                  "Antworte auf Deutsch, sofern keine andere Sprache gewünscht ist. "
                  "Erwähne keine internen Sitzungskennungen oder Laufzeitinformationen. "
                  "Beantworte komplexe Fragen vollständig statt sie auf wenige Sätze zu kürzen.")
    cmd = _hermes_base() + ["chat", "-Q", "-q", prompt, "--source", SOURCE]
    if valid_session(session_id):
        cmd += ["--resume", str(session_id)]
    if PROFILE and PROFILE != "default":
        cmd += ["--profile", PROFILE]
    if MODEL:
        cmd += ["--model", MODEL]
    if TOOLSETS:
        cmd += ["--toolsets", TOOLSETS]
    # Hermes one-shot output is currently plain text; slash commands that need a
    # live TUI are handled in commands.py before we get here. Prompts go to the
    # real agent with normal tool access.
    return cmd


def hermes_tools_snapshot(limit=36):
    """Kurze Übersicht der sichtbaren Hermes-Werkzeuge für die Oberfläche."""
    try:
        base = _hermes_base()
        proc = subprocess.run(base + ["tools", "list"], cwd=WORKDIR, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=20)
        out = (proc.stdout or proc.stderr or "").strip()
        tools = []
        for line in out.splitlines():
            clean = re.sub(r"\x1b\[[0-9;]*m", "", line).strip()
            if not clean or clean.startswith(("Usage", "─", "=")):
                continue
            if any(tok in clean.lower() for tok in ("enabled", "available", "tool", "browser", "terminal", "file", "google", "github", "web", "voice")):
                tools.append(clean[:80])
            if len(tools) >= limit:
                break
        return tools or [out[:120]] if out else []
    except Exception:
        return []


def run_hermes(message, session_id=None, system=None):
    with EXECUTION_LOCK:
        yield from _run_hermes_locked(message, session_id, system)


def _run_hermes_locked(message, session_id=None, system=None):
    global _ACTIVE_PROC
    started = _mono_ms()
    cmd = build_command(message, session_id, system)
    yield dict(t="status", model=MODEL or "Hermes-Standardmodell", tools=len(hermes_tools_snapshot()),
               mcp=[], permission=PERMISSION, profile=PROFILE, runtime="hermes",
               session_id=session_id)

    child_env = dict(os.environ)
    # Ensure GUI-started shells can still find common Homebrew/user installs.
    home = os.path.expanduser("~")
    child_env["PATH"] = ":".join(dict.fromkeys([
        child_env.get("PATH", ""),
        "/opt/homebrew/bin", "/usr/local/bin",
        os.path.join(home, ".local", "bin"),
        os.path.join(home, ".npm-global", "bin"),
        "/usr/bin", "/bin", "/usr/sbin", "/sbin",
    ]))

    try:
        proc = subprocess.Popen(cmd, cwd=WORKDIR, text=True, bufsize=1,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                env=child_env)
        with _ACTIVE_LOCK:
            _ACTIVE_PROC = proc
    except FileNotFoundError:
        raise RuntimeError("Hermes-CLI nicht gefunden. Bitte HERMES_CMD auf die vorhandene Hermes-Datei setzen.")

    q = collections.deque()
    lock = threading.Lock()
    done = threading.Event()
    errbuf = collections.deque(maxlen=120)
    raw = None
    if RAW_LOG:
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(os.path.expanduser(RAW_LOG), flags, 0o600)
        os.fchmod(fd, 0o600)
        raw = os.fdopen(fd, "w", encoding="utf-8", errors="replace")
        raw.write("$ " + " ".join(shlex.quote(x) for x in cmd) + "\n\n")
        raw.flush()

    def pump_stdout():
        try:
            for ln in proc.stdout:
                if raw:
                    raw.write("OUT " + ln); raw.flush()
                with lock:
                    q.append(ln)
        finally:
            done.set()

    def pump_stderr():
        try:
            for ln in proc.stderr:
                if raw:
                    raw.write("ERR " + ln); raw.flush()
                errbuf.append(ln.rstrip())
        except Exception:
            pass

    threading.Thread(target=pump_stdout, daemon=True).start()
    threading.Thread(target=pump_stderr, daemon=True).start()

    first = True
    last = time.monotonic()
    text_seen = False
    emitted_session = None
    try:
        while not done.is_set() or q:
            line = None
            with lock:
                if q:
                    line = q.popleft()
            if line is None:
                if proc.poll() is not None and done.is_set():
                    break
                if time.monotonic() - last > IDLE_TIMEOUT:
                    proc.kill()
                    err = " | ".join(list(errbuf)[-3:])
                    yield dict(t="error", message=(f"Hermes hat innerhalb von {IDLE_TIMEOUT} Sekunden nicht geantwortet und wurde gestoppt. " + err)[:400])
                    return
                time.sleep(0.05)
                continue
            last = time.monotonic()
            clean = _ANSI.sub("", line).strip()
            if not clean:
                continue
            session_match = re.match(r"^session_id:\s*(\S+)\s*$", clean, re.I)
            if session_match:
                candidate = session_match.group(1)
                if valid_session(candidate):
                    emitted_session = candidate
                continue
            # Be defensive when an older Hermes build ignores quiet mode.
            if _CLI_NOISE.match(clean):
                continue
            if first:
                first = False
                yield dict(t="latency", ms=_mono_ms() - started)
            text_seen = True
            yield dict(t="delta", text=clean + "\n")

        rc = proc.wait(timeout=5)
        # Hermes writes its programmatic session_id marker to stderr in quiet
        # mode, so capture it there without exposing it as response text.
        for errline in errbuf:
            session_match = re.match(r"^session_id:\s*(\S+)\s*$", errline.strip(), re.I)
            if session_match and valid_session(session_match.group(1)):
                emitted_session = session_match.group(1)
        if rc != 0:
            err = " | ".join(list(errbuf)[-6:])
            yield dict(t="error", message=(err or f"Hermes wurde mit Fehlercode {rc} beendet.")[:500])
            return
        if not text_seen:
            yield dict(t="delta", text="Hermes hat den Auftrag ohne Textantwort beendet.")
        yield dict(t="complete", session_id=emitted_session or session_id,
                   ms=_mono_ms() - started)
    finally:
        try:
            if raw:
                raw.close()
        except Exception:
            pass
        if proc.poll() is None:
            proc.terminate()
        with _ACTIVE_LOCK:
            if _ACTIVE_PROC is proc:
                _ACTIVE_PROC = None


def run_mock(message, session_id=None, system=None):
    ok, detail = _can_launch_hermes()
    yield dict(t="error", message=("Hermes ist aus dem Dashboard nicht erreichbar. "
                                  "Bitte HERMES_CMD oder den Hermes-Aufruf des Servicebenutzers prüfen. "
                                  f"Diagnose: {detail[:240]}"))


def run(message, session_id=None, system=None):
    if runtime_kind() != "hermes":
        yield from run_mock(message, session_id, system)
        return
    try:
        yield from run_hermes(message, session_id, system)
    except Exception as e:  # noqa: BLE001
        yield dict(t="error", message=f"Hermes-Kern konnte nicht gestartet werden: {e}")
