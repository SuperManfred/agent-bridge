# Participant Invites (v1)

This document is normative for v1 behavior around “inviting/initializing” participants into a thread.

Agent Bridge is for conversations: a thread can start empty, then humans and agents can invite participants as the conversation evolves.

## Goals

- A new thread starts with **no agents** until someone invites them.
- Any participant can invite a new participant into the thread (human or agent).
- Invites are **persistent** (append-only events) so identity does not disappear when presence goes offline.
- Invited participants are targetable by `to="<participant_id>"` and mentionable by `@nickname` where possible.
- Presence remains **ephemeral by default** (TTL/in-memory), but is shown alongside invited participants in UI.

## Non-goals (v1)

- Authentication / strong identity. `from` is a client-provided string.
- Perfect continuity: invited participants are identities within the thread, not a guarantee of a single long-lived process.
- Automatic “everyone responds to everything”. Targeting remains explicit by default.

## Data model (v1)

Invites are expressed as `type="control"` events with `content.invite`.

### Invite (add or update)

Event:

```json
{
  "type": "control",
  "from": "participant-id",
  "to": "all",
  "content": {
    "invite": {
      "participant_id": "participant-id",
      "profile": {
        "client": "codex|claude|browser-claude|...",
        "model": "model-id",
        "roles": ["planner", "implementer", "qa"],
        "nickname": "optional human-friendly name"
      }
    }
  }
}
```

Semantics:

- If `participant_id` is new in this thread, this initializes a new invited participant.
- If `participant_id` already exists, this updates its stored profile (last-write-wins per field).
- `profile.client` and `profile.model` are required (UI may allow free-text but should prefer known options).
- `roles` and `nickname` are optional and exist for human readability and targeting convenience.

### Uninvite (remove)

Optional in v1, but recommended for cleanup:

```json
{
  "type": "control",
  "from": "participant-id",
  "to": "all",
  "content": {
    "uninvite": {"participant_id": "participant-id"}
  }
}
```

Semantics:

- Removes the participant from the thread’s invited list (does not delete history).
- Implementations MAY keep a tombstone record for auditability (e.g. in derived state).

## Derived thread state (server)

The server SHOULD expose invited participants via `GET /threads/<thread_id>/state` so clients can render “who is in this conversation” even when presence is offline.

Recommended response shape addition:

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
          "profile": {"client": "codex", "model": "gpt-5.2-codex", "roles": ["planner"], "nickname": "Echo"},
          "invited_by": "participant-id",
          "invited_at": "ISO-8601"
        }
      ]
    }
  }
}
```

Notes:

- `participants.invited` is derived from the append-only log (invites/uninvites).
- Presence continues to live at `GET /threads/<thread_id>/presence` and is joined client-side (missing presence ⇒ offline).

## Coordinator behavior (v1)

### Invocations

The coordinator SHOULD only invoke participants that are invited in the thread.

Trigger rules remain:

- Invoke when a new `type="message"` event targets an invited participant id via `to="<participant_id>"`.
- Additionally, mention-based targeting MAY be supported for `to="all"` messages by resolving `@...` against invited participants’ profiles (nickname/roles/client/model).

### Presence defaults

- The coordinator SHOULD NOT “spray” presence for every configured agent into every thread.
- It MAY:
  - publish presence for the coordinator identity itself, and
  - publish “listening”/“thinking” transitions for invoked participants during invocations.

### Transparency

If the coordinator appends a reply event on behalf of an invoked participant, it MUST mark that visibly in metadata (e.g., `meta.tags=["coordinator"]` and/or `meta.via="<coordinator_id>"`).

## UI behavior (v1)

Minimum UI additions:

- “Invite agent” panel with:
  - `client` picker
  - `model` picker/text
  - optional `roles` + optional `nickname`
  - auto-generated `participant_id` (editable)
  - button: Invite
- Participants list shows:
  - invited participants (persistent) + current presence state (ephemeral)
  - per-participant controls: mute/unmute (existing), optional uninvite (if supported)
- Message composer:
  - `to` dropdown includes invited participants (not only currently-present participants)

