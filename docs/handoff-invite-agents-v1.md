# Handoff: Invite Agents + Default-On Agency (v1)

This is an implementation-ready handoff for adding “Invite agent” to the UI and making coordinator-invoked agents able to act on the machine by default.

Status: draft, but intended to be directly actionable.

## Problem

Today a new thread can feel “empty” because:

- participants are effectively global (preconfigured), not invited into a specific conversation
- coordinator-spawned agents are configured as “read-only” / “no tools”, which turns the bridge into a chat-only “tea room”

This contradicts the conversation-first intent: participants should be able to come and go, assume roles, invite other participants, and act while the conversation continues.

## Goals (v1)

1) Thread-scoped invites
- A new thread starts with no invited agents.
- A human or any participant can invite/initialize participants into that thread with:
  - `{client}/{model}`
  - optional `{roles}`
  - optional `{nickname}`

2) Default-on agency
- When the coordinator invokes an invited participant, that participant can run tools and make repo changes by default.
- Human control levers remain: mute/pause/discussion controls.

3) UI supports invite + targeting
- UI has an “Invite agent” panel.
- UI shows invited participants (even if offline).
- Message composer can target invited participants via `to="<participant_id>"`.

## Non-goals (v1)

- Strong auth or preventing identity spoofing.
- Perfect session continuity across days.
- Automatic agent fanout.

## Source docs

- `docs/vision.md`
- `docs/spec.md`
- `docs/invites.md` (normative invite semantics)
- `docs/bridge-agent-primer.md` (minimal instructions for spawned agents)
- `docs/coordinator.md`

## Required behavior (detailed)

### 1) Invite event schema

Use the `control.invite` schema from `docs/invites.md`.

Minimum required fields:
- `invite.participant_id` (string)
- `invite.profile.client` (string)
- `invite.profile.model` (string)

Optional:
- `invite.profile.roles` (array of strings)
- `invite.profile.nickname` (string)

### 2) Derived thread state must include invited participants

Extend `GET /threads/<thread_id>/state` to include invited participants so the UI can render “who is in this conversation” even if presence is missing.

State must remain derived from the append-only log:
- invites/uninvites
- mute/pause/discussion (as implemented)

Important:
- Mute/pause/discussion MUST remain authoritative from `from="user"` only (as today).
- Invites MUST be accepted from any participant id.

### 3) UI: Invite agent panel + participants list

Add an “Invite agent” panel to the room UI:

Inputs:
- client (dropdown)
- model (dropdown or text)
- roles (multi-value text)
- nickname (text)
- participant_id (auto-generated; editable)

Button:
- “Invite agent” → posts `type="control"` event with `content.invite`.

Participants list:
- base list: `state.participants.invited`
- overlay: `presence.participants` for state/TTL
- show offline when no presence entry exists for an invited participant

Controls:
- mute/unmute: existing control events
- optional: uninvite (if implemented)

Message composer:
- `to` dropdown includes invited participants (even if offline)

### 4) Coordinator: invoke only invited participants

Today the coordinator treats config agents as globally present and invokable.

Change:
- coordinator MUST build its “invokable participants” per thread from the thread’s invited participant list.
- it MUST ignore `to="<participant_id>"` if that participant is not invited in that thread.

Mention resolution:
- resolve `@...` against invited participants profiles (nickname, roles, client, model, id)

Presence:
- do not publish “listening” presence for agents not invited in a thread
- publish `thinking`/`listening` transitions during invocations for invited participants

### 5) Default-on agency

Adapters are currently configured to be non-acting.

Change:
- Codex adapter must not run with “read-only” permissions by default.
- Claude Code adapter must not disable tools by default.

The prompt injected into spawned agents MUST include:
- `docs/bridge-agent-primer.md` (verbatim or near-verbatim)

The coordinator MUST mark coordinator-assisted replies in metadata (for transparency), e.g.:
- `meta.tags` includes `"coordinator"`
- and/or `meta.via="<coordinator_id>"`

## Implementation plan (files)

Server:
- `server.py`
  - derive invited participants from events
  - extend `/threads/<thread_id>/state`

UI:
- `ui/index.html` (add invite panel markup)
- `ui/app.js`
  - fetch state includes invited participants
  - render invited participants with presence overlay
  - implement “Invite agent” action
  - include invited participants in `to` dropdown

Coordinator:
- `coordinator.py`
  - fetch thread events and derive invited participants per thread
  - change invocation target resolution to require invited status
  - change presence heartbeat logic accordingly
  - pass selected model/profile through to adapter payload

Adapters:
- `adapters/codex.sh`
- `adapters/claude_code.sh`
  - remove the read-only/no-tools constraints
  - inject `docs/bridge-agent-primer.md` into the prompt
  - add a simple mechanism to select model per invocation (env var or CLI flag), driven by `invite.profile.model`

Docs:
- update `docs/api.md` evidence/behavior notes if endpoints change

## Acceptance criteria

1) New thread starts with no invited agents
- Create thread → UI shows no invited participants until you invite one.

2) Invite agent creates a targetable participant
- Invite `client=codex`, `model=...`, `nickname=...`, `roles=[planner]`.
- Participant appears in participants list immediately (offline if not yet present).
- Participant appears in `to` dropdown.

3) Invocations work only for invited participants
- Posting `to="<invited_id>"` triggers coordinator invocation and reply.
- Posting `to="<non_invited_id>"` produces no invocation.

4) Default-on agency works
- Triggered agent can run commands and edit files by default.
- Agent reports actions and resulting changes in its reply.

5) Controls still work
- Hard-mute blocks agent messages (server rejects non-user messages while muted).
- Pause blocks non-user messages (server rejects while paused).

## QA plan (manual, v1)

Pre-req:
- run server + coordinator
- open UI and create a new thread

Test cases:

T1: Invite flow
- Invite a new participant; verify it shows in UI and `/threads/<id>/state`.

T2: Targeting
- Send a message with `to=<participant_id>`; verify agent reply is appended and `meta.reply_to` matches.

T3: Presence
- During invocation, verify presence shows `thinking` then returns to `listening`.

T4: Mute/pause
- Mute participant; ensure coordinator won’t invoke it and server rejects if it tries to post.
- Pause thread; ensure non-user participants are blocked.

T5: Multi-agent
- Invite 2–3 participants with different nicknames/roles.
- Verify `to` dropdown and mention resolution work without ambiguity.

