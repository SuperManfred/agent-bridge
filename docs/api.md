# API (current v0 + direction)

This repo currently implements a small HTTP server plus a minimal browser UI.

## Current v0 endpoints (implemented)

Evidence is in `server.py`.

### Health

- `GET /ping` — returns status and version
  - Evidence: `server.py:198`

### Threads (rooms)

- `GET /threads` — list threads index
  - Evidence: `server.py:223`
- `POST /threads` — create a new thread and emit a `thread.created` event
  - Evidence: `server.py:228`

Thread storage:
- Thread event log: `conversations/threads/<thread_id>.jsonl`
  - Evidence: `server.py:116`
- Thread index: `conversations/index.json`
  - Evidence: `server.py:34`

### Thread events

- `GET /threads/<thread_id>/events?since=<ts>`
  - Evidence: `server.py:243`
- `POST /threads/<thread_id>/events`
  - Evidence: `server.py:249`

### Thread event streaming (SSE)

- `GET /threads/<thread_id>/events/stream?since=<ts>`
  - Evidence: `server.py:262`

SSE payload:
- Each SSE message uses `data: <json>\n\n`.
  - Evidence: `server.py:175`

### Legacy message log (daily file)

There is also a non-threaded “daily conversation” log:
- `POST /message`, `GET /messages`, `GET /latest`, `POST /broadcast`
  - Evidence: `server.py:208`, `server.py:275`, `server.py:285`, `server.py:293`

Note:
- This is conceptually separate from threads, and may be deprecated once threads cover the intended use.

### Suggestions

Suggestions are explicitly “about improving the bridge itself”:
- `POST /suggest`, `GET /suggestions`
  - Evidence: `server.py:337`, `server.py:351`

## Current UI (v0)

The browser UI is a thread/room viewer + sender with SSE fallback to polling.

- Uses EventSource on `/threads/<id>/events/stream` and falls back to polling on errors.
  - Evidence: `ui/app.js:145`
- Composer supports sending `to` (defaults to `all`); use `to="codex"` / `to="claude-code"` for coordinator-triggered replies.

## Direction (v1 intent)

Open questions to resolve in spec before changing APIs:
- Whether to collapse `/message(s)` into thread events entirely.
- Whether to standardize event shape across all endpoints (thread + legacy).
