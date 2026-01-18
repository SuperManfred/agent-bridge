# Concepts

## Thread

A **thread** is a single conversation timeline represented by an append-only sequence of events.

Notes:
- The current UI and endpoints use the word “room”, but this is purely naming; the intended concept is a thread.

## Event

An **event** is one append-only record in a thread log. Events are the source of truth.

Common fields (v1 intent) are defined in `docs/spec.md`.

## Participant

A **participant** is an entity that reads and/or writes events:
- human (user)
- CLI agents (e.g., `codex`, `claude-code`)
- browser agent client (optional)
- system components (optional)

## Targeting

**Targeting** means an event can address everyone or a specific participant via `to`.

Agent Bridge’s default posture is to prevent “everyone responding to everything” while still allowing agents to join in when it makes sense.

Practical framing:
- In a **small thread** (e.g., 1 human + 2–3 agents), “free-form” participation can be acceptable and even desirable.
- In a **large thread**, some form of turn-taking / invitation / throttling becomes necessary to preserve usefulness.

## Controls

Controls are conventions expressed as events that influence participation without rewriting history. Examples (names TBD):
- `mute` — participant should not auto-respond
- `prod` — participant should respond once
- `done` — participant signals completion
- `ttl` — limits “runway” for auto-participation

## Presence / Thinking

Presence/thinking are *signals* to help turn-taking (e.g., “agent is thinking”, “agent is writing”).

Open question:
- Whether these signals are persisted as events, kept ephemeral (derived), or both.
