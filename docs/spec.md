# Spec (v1)

This document is normative: it defines intended behavior. Where the current implementation differs, `docs/api.md` describes “v0 behavior”.

## Naming

- This spec uses **thread** (not room) for the conversation container.
- “Orchestrator” is avoided as a primary framing term; automation is described as optional **coordination**.

## Identifiers and timestamps

- `id`: globally unique per event (ULID recommended).
- `ts`: ISO-8601 timestamp (event creation time).
- `thread`: thread identifier (opaque string, ULID recommended).

## Participants and profiles

- `from` and `to` refer to a **participant id** (`participant_id`): an opaque, stable handle within a thread.
- Participants SHOULD publish a **profile** so other participants can interpret who is speaking and target them naturally.

Threads are conversations: participants come and go.

In v1 we distinguish:
- **Invited participants (persistent)**: a thread can persist “who is part of this conversation” (including `client`/`model` and optional `roles`/`nickname`) so a new thread can start empty and the human (or another agent) can invite participants into the conversation.
- **Presence (ephemeral)**: who is currently listening/thinking/typing/idle/offline, derived from live clients and TTLs by default.

Recommended profile fields (align values with `/Users/MN/.config/ai-registry/registry.yaml`):
- `client`: a key under `clients:` (e.g. `codex`, `claude`, `gemini`)
- `model`: a key under `models:` (e.g. `gpt-5.2-codex`, `claude-opus-4-5`)
- `nickname` (optional): a human-friendly alias
- `roles` (optional): free-form strings (assigned by the human and/or participants; not an authority system)

Profile publication:
- **Ephemeral (recommended default)**: included in presence updates (e.g. presence `details`) so it can change without rewriting history.
- **Persistent (optional)**: appended as a `control` event when it matters to preserve a durable record.

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

Recommended:
- Use `meta.reply_to` when replying to a specific prior event (helps humans follow the thread).

### `control`

Signals that influence participation policy.

Recommended `content` shapes (exact schema TBD):
- `{"mute": {"targets": ["participant-id"], "mode": "hard"}}`
- `{"unmute": {"targets": ["participant-id"]}}`
- `{"pause": {"on": true}}`
- `{"pause": {"on": false}}`
- `{"prod": ["participant-id"]}`
- `{"done": true}`
- `{"ttl_seconds": 600}`
- `{"discussion": {"on": true, "allow_agent_mentions": true}}`
- `{"invited_auto": {"on": true}}`
- `{"invite": {"participant_id": "participant-id", "profile": {"client": "codex", "model": "gpt-5.2-codex", "roles": ["planner"], "nickname": "optional"}}}`

Note:
- For `discussion`, if `allow_agent_mentions` is omitted, implementations MAY treat it as the same value as `on`.

Open question:
- Whether controls are represented via `type="control"` + `content` (recommended) or via subtypes like `control.mute`.

#### Hard mute / pause (v1 intent)

This project targets “local-first, single user”. In that scope:

- **Hard mute**: when a participant is hard-muted in a thread, the server SHOULD reject new `type="message"` events authored by that participant for that thread with an explicit error response (so the muted participant is aligned to the conversation state).
- **Pause**: when a thread is paused, the server SHOULD reject new `type="message"` events from non-human participants until resumed.

Notes:
- This is best-effort (there is no strong identity/auth in v1). It is meant for alignment and UX, not security.
- Clients SHOULD reflect mute/pause state in presence (e.g. remain `listening`) and avoid generating long outputs when muted/paused.

### `presence`

Signals like “listening”, “thinking”, “typing”, “idle”.

Decision (v1):
- Presence/thinking/typing is **ephemeral by default** (derived from live connections or local UI state), not a continuously persisted stream.

Optional (still v1-compatible):
- Persist **state transitions** as events when useful for coordination or auditability (e.g., `thinking.start`, `thinking.end`) rather than emitting frequent heartbeats.

Recommended presence states:
- `listening` — present and paying attention (default steady state)
- `thinking` — actively working on a response/action
- `typing` — composing a message
- `idle` — away/unresponsive
- `offline` — derived when presence is stale (implementation-defined TTL)

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
    - explicitly invited (e.g. via a persisted `control` `invite`)
  - Agents SHOULD NOT respond to every `to="all"` message by default.

Rationale:
- Supports the desired “fluid” collaboration while preserving human steering and preventing chatter.

Per-thread opt-in:
- When `control.invited_auto.on` is true, implementations MAY auto-invoke invited participants for `from="user"` + `to="all"` messages that contain no explicit `@mentions`.

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

## Side channels (threads as scoping)

Side channels are explicit, separate threads used to work through detail without forcing every participant to ingest it immediately.

Normative intent:
- Side channels MUST be visible and discoverable (no “private” side channels in v1).
- A side channel SHOULD be linked from the main thread with enough metadata for others to decide whether to open it.
- A side channel SHOULD be “threaded back” into the main thread with a short summary and a link when done.
