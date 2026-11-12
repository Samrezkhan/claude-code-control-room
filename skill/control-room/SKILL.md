---
name: control-room
description: Keep this project's docs/status.json current for the Control Room dashboard. Use at the start of work in any project, at every milestone (something starts, finishes, gets stuck or needs the owner), and before ending a session.
---

# Keep the Control Room current

The owner watches every project on one local page (the Control Room, http://localhost:9999). This project appears
there from its own `docs/status.json`. The schema is in `docs/schema.md` of the Control Room repository.

## When

- **First time in a project:** if `docs/status.json` does not exist, build it from what you know of the project and
  this conversation: what is done, what is running, what waits on the owner, what is stuck and why.
- **At every milestone:** something starts, finishes, gets stuck, or needs the owner. Update the file then, not at
  the end of the day.
- **Before the session ends.**

## How

1. A tree of `nodes`: workstreams as folders, tasks inside them. Keep names short and plain.
2. When the owner gives a new instruction, rewrite the affected part of the status in the same turn: replaced work becomes `stopped` with a note saying what replaced it (or is removed), the new steps go in order, the step that waits on their approval is `waiting`, and the steps after it are `planned` with a note that they start after their yes.
3. Set `updated` (e.g. `2026-11-12T14:30`) on a task whenever its state, note or detail changes, and `added` when you put a new task on the list, so the owner can tell what moved after their last instruction.
2. Every task has a `state`. Use `waiting` only when the owner must act, and say exactly what in `detail`.
   Use `stuck` only for a real block, and say why and what happens next.
3. Add `links` for every output the owner can look at (a video, a picture, a page, a report), with paths relative
   to the project folder. Never link secrets.
4. Put the latest two or three changes in `newSince`.
5. Write only this project's own file. Never read or write another project's files.

## Messages from the Control Room

The owner can speak or type to a project from the Control Room. When such a message reaches you (it arrives marked
"MESSAGE FROM THE OWNER THROUGH THE CONTROL ROOM"), act on it as if it had been typed here, then answer it with the
`reply.py` command given in the message so the answer shows in the Control Room.
