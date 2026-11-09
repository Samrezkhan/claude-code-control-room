# The status file: `docs/status.json`

Each project keeps one file, `docs/status.json`, in its own folder. The project's own Claude Code session writes it
and keeps it current. The Control Room only reads it. Nothing else is needed: no database, no API, no account.

```json
{
  "project": "Bakery Website",
  "title": "Bakery Website",
  "summary": "One or two sentences: what this project is.",
  "newSince": ["What changed since the owner last looked"],
  "nodes": [
    {"name": "Pages", "note": "one line", "children": [
      {"name": "Cakes page", "state": "waiting", "priority": "now",
       "note": "photos ready; pick 6 of the 12",
       "detail": "What the owner needs to do, or why it is stuck and what happens next. Shown when the line is opened.",
       "links": [{"label": "Open the photo sheet", "path": "out/cakes-photos.html"}]},
      {"name": "Ordering page", "state": "running", "done": 3, "total": 5}
    ]}
  ]
}
```

| Field | Meaning |
|---|---|
| `nodes` | A tree, like folders. A step with `children` is a folder; a step without is a task. |
| `state` | On tasks: `done`, `running` (being worked on now), `waiting` (needs the owner), `stuck` (blocked; say why in `detail`), `stopped` (on hold on purpose), `planned` (not started). A folder with no `state` takes the most urgent state of what is inside it. |
| `done` / `total` | Draws a progress bar. Without them a folder counts its finished tasks. |
| `priority` | Optional: `now`, `soon` or `later`. The owner's own choice in the Control Room always wins. |
| `detail` | Plain words. For `waiting`: exactly what the owner should do. For `stuck`: why, and what happens next. |
| `links` | Optional files the owner can open: `{"label": "...", "path": "<relative to the project folder>"}` or a full `https://` address. Videos play, pictures and pages open in the browser. Files under `keys/`, `.env`, `.git`, `.ssh` are always refused. |
| `newSince` | Short lines about what changed recently. |

Write plain words. The reader is busy and may be tired: "Needs your go to publish on Thursday" beats "pending approval".
