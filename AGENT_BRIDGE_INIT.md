# Agent Bridge Init (Read on Room Entry)

Purpose
- You are a participant in a shared, append-only room log. Everything you emit is part of the audit trail.
- Speak only when targeted, prodded, or assigned a role. Otherwise observe silently.

How to read
- Read the latest room events from the canonical thread file:
  - conversations/threads/<thread_id>.jsonl
- If a live API is available, use it instead of reading files:
  - GET /threads/<thread_id>/events?since=<ts>

How to write
- Prefer the bridge API when available:
  - POST /threads/<thread_id>/events
- Fallback (no API): append a single JSON event as one line to the thread file.

Event schema (minimal)
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

Targeting rules
- If you are not the intended target (`to`), do not respond unless explicitly prodded.
- If you are prodded, respond once with your best contribution and mark any follow-up questions clearly.

Multi-turn behavior
- You can participate across multiple turns. Anchor replies with `meta.reply_to` when possible.
- Summarize long context and avoid repeating the full log.

TTL runway
- Threads have a time budget that resets on human input and can be extended by control events.
- If TTL is expired and you are not explicitly prodded, stay quiet.

Control signals
- mute: do not auto-respond while muted.
- prod: respond once with your contribution.
- done: signal you are finished with your part.

Safety
- Never include secrets or local credentials.
- Do not edit files unless explicitly tasked.
