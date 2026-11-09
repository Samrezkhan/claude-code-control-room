# How the Control Room was built

Notes for anyone who wants to build their own version or change this one.

## The problem

Running several Claude Code projects at once, the owner lost track: which chat was doing what, what was waiting for
an answer, what had quietly stalled. Asking each chat for a summary meant reading long replies every morning.
Existing tools list chat sessions; none showed the work itself as a tree you can open like folders, with what
needs you at the top.

## Three decisions that shaped it

1. **Each project writes its own status; the dashboard only reads.** A project's own Claude knows its work best,
   so it keeps `docs/status.json` (see `schema.md`). The dashboard never reads a project's chats or files beyond
   that one file and the files a status links to. Projects stay separate: a client project and a personal project
   can sit side by side on the page without either chat ever seeing the other.
2. **Hooks give live state for free.** Claude Code hooks (`UserPromptSubmit`, `PostToolUse`, `Notification`,
   `Stop`) write a tiny file saying working, waiting or finished. No model call, no polling of chats. A
   `SessionStart` hook starts the server and tells each new session to keep its status file.
3. **No API, no build step, no dependencies.** One Python file (standard library only) and one HTML file. It runs on
   any machine that has Python. Talking to a project runs that project's own Claude Code on your normal plan.

## The page

- **Exception first.** The top line answers "does anything need me?" in one sentence. Then "Do these first": the
  three most important open items, from the top project and anything marked Now.
- **Three columns**: Completed (with when, from the change history the server records), In progress, Pending
  (needs you, stuck, on hold, not started).
- **Folders.** Every project opens as a tree; a stuck or waiting task opens to say why and what to do, with a
  reply box and a microphone right there.
- **A trail at the top** (All projects › Pending › project › folder › task) so you can always get back.
- **Priority** by dragging projects into order, and Now / Soon / Later on single tasks.
- **Design**: white, one legible typeface, colour spent only on state (green done, blue working, amber needs you,
  red stuck). Built with a design-review pass that checks contrast, motion, focus states and common
  "generated-looking" patterns.

## Talking to a project

The microphone uses the browser's own speech recognition (Chrome and Edge), so it costs nothing. A message is
queued for its project. If that project's chat is open, a hook hands the message in at its next step and the chat
answers back with `reply.py`. If no chat is open, the server starts that project's Claude Code in the background
(`claude -p --resume <session>` in the project folder) and shows the reply. Only the page itself can send: every
request needs a key the server makes at start and gives only to its own page, so other websites cannot use it.

## Ideas not built yet

- A phone view over the local network (it would need a password first).
- Notifications when something becomes stuck.
- Reading costs and token use per project.
