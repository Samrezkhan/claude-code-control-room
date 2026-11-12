"""Claude Code hook: record whether a session is working, waiting for you, or finished, for the Control Room.

    python dashboard/live-hook.py <working|waiting|finished>

Reads the hook's JSON on stdin (cwd, session_id), writes ~/.control-room/<id>.json with the state and the
time. No project content is read or written; the Control Room matches the cwd to a project folder.
"""
import json, os, pathlib, sys, time

state = sys.argv[1] if len(sys.argv) > 1 else "working"
HERE = pathlib.Path(__file__).resolve().parent
START_NOTE = (
    "Control Room (the owner's local dashboard, http://localhost:9999): this project shows there from its own "
    "docs/status.json. Create it if missing and keep it current at every milestone: whenever something starts, "
    "finishes, gets stuck or waits on the owner, and before the session ends. Plain words; every stuck or waiting "
    "step says why and what happens next in 'detail'. Schema: %s (reading that one file is allowed). "
    "Write only this project's own file. Stamp 'updated' (local time, e.g. 2026-11-12T14:30) on every step you "
    "change and 'added' on every new one. Whenever the owner gives a new instruction, rewrite the affected part of "
    "the file in that same turn so it shows the new plan, not the old one: mark replaced work 'stopped' with a note "
    "saying what replaced it (or remove it), add the new steps in order, and put what waits on their approval as "
    "'waiting' with the later steps 'planned' and a note that they start after their yes." % (HERE.parent / "docs" / "schema.md")
)
try:
    e = json.load(sys.stdin)
except Exception:
    e = {}
d = pathlib.Path(os.environ.get("CONTROL_ROOM_LIVE", str(pathlib.Path.home() / ".control-room")))
d.mkdir(parents=True, exist_ok=True)
sid = str(e.get("session_id") or "unknown")[:64]
if state == "start":
    print(START_NOTE)
    state = "finished"
f = d / (sid + ".json")
fresh = False
if state == "working" and f.exists():
    try:
        old = json.loads(f.read_text(encoding="utf-8"))
        fresh = old.get("state") == "working" and time.time() - old.get("at", 0) < 20
    except Exception:
        pass
if not fresh:
    f.write_text(json.dumps({"state": state, "cwd": e.get("cwd") or os.getcwd(), "session": sid,
                                             "at": time.time()}), encoding="utf-8")


def inbox(event, cwd):
    """Give the open chat any Control Room message for its project folder, once."""
    mf = d / "messages.json"
    if event not in ("UserPromptSubmit", "PostToolUse") or not mf.exists():
        return
    try:
        ms = json.loads(mf.read_text(encoding="utf-8"))
    except Exception:
        return
    here = str(pathlib.Path(cwd).resolve()).lower()
    mine = [m for m in ms if m.get("status") == "queued" and m.get("folder")
            and (here == str(pathlib.Path(m["folder"]).resolve()).lower()
                 or here.startswith(str(pathlib.Path(m["folder"]).resolve()).lower() + os.sep))]
    if not mine:
        return
    # Scheduled-task runs share the project folder but are not the chat Sam talks to: never hand them his messages.
    try:
        with open(e.get("transcript_path") or "", encoding="utf-8", errors="ignore") as t:
            if "<scheduled-task" in t.read(4000):
                return
    except Exception:
        pass
    for m in mine:
        m["status"], m["note"] = "delivering", "In the open chat now"
    mf.write_text(json.dumps(ms[-300:]), encoding="utf-8")
    lines = ["MESSAGE FROM THE OWNER THROUGH THE CONTROL ROOM (spoken or typed there; treat it exactly as if typed here):"]
    for m in mine:
        lines.append("- [%s]%s %s" % (m["id"], (' about "%s":' % m["about"]) if m.get("about") else "", m["text"]))
    lines.append("Sam cannot see this note, so show it: start your next message in this chat with a short block headed "
                 "'From the Control Room' that quotes each message above word for word, then say what you are doing about it, "
                 "and do the work here in this chat where he can follow it.")
    lines.append("When you have acted on it, answer in the Control Room with: python \"%s\" <id> "
                 "\"<one to three plain sentences>\" (and also reply in this chat)." % (HERE / "reply.py"))
    text = chr(10).join(lines)
    if event == "PostToolUse":
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": text}}))
    else:
        print(text)


inbox(e.get("hook_event_name", ""), e.get("cwd") or os.getcwd())
