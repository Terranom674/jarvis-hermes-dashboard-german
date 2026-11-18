"""
JARVIS-Befehlszentrale für den vorhandenen Hermes Agent.

Local commands keep the HUD fast for mission control/status while prompts and
unknown slash commands are handed to Hermes Agent. Hermes-native tool access comes
from the runtime subprocess (`hermes chat -q ...`) using the configured profile.
"""
import json
import os
import pathlib
import re
import shlex
import shutil
import subprocess
import threading
import time
import uuid

ROOT = pathlib.Path(__file__).resolve().parent
STATE_FILE = pathlib.Path(os.environ.get("JARVIS_STATE", ROOT / "state.json"))
_LOCK = threading.Lock()
_DEFAULT = {"profile": [], "goal": "", "personality": "", "tasks": [], "missions": []}


def _load_unlocked():
    try:
        d = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return {**_DEFAULT, **d}
    except (OSError, json.JSONDecodeError):
        return dict(_DEFAULT)


def load():
    with _LOCK:
        return _load_unlocked()


def _save_unlocked(d):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    temp = STATE_FILE.with_name(f".{STATE_FILE.name}.{uuid.uuid4().hex}.tmp")
    try:
        temp.write_text(json.dumps(d, indent=2) + "\n", encoding="utf-8")
        os.replace(temp, STATE_FILE)
    finally:
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass


def save(d):
    with _LOCK:
        _save_unlocked(d)


def update_state(mutator):
    """Apply one read-modify-write transaction without losing concurrent updates."""
    with _LOCK:
        d = _load_unlocked()
        result = mutator(d)
        _save_unlocked(d)
        return result


def context_block():
    d = load()
    out = []
    if d["profile"]:
        out.append("## Benutzerprofilnotizen aus JARVIS\n" + "\n".join(f"- {x}" for x in d["profile"][-40:]))
    if d["goal"]:
        out.append(f"## Dauerhaftes Ziel\n{d['goal']}\nBerücksichtige es, wenn es zur Anfrage passt.")
    if d["personality"]:
        out.append(f"## Tonfallvorgabe\n{d['personality']}\nBerücksichtige den gewünschten Tonfall.")
    open_tasks = [t for t in d["tasks"] if not t.get("done")]
    if open_tasks:
        out.append("## Auftragsliste\n" + "\n".join(f"- {t['text']}" for t in open_tasks[:20]))
    return "\n\n".join(out)


JOBS = {}
_JOB_LOCK = threading.Lock()


def start_background(mission, runner):
    jid = uuid.uuid4().hex[:8]
    with _JOB_LOCK:
        JOBS[jid] = {"id": jid, "status": "running", "mission": mission,
                     "result": "", "started": time.time(), "finished": None}
    update_state(lambda d: d["missions"].append(
        {"id": jid, "mission": mission, "status": "running", "at": time.time()}))

    def _work():
        text = ""
        status = "done"
        try:
            for ev in runner(mission):
                if ev.get("t") == "delta":
                    text += ev["text"]
                elif ev.get("t") == "error":
                    status = "failed"
                    text = text or ("Fehlgeschlagen: " + str(ev.get("message", ""))[:260])
        except Exception as e:  # noqa: BLE001
            status = "failed"
            text = f"Fehlgeschlagen: {e}"[:260]
        with _JOB_LOCK:
            JOBS[jid].update(status=status, result=text.strip(), finished=time.time())
        def finish(d2):
            for item in d2.get("missions", []):
                if item.get("id") == jid:
                    item.update(status=status, finished=time.time(), result=text.strip()[:500])
        update_state(finish)

    threading.Thread(target=_work, daemon=True).start()
    return jid


def jobs_snapshot():
    with _JOB_LOCK:
        return [dict(j) for j in JOBS.values()]


def take_finished():
    with _JOB_LOCK:
        done = [dict(j) for j in JOBS.values() if j["status"] in ("done", "failed")]
        for j in done:
            JOBS.pop(j["id"], None)
        return done


_ALIASES = {
    "neu": "new", "profil": "profile", "ziel": "goal",
    "tonfall": "personality", "aufgaben": "kanban",
    "auftrag": "mission", "auftraege": "missions", "aufträge": "missions",
    "hintergrund": "background", "werkzeuge": "tools",
    "werkzeugsaetze": "toolsets", "werkzeugsätze": "toolsets",
    "verbindungen": "connectors", "verbinden": "connect",
    "befehle": "commands", "hilfe": "help", "leeren": "clear",
}
_CMD = re.compile(r"^\s*/([a-zA-ZäöüÄÖÜß]+)\b\s*(.*)$", re.I | re.S)
_KNOWN_COMMANDS = set(
    "new profile goal personality kanban mission missions background tools toolsets "
    "connectors connect status commands help browser clear".split()
)


def _hermes_command(*args):
    configured = os.environ.get("HERMES_CMD", "").strip()
    if configured:
        return shlex.split(configured) + list(args)
    executable = shutil.which("hermes")
    if executable:
        return [executable, *args]
    return ["python3", "-m", "hermes_cli.main", *args]


def _shell(cmd, timeout=25):
    try:
        p = subprocess.run(cmd, text=True, cwd=os.getcwd(), stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, timeout=timeout)
        return (p.stdout or p.stderr or "").strip()[:3500]
    except Exception as e:  # noqa: BLE001
        return f"Nicht verfügbar: {e}"


def _commands_reply():
    return """JARVIS-Kurzbefehle – deutsche und ursprüngliche Namen:
/neu oder /new – neues Gespräch beginnen
/ziel <Text> – Ziel speichern; /ziel status oder /ziel löschen
/profil <Info> – zusätzliche Profilnotiz speichern
/tonfall <Beschreibung> – Sprachstil anpassen
/aufgaben [Aufgabe] – Auftragsliste ansehen oder Aufgabe eintragen
/auftrag [Aufgabe] – wie /aufgaben
/hintergrund <Auftrag> – Hermes im Hintergrund beauftragen
/werkzeuge – aktivierte Hermes-Werkzeuge auflisten
/werkzeugsaetze – Hermes-Werkzeugsätze abfragen
/verbindungen – vorhandene Hermes-Anbindungen erläutern
/verbinden <Dienst> – Verbindung eines Dienstes mit Hermes erklären
/status – JARVIS-Status anzeigen
/browser <Auftrag> – Browser-Auftrag ausführen
/leeren – Antwortanzeige leeren
/hilfe oder /befehle – Übersicht anzeigen

Alle bisherigen englischen Befehle bleiben verwendbar.
Normaler Text geht direkt an Hermes."""


def handle(message, runner=None):
    m = _CMD.match(message or "")
    if not m:
        return None
    raw, arg = m.group(1).lower(), m.group(2).strip()
    cmd = _ALIASES.get(raw, raw)
    if cmd not in _KNOWN_COMMANDS:
        return None
    d = load()

    if cmd in ("help", "commands"):
        return dict(message=None, reply=_commands_reply(), note="Befehle angezeigt")

    if cmd == "clear":
        return dict(message=None, reply="Antwortbereich geleert. Das Gespräch bleibt erhalten.",
                    note="Anzeige geleert")

    if cmd == "new":
        return dict(fresh=True,
                    message=arg or "Beginne ein neues Gespräch. Begrüße mich kurz und natürlich auf Deutsch.",
                    note="Neues Hermes-Gespräch")

    if cmd == "status":
        profile = os.environ.get("HERMES_PROFILE", os.environ.get("JARVIS_PROFILE", "default"))
        audio = os.environ.get("JARVIS_AUDIO_BACKEND", "auto")
        return dict(message=None,
                    reply=f"JARVIS ist erreichbar. Hermes-Profil: {profile}. "
                          f"Sprachmodus: {audio}. Arbeitsordner: {os.getcwd()}",
                    note="Status abgerufen")

    if cmd in ("tools", "toolsets"):
        if cmd == "tools":
            out = _shell(_hermes_command("tools", "list"))
            reply = out or ("Hermes hat keine Werkzeugliste geliefert. "
                            "Bitte HERMES_CMD und hermes tools list prüfen.")
            return dict(message=None, reply=reply, note="Hermes-Werkzeuge angezeigt")
        return dict(message=(
            "Welche Hermes-Werkzeuge, Werkzeugsätze und externen Verbindungen sind "
            "für mein aktives Profil verfügbar? Nenne auch den Browserstatus. "
            "Antworte bitte auf Deutsch."
        ), note="Werkzeugsätze abgefragt")

    if cmd == "connectors":
        return dict(message=None, note="Hermes-Verbindungen erläutert", reply=(
            "Die JARVIS-Oberfläche verwendet dein bereits eingerichtetes Hermes-Profil. "
            "Externe Dienste und MCP-Server werden in Hermes verbunden; "
            "hier sind keine zweiten Zugangsdaten nötig.\n\n"
            "Verwaltung in Hermes über hermes tools, hermes mcp und vorhandene Skills. "
            "Danach /werkzeuge oder /werkzeugsaetze zur Übersicht verwenden."
        ))

    if cmd == "connect":
        target = (arg or "einen externen Dienst").strip()
        return dict(message=(
            f"Erkläre auf Deutsch, wie ich {target} mit dem bestehenden Hermes Agent "
            "verbinden kann. Nenne nur tatsächlich vorhandene Hermes-Befehle, "
            "MCP-Schnittstellen oder Skills. Keine zweite Anmeldung im Dashboard."
        ), note=f"Verbindungshilfe: {target[:45]}")

    if cmd == "browser":
        task = arg or "prüfe, welche Browserwerkzeuge Hermes zur Verfügung stehen"
        return dict(
            message=f"Nutze die in Hermes vorhandenen Browserwerkzeuge, falls verfügbar: {task}",
            note="Browserauftrag gestartet",
        )

    if cmd == "profile":
        if not arg:
            facts = d["profile"]
            return dict(message=None,
                        reply="\n".join(f"- {x}" for x in facts[-20:])
                              if facts else "Hier sind noch keine zusätzlichen Profilnotizen gespeichert.",
                        note="Profilnotizen angezeigt")
        update_state(lambda state: state["profile"].append(arg))
        return dict(message=(
            f'Der Nutzer hat diese zusätzliche Profilnotiz gespeichert: "{arg}". '
            "Bestätige das kurz auf Deutsch."
        ), note=f"Profilnotiz gespeichert: {arg[:50]}")

    if cmd == "goal":
        if arg.lower() in ("clear", "löschen", "loeschen"):
            update_state(lambda state: state.__setitem__("goal", ""))
            return dict(message=None, reply="Dauerhaftes Ziel gelöscht.", note="Ziel gelöscht")
        if not arg or arg.lower() == "status":
            return dict(message=None,
                        reply=d["goal"] or "Noch kein dauerhaftes Ziel festgelegt.",
                        note="Ziel angezeigt")
        update_state(lambda state: state.__setitem__("goal", arg))
        return dict(message=(
            f'Der Nutzer hat dieses dauerhafte Ziel festgelegt: "{arg}". '
            "Bestätige es kurz auf Deutsch."
        ), note=f"Ziel gespeichert: {arg[:50]}")

    if cmd == "personality":
        if not arg:
            return dict(message=None,
                        reply=d["personality"] or "Standardmäßiger JARVIS-Tonfall aktiv.",
                        note="Tonfall angezeigt")
        update_state(lambda state: state.__setitem__("personality", arg))
        return dict(message=(
            f'Der Nutzer wünscht diesen Tonfall: "{arg}". '
            "Bestätige die Änderung mit einem kurzen deutschen Satz."
        ), note=f"Tonfall geändert: {arg[:50]}")

    if cmd in ("kanban", "mission", "missions"):
        if arg:
            update_state(lambda state: state["tasks"].append(
                {"text": arg, "done": False, "at": time.time()}))
            return dict(message=(
                f'Eintrag zur JARVIS-Auftragsliste hinzugefügt: "{arg}". '
                "Bestätige die Aufnahme kurz auf Deutsch."
            ), note=f"Aufgabe gespeichert: {arg[:50]}")
        open_tasks = [t["text"] for t in d["tasks"] if not t.get("done")]
        if not open_tasks:
            return dict(message=None, reply="Die Auftragsliste ist leer.", note="Auftragsliste leer")
        return dict(message=None,
                    reply="Offene Aufgaben:\n" + "\n".join(f"- {t}" for t in open_tasks),
                    note=f"Aufgaben angezeigt: {len(open_tasks)}")

    if cmd == "background":
        if not arg:
            return dict(message=None, reply="Bitte nenne einen konkreten Auftrag.",
                        note="Auftrag fehlt")
        if runner is None:
            return dict(message=None, reply="Hintergrundaufträge sind nicht verfügbar.",
                        note="Hintergrund nicht verfügbar")
        jid = start_background(arg, runner)
        return dict(message=None,
                    reply=f"Hermes-Hintergrundauftrag {jid} gestartet. "
                          "Der Abschluss wird im Dashboard gemeldet.",
                    note=f"Auftrag gestartet: {arg[:50]}")

    return None
