"""Install the Control Room hooks into Claude Code, and optionally start it with your computer.

    python install.py              add the hooks to ~/.claude/settings.json (a backup is written first)
    python install.py --autostart  also start the Control Room when you log in (Windows, macOS, Linux)
    python install.py --name Alex  the name shown in the greeting
    python install.py --uninstall  remove everything this installer added

The hooks only write small state files to ~/.control-room (working / waiting / finished, the folder, the time).
They read nothing from your projects and send nothing anywhere.
"""
import argparse
import json
import os
import pathlib
import shutil
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
PY = sys.executable
SERVER = HERE / "server.py"
HOOK = HERE / "live-hook.py"
MARK = str(HERE).replace("\\", "/")


def q(p):
    return '"%s"' % str(p).replace("\\", "/")


def hooks(name):
    serve = "%s %s --detach --open%s" % (q(PY), q(SERVER), (" --name %s" % q(name)) if name else "")
    h = lambda state: {"type": "command", "command": "%s %s %s" % (q(PY), q(HOOK), state), "timeout": 5}
    return {
        "SessionStart": [{"hooks": [{"type": "command", "command": serve, "timeout": 10}, h("start")]}],
        "UserPromptSubmit": [{"hooks": [h("working")]}],
        "PostToolUse": [{"matcher": "*", "hooks": [h("working")]}],
        "Notification": [{"hooks": [h("waiting")]}],
        "Stop": [{"hooks": [h("finished")]}],
    }


def ours(group):
    return any(MARK in str(x.get("command", "")).replace("\\", "/") for x in group.get("hooks", []))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--autostart", action="store_true")
    ap.add_argument("--uninstall", action="store_true")
    ap.add_argument("--name", default="")
    a = ap.parse_args()

    settings = pathlib.Path.home() / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True, exist_ok=True)
    data = json.loads(settings.read_text(encoding="utf-8")) if settings.exists() else {}
    if settings.exists():
        backup = settings.with_name("settings.json.bak-%d" % int(time.time()))
        shutil.copy2(settings, backup)
        print("backup:", backup)

    all_hooks = data.setdefault("hooks", {})
    for event in list(all_hooks):  # take out any earlier copy of ours
        all_hooks[event] = [g for g in all_hooks[event] if not ours(g)]
        if not all_hooks[event]:
            del all_hooks[event]
    if not a.uninstall:
        for event, groups in hooks(a.name).items():
            all_hooks.setdefault(event, []).extend(groups)
    if not all_hooks:
        data.pop("hooks", None)
    settings.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(("removed" if a.uninstall else "installed") + " hooks in", settings)

    if a.autostart or a.uninstall:
        autostart(a.uninstall, a.name)
    if not a.uninstall:
        print("\nOpen http://localhost:9999 (Chrome and Edge also take http://control.localhost:9999).")
        print("It starts by itself the next time a Claude Code session starts" +
              (", and when you log in." if a.autostart else "."))


def mine(path):
    """Only touch an autostart entry that starts this copy of the Control Room."""
    try:
        return str(SERVER) in path.read_text(encoding="utf-8", errors="replace").replace('""', '"')
    except Exception:
        return False


def autostart(remove, name):
    pyw = pathlib.Path(PY).with_name("pythonw.exe")
    extra = ' --name "%s"' % name if name else ""
    if sys.platform == "win32":
        startup = pathlib.Path(os.environ["APPDATA"]) / "Microsoft/Windows/Start Menu/Programs/Startup/Control Room.vbs"
        if remove:
            if startup.exists() and mine(startup):
                startup.unlink()
            else:
                print("left alone (not this copy):", startup)
        else:
            exe = pyw if pyw.exists() else pathlib.Path(PY)
            startup.write_text('Set s = CreateObject("WScript.Shell")\r\ns.Run """%s"" ""%s"" --detach%s", 0, False\r\n'
                               % (exe, SERVER, extra.replace('"', '""')), encoding="ascii")
        print(("removed " if remove else "autostart: ") + str(startup))
    elif sys.platform == "darwin":
        plist = pathlib.Path.home() / "Library/LaunchAgents/local.control-room.plist"
        if remove:
            if plist.exists() and mine(plist):
                plist.unlink()
            else:
                print("left alone (not this copy):", plist)
        else:
            args = "".join("<string>%s</string>" % x for x in [PY, str(SERVER), "--detach"] + (["--name", name] if name else []))
            plist.write_text('<?xml version="1.0" encoding="UTF-8"?>\n<plist version="1.0"><dict><key>Label</key>'
                             '<string>local.control-room</string><key>ProgramArguments</key><array>%s</array>'
                             '<key>RunAtLoad</key><true/></dict></plist>\n' % args, encoding="utf-8")
        print(("removed " if remove else "autostart: ") + str(plist))
    else:
        desk = pathlib.Path.home() / ".config/autostart/control-room.desktop"
        if remove:
            if desk.exists() and mine(desk):
                desk.unlink()
            else:
                print("left alone (not this copy):", desk)
        else:
            desk.parent.mkdir(parents=True, exist_ok=True)
            desk.write_text("[Desktop Entry]\nType=Application\nName=Control Room\nExec=%s %s --detach%s\n"
                            % (PY, SERVER, extra), encoding="utf-8")
        print(("removed " if remove else "autostart: ") + str(desk))


if __name__ == "__main__":
    main()
