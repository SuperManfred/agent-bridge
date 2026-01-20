# Agent Bridge Init

Copy-paste this into any agent session to connect it to the bridge.

## Quick Start (copy-paste ready)

```
You're joining an Agent Bridge multi-agent session.

## Setup (do this first)

Start the bridge server and coordinator in background:

```bash
cd /Users/MN/GITHUB/.agent-bridge && python server.py &
cd /Users/MN/GITHUB/.agent-bridge && python coordinator.py &
```

## Bridge Connection

- **Endpoint**: http://localhost:5111
- **Thread**: {THREAD_ID}
- **Your participant id**: {YOUR_PARTICIPANT_ID}
- **Your profile**: {YOUR_CLIENT} / {YOUR_MODEL} (optional: {YOUR_NICKNAME}, roles: {YOUR_ROLES})

## Protocol

**Every turn, check the bridge FIRST before doing anything else:**

```bash
curl -s "http://localhost:5111/threads/{THREAD_ID}/events" | tail -c 2000
```

**Send messages to the bridge, not just terminal:**

```bash
curl -X POST http://localhost:5111/threads/{THREAD_ID}/events \
  -H "Content-Type: application/json" \
  -d '{"type":"message","from":"{YOUR_PARTICIPANT_ID}","to":"all","content":"your message","meta":{}}'
```

**Register your profile + presence (ephemeral):**

```bash
curl -X POST http://localhost:5111/threads/{THREAD_ID}/presence \
  -H "Content-Type: application/json" \
  -d '{"from":"{YOUR_PARTICIPANT_ID}","state":"listening","details":{"client":"{YOUR_CLIENT}","model":"{YOUR_MODEL}","nickname":"{YOUR_NICKNAME}","roles":["{ROLE_1}","{ROLE_2}"]}}'
```

## Rules

- Check bridge -> Read new messages -> Respond via bridge -> Then do any work
- Keep responses concise
- Prefer explicit targeting: set `to="<participant-id>"` when you want a specific participant to respond
- Mentions: `to="all"` + `@...` can also target (human mentions are enabled by default; non-human mentions require an explicit thread control)
```

Replace `{THREAD_ID}` and `{YOUR_PARTICIPANT_ID}` (and profile fields) before pasting.

---

## Reference

### Agent identifiers

In v1 intent, participants are identified by `participant_id` plus a profile (client/model/nickname/roles). Legacy ids still exist (e.g. `claude-code`, `codex`, `user`).

### Event schema

```json
{
  "id": "ulid",
  "ts": "ISO-8601",
  "thread": "thread-id",
  "type": "message|control|task|result|presence",
  "from": "agent-id",
  "to": "all|agent-id",
  "content": "string or object",
  "meta": {"reply_to": "event-id", "tags": []}
}
```

### Targeting rules

- If you are not the intended target (`to`), do not respond unless explicitly prodded.
- If you are prodded, respond once with your best contribution.

### Control signals

- `mute` - do not auto-respond while muted
- `prod` - respond once with your contribution
- `done` - signal you are finished with your part

### Safety

- Never include secrets or local credentials.
- Do not edit files unless explicitly tasked.
