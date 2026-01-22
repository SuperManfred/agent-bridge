# API (current v0 + direction)

This repo currently implements a small HTTP server plus a minimal browser UI.

## Current v0 endpoints (implemented)

Evidence is in `server.py`.

### Health

- `GET /ping` — returns status and version
  - Evidence: `server.py:321`

### Threads (rooms)

- `GET /threads` — list threads index
  - Evidence: `server.py:330`
- `POST /threads` — create a new thread and emit a `thread.created` event
  - Evidence: `server.py:335`

Thread storage:
- Thread event log: `conversations/threads/<thread_id>.jsonl`
  - Evidence: `server.py:107`
- Thread index: `conversations/index.json`
  - Evidence: `server.py:40`

### Thread events

- `GET /threads/<thread_id>/events?since=<ts>`
  - Evidence: `server.py:350`
- `POST /threads/<thread_id>/events`
  - Evidence: `server.py:360`

### Thread state (derived)

- `GET /threads/<thread_id>/state`
  - Evidence: `server.py:355`

Response shape (partial):

```json
{
  "thread": "thread-id",
  "state": {
    "paused": false,
    "muted": ["participant-id"],
    "discussion": {"on": false, "allow_agent_mentions": false},
    "participants": {
      "invited": [
        {
          "id": "participant-id",
          "profile": {"client": "codex", "model": "gpt-5.1-codex", "roles": ["planner"], "nickname": "Echo"},
          "invited_by": "participant-id",
          "invited_at": "ISO-8601"
        }
      ]
    }
  }
}
```

Notes:
- Invited participants are derived from `control.invite` / `control.uninvite` authored by any participant.
  - Evidence: `server.py:156`
- `mute`, `pause`, and `discussion` controls remain authoritative from `from="user"` only.
  - Evidence: `server.py:194`

### Thread event streaming (SSE)

- `GET /threads/<thread_id>/events/stream?since=<ts>`
  - Evidence: `server.py:393`

SSE payload:
- Each SSE message uses `data: <json>\n\n`.
  - Evidence: `server.py:142`

### Thread presence (ephemeral)

- `GET /threads/<thread_id>/presence`
  - Evidence: `server.py:405`
- `POST /threads/<thread_id>/presence`
  - Evidence: `server.py:409`

Notes:
- Presence is stored in memory with a TTL and is not appended to the thread log by default.
- `details` may include participant profile fields like `{client, model, nickname, roles}`.

### Legacy daily message log (removed)

The non-threaded “daily conversation” endpoints (`/message`, `/messages`, `/latest`, `/broadcast`) have been removed in favor of thread events.

### Suggestions

Suggestions are explicitly “about improving the bridge itself”:
- `POST /suggest`, `GET /suggestions`
  - Evidence: `server.py:453`, `server.py:467`

## Current UI (v0)

The browser UI is a thread/room viewer + sender with SSE fallback to polling.

- Uses EventSource on `/threads/<id>/events/stream` and falls back to polling on errors.
  - Evidence: `ui/app.js:145`
- UI supports inviting participants (persists `control.invite`) and targeting invited participants via the `to` dropdown.
- Composer supports sending `to` (defaults to `all`); use `to="codex"` / `to="claude-code"` for coordinator-triggered replies, or use `to="all"` with `@mentions` when enabled.

## Direction (v1 intent)

Open questions to resolve in spec before changing APIs:
- Whether to standardize event shape across all endpoints (thread + legacy).
