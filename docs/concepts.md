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
- AI clients running specific models (e.g., `codex` + `gpt-5.2-codex`, `claude` + `claude-opus-4-5-20251101`)
- browser agent client (optional)
- system components (optional)

## Participant profile

Participants are identified by a stable `participant_id` (the value used in event `from` / `to`), plus an optional **profile** used for human-friendly interpretation and targeting.

Recommended profile fields:
- `client`: the harness/client name (align with `/Users/MN/.config/ai-registry/registry.yaml` `clients:` keys)
- `model`: the model name (align with `/Users/MN/.config/ai-registry/registry.yaml` `models:` keys)
- `nickname` (optional): human-friendly alias that can change
- `roles` (optional): free-form strings (assigned by the human and/or any participant; not an authority system)

Profiles can be:
- **Ephemeral** (recommended default): published via presence `details` so they can change without rewriting history.
- **Persisted** (optional): appended as events when it matters to keep a durable record (e.g., “who was the reviewer in this thread”).

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

Recommended presence states:
- `listening` — present and paying attention (default steady state)
- `thinking` — actively working on a response/action
- `typing` — composing a message
- `idle` — away/unresponsive (still a participant, but not actively present)
- `offline` — derived state when the participant’s presence has gone stale

Presence is **ephemeral by default** and should not spam the append-only log.

## Side channels

A **side channel** is a separate thread used to work through detail without burdening all participants’ context.

Side channels should be:
- **Explicit**: created and linked from the main thread (no “hidden DMs” in v1).
- **Discoverable**: any participant can open/read them, but clients should not auto-consume side-channel content in the main thread.
- **Threaded back**: the main thread should get a short summary + link so others can decide whether to open the side channel.
