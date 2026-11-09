"""Answer in the Control Room: python reply.py <message id> "<reply>" """
import json, os, pathlib, sys, time

d = pathlib.Path(os.environ.get("CONTROL_ROOM_LIVE", str(pathlib.Path.home() / ".control-room")))
mid, text = sys.argv[1], " ".join(sys.argv[2:]).strip()
f = d / "messages.json"
ms = json.loads(f.read_text(encoding="utf-8"))
hit = [m for m in ms if m["id"] == mid]
for m in hit:
    m.update(status="done", reply=text[:4000], note="", finished=time.time())
f.write_text(json.dumps(ms[-300:]), encoding="utf-8")
print("reply saved" if hit else "no message with that id")
