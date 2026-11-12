"""Project dashboard: one local page for every Claude project.

    python server.py [--port 9999] [--root <folder of projects>] [--name <your name>] [--open]

Finds projects three ways: every folder under --root (one level down) that holds docs/status.json; every folder
Claude Code has been opened in (the folder names under ~/.claude/projects, decoded back to real paths; nothing
inside them is read); and any folder listed one per line in dashboard/projects.txt. A project with no
docs/status.json yet is still shown, as "not set up yet". Serves http://127.0.0.1:9999 (this machine only). Nothing is sent anywhere and
no API is called: each project's own Claude session writes its own docs/status.json; this page only reads them.
Schema: dashboard/README.md.
"""
import argparse, json, pathlib, secrets, shutil, socket, subprocess, sys, threading, time, uuid, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = pathlib.Path(__file__).resolve().parent


import os, re

ENC = lambda name: re.sub(r"[^A-Za-z0-9]", "-", name)
def claude_projects_dir():
    return pathlib.Path(os.environ.get("CONTROL_ROOM_CLAUDE_PROJECTS", pathlib.Path.home() / ".claude" / "projects"))
SKIP_PARTS = {".claude", "appdata", "temp", "tmp", "node_modules", "worktrees"}


def decode(encoded):
    """Turn Claude's encoded folder name (C--Users-me-projects-shop) back into a real path, by walking the disk."""
    m = re.match(r"^([A-Za-z])--(.*)$", encoded)
    if not m:
        return None
    cur, rest = pathlib.Path(m.group(1) + ":/"), m.group(2)
    while rest:
        try:
            kids = sorted((k for k in cur.iterdir() if k.is_dir()), key=lambda k: -len(k.name))
        except Exception:
            return None
        for k in kids:
            e = ENC(k.name)
            if rest == e or rest.startswith(e + "-"):
                cur, rest = k, rest[len(e) + 1:]
                break
        else:
            return None
    return cur


def claude_folders():
    out = []
    cp = claude_projects_dir()
    if cp.is_dir():
        for d in cp.iterdir():
            p = decode(d.name) if d.is_dir() else None
            if p and p.is_dir():
                out.append(p)
    return out


def usable(d, root):
    d = pathlib.Path(d)
    low = [x.lower() for x in d.parts]
    if any(x in SKIP_PARTS for x in low) or len(d.parts) < 2:
        return False
    rp = str(d.resolve()).lower().rstrip("\\/")
    banned = {str(pathlib.Path.home().resolve()).lower()}
    if root:
        banned.add(str(pathlib.Path(root).resolve()).lower())
    return rp not in banned


def project_dirs(root):
    dirs = []
    r = pathlib.Path(root) if root else None
    if r and r.is_dir():
        dirs += [d for d in sorted(r.iterdir()) if d.is_dir() and (d / "docs" / "status.json").exists()]
    found = claude_folders()
    live = pathlib.Path(os.environ.get("CONTROL_ROOM_LIVE", str(pathlib.Path.home() / ".control-room")))
    if live.is_dir():
        for f in live.glob("*.json"):
            try:
                c = json.loads(f.read_text(encoding="utf-8")).get("cwd")
                if c and pathlib.Path(c).is_dir():
                    found.append(pathlib.Path(c))
            except Exception:
                pass
    dirs += [d for d in found if usable(d, root)]
    extra = HERE / "projects.txt"
    if extra.exists():
        for line in extra.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                dirs.append(pathlib.Path(line))
    seen, out = set(), []
    for d in dirs:
        k = str(d.resolve()).lower()
        if k not in seen:
            seen.add(k)
            out.append(d)
    # a folder inside another listed project is part of it, not a project of its own
    keys = [str(d.resolve()).lower() for d in out]
    return [d for d, k in zip(out, keys) if not any(k != o and k.startswith(o + os.sep) for o in keys)]


def collect(root):
    out = []
    for d in project_dirs(root):
        f = d / "docs" / "status.json"
        if not f.exists():
            out.append({"project": d.name, "_folder": str(d), "_missing": True})
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            data.setdefault("project", d.name)
            data["_folder"] = str(d)
            data["_mtime"] = f.stat().st_mtime
        except Exception as e:
            data = {"project": d.name, "_folder": str(d), "_error": "status.json unreadable: %s" % e}
        out.append(data)
    live = pathlib.Path(os.environ.get("CONTROL_ROOM_LIVE", str(pathlib.Path.home() / ".control-room")))
    sessions = []
    if live.is_dir():
        for f in live.glob("*.json"):
            try:
                x = json.loads(f.read_text(encoding="utf-8"))
                if isinstance(x, dict) and x.get("cwd") and x.get("state"):
                    sessions.append(x)
            except Exception:
                pass
    for data in out:
        folder = str(pathlib.Path(data["_folder"]).resolve()).lower()
        mine = [x for x in sessions if str(pathlib.Path(x.get("cwd") or "/").resolve()).lower().startswith(folder)
                and time.time() - x.get("at", 0) < 3 * 86400]
        mine.sort(key=lambda x: -x.get("at", 0))
        data["_sessions"] = mine[:6]
    return out


LOCK = threading.Lock()


def leaves(p):
    out = {}

    def go(nodes, path):
        for n in nodes or []:
            kids = n.get("children") or []
            if kids:
                go(kids, path + [n.get("name", "")])
            else:
                out[" > ".join(path + [n.get("name", "")])] = (n.get("state") or "planned", path, n.get("name", ""))
    go(p.get("nodes"), [])
    return out


def history(projects):
    """Record every step whose state changed since the last look, so the page can show when things got done."""
    live = pathlib.Path(os.environ.get("CONTROL_ROOM_LIVE", str(pathlib.Path.home() / ".control-room")))
    live.mkdir(parents=True, exist_ok=True)
    snap_f, hist_f = live / "snapshot.json", live / "history.jsonl"
    with LOCK:
        try:
            snap = json.loads(snap_f.read_text(encoding="utf-8"))
        except Exception:
            snap = None
        now = {}
        events = []
        for p in projects:
            if p.get("_missing") or p.get("_error"):
                continue
            for k, (st, path, name) in leaves(p).items():
                key = p["project"] + " | " + k
                now[key] = st
                if snap is not None and snap.get(key) != st:
                    events.append({"at": time.time(), "project": p["project"], "path": path, "name": name,
                                   "from": snap.get(key), "to": st})
        if events:
            with hist_f.open("a", encoding="utf-8") as f:
                for e in events:
                    f.write(json.dumps(e) + chr(10))
        if snap != now:
            snap_f.write_text(json.dumps(now), encoding="utf-8")
        try:
            lines = hist_f.read_text(encoding="utf-8").splitlines()[-400:]
            return [json.loads(x) for x in lines if x.strip()]
        except Exception:
            return []



def _iso(v):
    """A date the project wrote itself ("2026-11-12" or "2026-11-12T14:30"), as a timestamp."""
    import datetime
    try:
        s = str(v).strip().replace("Z", "")
        fmt = "%Y-%m-%dT%H:%M" if "T" in s else "%Y-%m-%d"
        return datetime.datetime.strptime(s[:16] if "T" in s else s[:10], fmt).timestamp()
    except Exception:
        return None


def times(projects):
    """When each task was added and when it last changed (state, note, detail or count), for the timeline labels."""
    live = pathlib.Path(os.environ.get("CONTROL_ROOM_LIVE", str(pathlib.Path.home() / ".control-room")))
    live.mkdir(parents=True, exist_ok=True)
    tf, hf = live / "times.json", live / "history.jsonl"
    with LOCK:
        try:
            t = json.loads(tf.read_text(encoding="utf-8"))
        except Exception:
            t = {}
        first = {}
        try:
            for line in hf.read_text(encoding="utf-8").splitlines():
                e = json.loads(line)
                k = e["project"] + "|" + " > ".join(e.get("path", []) + [e.get("name", "")])
                first.setdefault(k, e["at"])
        except Exception:
            pass
        start = min(first.values()) if first else time.time()
        now, dirty, fresh = time.time(), False, not t

        def walk(p, nodes, path):
            nonlocal dirty
            for n in nodes or []:
                kids = n.get("children") or []
                k = p["project"] + "|" + " > ".join(path + [n.get("name", "")])
                fp = "|".join(str(n.get(f, "")) for f in ("state", "note", "detail", "done", "total")) + "|%d" % len(kids)
                r = t.get(k)
                if r is None:
                    if fresh:
                        r = {"added": first.get(k, start), "est": True, "updated": first.get(k, start), "fp": fp}
                    else:
                        r = {"added": now, "est": False, "updated": now, "fp": fp}
                    t[k], dirty = r, True
                elif r.get("fp") != fp:
                    r["fp"], r["updated"], dirty = fp, now, True
                walk(p, kids, path + [n.get("name", "")])

        for p in projects:
            if p.get("_missing") or p.get("_error"):
                continue
            walk(p, p.get("nodes"), [])
        if dirty:
            tf.write_text(json.dumps(t), encoding="utf-8")
        out = {k: {"added": v["added"], "est": v.get("est", False), "updated": v["updated"]} for k, v in t.items()}

        def own(p, nodes, path):
            for n in nodes or []:
                k = p["project"] + "|" + " > ".join(path + [n.get("name", "")])
                a, u = _iso(n.get("added")), _iso(n.get("updated"))
                if k in out:
                    if a:
                        out[k]["added"], out[k]["est"] = a, False
                    if u:
                        out[k]["updated"] = max(u, out[k]["updated"]) if not a else u
                own(p, n.get("children"), path + [n.get("name", "")])

        for p in projects:
            if not (p.get("_missing") or p.get("_error")):
                own(p, p.get("nodes"), [])
        return out

def prefs_file():
    d = pathlib.Path(os.environ.get("CONTROL_ROOM_LIVE", str(pathlib.Path.home() / ".control-room")))
    d.mkdir(parents=True, exist_ok=True)
    return d / "prefs.json"


def read_prefs():
    try:
        return json.loads(prefs_file().read_text(encoding="utf-8"))
    except Exception:
        return {"order": [], "hidden": []}


TOKEN = secrets.token_hex(16)  # new each start; only the page this server serves knows it
PORT = [9999]
NAME = [""]
MSG_LOCK = threading.Lock()


def live_dir():
    d = pathlib.Path(os.environ.get("CONTROL_ROOM_LIVE", str(pathlib.Path.home() / ".control-room")))
    d.mkdir(parents=True, exist_ok=True)
    return d


def read_msgs():
    f = live_dir() / "messages.json"
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return []


def write_msgs(ms):
    (live_dir() / "messages.json").write_text(json.dumps(ms[-300:]), encoding="utf-8")


def update_msg(mid, **kw):
    with MSG_LOCK:
        ms = read_msgs()
        for m in ms:
            if m["id"] == mid:
                m.update(kw)
        write_msgs(ms)


def latest_session(folder):
    """The newest Claude chat that ran in this project's folder, from the live hooks."""
    best = None
    root = str(pathlib.Path(folder).resolve()).lower()
    for f in live_dir().glob("*.json"):
        if f.name in ("snapshot.json", "prefs.json", "messages.json"):
            continue
        try:
            x = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        c = str(pathlib.Path(x.get("cwd") or "/").resolve()).lower()
        if (c == root or c.startswith(root + os.sep)) and (best is None or x.get("at", 0) > best.get("at", 0)):
            best = x
    return best


def deliver_once(root):
    """Hand each queued message to its project's own Claude (one at a time per project), on your own Claude plan."""
    claude = shutil.which("claude")
    with MSG_LOCK:
        ms = read_msgs()
    busy = {m["project"] for m in ms if m.get("status") == "delivering"}
    for m in ms:
        if m.get("status") != "queued" or m["project"] in busy or m.get("retry_at", 0) > time.time():
            continue
        proj = next((x for x in collect(root) if x.get("project") == m["project"]), None)
        if not proj:
            update_msg(m["id"], status="failed", reply="That project folder was not found.")
            continue
        if not claude:
            update_msg(m["id"], status="failed", reply="The claude program was not found on this PC.")
            continue
        sess = latest_session(proj["_folder"])
        if sess and time.time() - sess.get("at", 0) < 600:
            update_msg(m["id"], note="Goes into that project's open chat at its next step")
            continue
        if sess and sess.get("state") == "working" and time.time() - sess.get("at", 0) < 180:
            update_msg(m["id"], note="Waiting for that project's Claude to finish what it is doing")
            continue
        busy.add(m["project"])
        update_msg(m["id"], status="delivering", note="Its Claude is working on it", started=time.time())
        threading.Thread(target=run_one, args=(m, proj["_folder"], claude, sess), daemon=True).start()


def run_one(m, folder, claude, sess):
    about = (" about \"%s\"" % m["about"]) if m.get("about") else ""
    prompt = ("Message from the owner through the Control Room%s (spoken or typed there, not in this chat):\n\n%s\n\n"
              "Act on it exactly as if the owner had typed it here, following this project's own rules. Then update "
              "docs/status.json. End with a reply in one to three plain sentences: it is shown in the Control Room."
              % (about, m["text"]))
    args = [claude, "-p", prompt, "--output-format", "json"]
    if sess and sess.get("session") and sess["session"] != "unknown":
        args += ["--resume", sess["session"]]
    try:
        r = subprocess.run(args, cwd=folder, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=3600, creationflags=0x08000000 if sys.platform == "win32" else 0)
        reply, ok = "", r.returncode == 0
        try:
            j = json.loads(r.stdout)
            reply = str(j.get("result") or "")
            ok = ok and not j.get("is_error")
        except Exception:
            reply = (r.stdout or r.stderr or "").strip()[-1500:]
        if not ok and ("authenticate" in reply.lower() or "login" in reply.lower() or "/login" in reply):
            update_msg(m["id"], status="queued", reply="", retry_at=time.time() + 120,
                       note="Claude on this PC needs a one-time sign-in (run claude, then /login); it sends by itself after")
            return
        update_msg(m["id"], status="done" if ok else "failed", reply=reply[:4000] or "(no reply)",
                   finished=time.time(), note="")
    except subprocess.TimeoutExpired:
        update_msg(m["id"], status="failed", reply="It ran for an hour without finishing; stopped.", note="")
    except Exception as e:
        update_msg(m["id"], status="failed", reply="Could not start: %s" % e, note="")


def delivery_loop(root):
    with MSG_LOCK:  # a restart leaves nothing stuck half-way
        ms = read_msgs()
        for m in ms:
            if m.get("status") == "delivering":
                m["status"], m["note"] = "queued", "Sent again after the Control Room restarted"
        write_msgs(ms)
    while True:
        try:
            deliver_once(root)
        except Exception:
            pass
        time.sleep(10)


class H(BaseHTTPRequestHandler):
    root = ""

    def log_message(self, *a):
        pass

    def send(self, code, body, ctype):
        b = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path.startswith("/api/status"):
            ps = collect(self.root)
            self.send(200, json.dumps({"now": time.time(), "projects": ps, "history": history(ps), "times": times(ps),
                                       "prefs": read_prefs(), "messages": read_msgs()[-120:]}),
                      "application/json")
        elif self.path.startswith("/file?"):
            self.serve_file()
        elif self.path.split("?")[0] in ("/", "/index.html"):
            self.send(200, (HERE / "index.html").read_text(encoding="utf-8").replace("__CR_TOKEN__", TOKEN).replace("__CR_NAME__", NAME[0].replace("\\", "").replace("'", "")),
                      "text/html; charset=utf-8")
        else:
            self.send(404, "not found", "text/plain")


TYPES = {".mp4": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime", ".mp3": "audio/mpeg",
         ".wav": "audio/wav", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif",
         ".webp": "image/webp", ".svg": "image/svg+xml", ".pdf": "application/pdf", ".html": "text/html; charset=utf-8",
         ".md": "text/plain; charset=utf-8", ".txt": "text/plain; charset=utf-8", ".csv": "text/plain; charset=utf-8",
         ".json": "text/plain; charset=utf-8"}
BLOCKED = {"keys", ".env", ".git", ".ssh", "secrets", "credentials"}


def _serve_file(self):
    """Open a file a project's status points at: only inside that project's folder, only viewable types, never keys."""
    from urllib.parse import urlparse, parse_qs
    q = parse_qs(urlparse(self.path).query)
    name, rel = (q.get("project") or [""])[0], (q.get("path") or [""])[0]
    proj = next((x for x in collect(self.root) if x.get("project") == name), None)
    if not proj or not rel:
        return self.send(404, "not found", "text/plain")
    root = pathlib.Path(proj["_folder"]).resolve()
    f = (root / rel).resolve() if not pathlib.Path(rel).is_absolute() else pathlib.Path(rel).resolve()
    low = [x.lower() for x in f.parts]
    if root not in f.parents or any(x in BLOCKED or x.endswith(".env") for x in low) or not f.is_file():
        return self.send(404, "not found (only files inside the project, never keys)", "text/plain")
    ctype = TYPES.get(f.suffix.lower())
    if not ctype:
        return self.send(415, "this kind of file does not open in the browser: " + f.name, "text/plain")
    size = f.stat().st_size
    rng = self.headers.get("Range")
    start, end = 0, size - 1
    if rng and rng.startswith("bytes="):
        a, _, b = rng[6:].partition("-")
        start = int(a or 0)
        end = min(int(b) if b else size - 1, size - 1)
    length = max(0, end - start + 1)
    self.send_response(206 if rng else 200)
    self.send_header("Content-Type", ctype)
    self.send_header("Accept-Ranges", "bytes")
    self.send_header("Content-Length", str(length))
    if rng:
        self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
    self.end_headers()
    with f.open("rb") as fh:
        fh.seek(start)
        left = length
        while left > 0:
            chunk = fh.read(min(1 << 20, left))
            if not chunk:
                break
            try:
                self.wfile.write(chunk)
            except (BrokenPipeError, ConnectionResetError):
                return
            left -= len(chunk)


H.serve_file = _serve_file


def _post(self):
    """Save the owner's order, hidden list and priorities (the only thing the page ever writes)."""
    host = (self.headers.get("Host") or "").split(":")[0].lower()
    origin = (self.headers.get("Origin") or "").lower()
    local = host in ("localhost", "127.0.0.1") or host.endswith(".localhost")
    origin_ok = not origin or any(origin.startswith(x) for x in ("http://localhost:", "http://127.0.0.1:")) or (
        origin.startswith("http://") and origin.split("//")[1].split(":")[0].endswith(".localhost"))
    if not local or not origin_ok or self.headers.get("X-CR-Token") != TOKEN:
        return self.send(403, "refused: only the Control Room page itself may send", "text/plain")
    if self.path == "/api/send":
        try:
            n = min(int(self.headers.get("Content-Length", "0")), 100000)
            d = json.loads(self.rfile.read(n).decode("utf-8"))
            text = str(d.get("text", "")).strip()[:8000]
            proj = str(d.get("project", ""))[:200]
            if not text or not proj:
                return self.send(400, "a project and a message are needed", "text/plain")
            pr = next((x for x in collect(self.root) if x.get("project") == proj), None)
            m = {"id": uuid.uuid4().hex[:12], "at": time.time(), "project": proj,
                 "folder": pr["_folder"] if pr else "",
                 "about": str(d.get("about", ""))[:300], "text": text, "status": "queued", "note": ""}
            with MSG_LOCK:
                ms = read_msgs()
                ms.append(m)
                write_msgs(ms)
            return self.send(200, json.dumps(m), "application/json")
        except Exception as e:
            return self.send(400, "bad request: %s" % e, "text/plain")
    if self.path != "/api/prefs":
        return self.send(404, "not found", "text/plain")
    try:
        n = min(int(self.headers.get("Content-Length", "0")), 100000)
        d = json.loads(self.rfile.read(n).decode("utf-8"))
        clean = {"order": [str(x)[:200] for x in d.get("order", [])][:200],
                 "hidden": [str(x)[:200] for x in d.get("hidden", [])][:200],
                 "prio": {str(k)[:600]: v for k, v in list((d.get("prio") or {}).items())[:500]
                          if v in ("now", "soon", "later")}}
        prefs_file().write_text(json.dumps(clean), encoding="utf-8")
        self.send(200, json.dumps(clean), "application/json")
    except Exception as e:
        self.send(400, "bad request: %s" % e, "text/plain")


H.do_POST = _post


def port_busy(port):
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9999)
    ap.add_argument("--root", default=os.environ.get("CONTROL_ROOM_ROOT", ""),
                    help="optional: a folder whose sub-folders are projects (Claude-opened folders are found anyway)")
    ap.add_argument("--name", default=os.environ.get("CONTROL_ROOM_NAME", ""), help="shown in the greeting")
    ap.add_argument("--open", action="store_true", help="open the browser (only when this call starts the server)")
    ap.add_argument("--claude-projects", help="testing: another ~/.claude/projects folder")
    ap.add_argument("--live", help="testing: another live-state folder")
    ap.add_argument("--detach", action="store_true", help="start the server in the background and return at once")
    a = ap.parse_args()
    url = "http://control.localhost:%d" % a.port
    if port_busy(a.port):
        print("dashboard already running at", url)
        return 0
    if a.detach:
        import subprocess
        exe = pathlib.Path(sys.executable)
        w = exe.with_name("pythonw.exe")
        args = [str(w if w.exists() else exe), str(pathlib.Path(__file__).resolve()), "--port", str(a.port),
                "--root", a.root, "--name", a.name]
        if a.open:
            args.append("--open")
        flags = 0x00000008 | 0x00000200 if sys.platform == "win32" else 0  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        subprocess.Popen(args, creationflags=flags, close_fds=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("dashboard starting at", url)
        return 0
    H.root = a.root
    PORT[0] = a.port
    NAME[0] = a.name[:40]
    if a.claude_projects:
        os.environ["CONTROL_ROOM_CLAUDE_PROJECTS"] = a.claude_projects
    if a.live:
        os.environ["CONTROL_ROOM_LIVE"] = a.live
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), H)
    threading.Thread(target=delivery_loop, args=(a.root,), daemon=True).start()
    print("dashboard at", url)
    if a.open:
        webbrowser.open(url)
    srv.serve_forever()


if __name__ == "__main__":
    sys.exit(main())
