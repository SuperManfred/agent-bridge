# Spec (v1)

This document is normative: it defines intended behavior. Where the current implementation differs, `docs/api.md` describes “v0 behavior”.

## Naming

- This spec uses **thread** (not room) for the conversation container.
- “Orchestrator” is avoided as a primary framing term; automation is described as optional **coordination**.

## Identifiers and timestamps

- `id`: globally unique per event (ULID recommended).
- `ts`: ISO-8601 timestamp (event creation time).
- `thread`: thread identifier (opaque string, ULID recommended).

## Event envelope

Minimum recommended event fields:

```json
{
  "id": "ulid",
  "ts": "ISO-8601",
  "thread": "thread-id",
  "type": "message|control|presence|task|result",
  "from": "participant-id",
  "to": "all|participant-id",
  "content": "string or object",
  "meta": {
    "reply_to": "event-id",
    "tags": []
  }
}
```

Notes:
- `content` MAY be omitted for some `control` events.
- `meta` is optional; missing fields are treated as absent.

## Event types (v1 set)

### `message`

Human- or agent-authored conversational content.

Required:
- `from`
- `to` (default `all` if omitted by transport)
- `content` (string)

### `control`

Signals that influence participation policy.

Recommended `content` shapes (exact schema TBD):
- `{"mute": ["participant-id"]}`
- `{"prod": ["participant-id"]}`
- `{"done": true}`
- `{"ttl_seconds": 600}`

Open question:
- Whether controls are represented via `type="control"` + `content` (recommended) or via subtypes like `control.mute`.

### `presence`

Signals like “online”, “thinking”, “typing”, “idle”.

Decision (v1):
- Presence/thinking/typing is **ephemeral by default** (derived from live connections or local UI state), not a continuously persisted stream.

Optional (still v1-compatible):
- Persist **state transitions** as events when useful for coordination or auditability (e.g., `thinking.start`, `thinking.end`) rather than emitting frequent heartbeats.

### `task` / `result` (optional in v1)

Task assignment and structured outputs. Kept optional because this can prematurely force a “middleman coordinator” design.

Decision (v1 delivery):
- `task` / `result` are **deferred**; v1 focuses on `message` / `control` / `presence`.

If included:
- `task` is a request for work addressed to one participant (or a role)
- `result` is an output that references a task via `meta.reply_to` or a `task_id`

## Targeting and participation policy

Agent Bridge separates:
1) **transport/storage** (append-only events)
2) **participation policy** (when agents choose to respond)

Participation policy is intentionally configurable because the desired behavior varies by thread size and context.

Recommended starting modes:

- **Small-thread mode (permissive)**:
  - Agents MAY contribute to `to="all"` messages when they have relevant value to add.
  - Agents SHOULD still avoid interrupting an ongoing response if they have an explicit “thinking/typing” signal available (see `presence`).
- **Large-thread mode (conservative)**:
  - Agents SHOULD respond when:
    - explicitly targeted via `to`, or
    - explicitly prodded via a control event, or
    - explicitly invited (convention; schema TBD)
  - Agents SHOULD NOT respond to every `to="all"` message by default.

Rationale:
- Supports the desired “fluid” collaboration while preserving human steering and preventing chatter.

## Thread lifecycle

Threads are created by generating a `thread` id and emitting a first event recording the title/name.

Decision (v1):
- Thread naming is represented **both** ways:
  - **In-log events** (`thread.created`, `thread.renamed`) are the source of truth for history.
  - A thread index/metadata view MAY exist for fast lookup, but is treated as derived/cached.

## Automation components (optional)

Automation may exist (e.g., adapters, bots, watchers), but it should behave like a **participant**, not an invisible intermediary:
- It writes events under its own `from` identity (no impersonation).
- It does not rewrite history; any “summaries” or “routing decisions” are appended as events.
- It should make its actions legible to the human and other participants in the thread.
