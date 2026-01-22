# Decisions and Open Questions

## Decisions (confirmed)

- **Docs format**: Option A (“small but complete” multi-file docs).
- **Scope**: single-user localhost; avoid premature auth/complexity.
- **Conversation-first framing**: threads are informal conversations; participants come/go; the system should feel like fluid human collaboration, not a rigid workflow.
- **Participant profile**: participants are identified by `participant_id` plus an optional profile (`client`, `model`, optional `nickname`, optional `roles`) aligned to `/Users/MN/.config/ai-registry/registry.yaml`.
- **Presence states**: ephemeral by default; include `listening` distinct from `idle` (idle = away/unresponsive); optionally persist state transitions if needed.
- **v1 event types**: focus on `message` / `control` / `presence`; defer `task` / `result` as a later layer.
- **Terminology**: align terms with Codex and Claude Code docs where possible (avoid redefining common words like “task”, “session”, “agent”).
  - Local sources to treat as reference: `/Users/MN/GITHUB/.knowledge/curated-docs-repo/ericbuess-claude-code-docs`, `/Users/MN/GITHUB/.knowledge/curated-code-repo/openai-codex`.
- **Thread naming**: keep `thread.created` / `thread.renamed` as in-log events; keep an index/metadata view as derived cache.
- **Turn-taking defaults**: conversationally permissive, but automation triggers are conservative by default (explicit `to=<id>` and human mentions); human has an “escape hatch” (hard mute/pause/prod).
- **Mentions**: human mentions (`from="user"`, `to="all"`, `@...`) are enabled by default; non-human mentions require an explicit thread control.
- **Broadcast fanout**: off by default; opt-in via thread control.
- **Side channels**: explicit, discoverable threads with link-back summary; no “private” side channels in v1.
- **Threads are canonical**: thread events are the only conversation substrate; the legacy “daily log” endpoints/files are removed.

- **Thread-scoped participant invites**: participants are invited/initialized per thread so a new thread can start empty and you can explicitly “invite an agent” into the conversation (including `client`/`model`, optional `roles`, optional `nickname`).
- **Language**: prefer “participant” + “invite/initialize” over more formal team-management language (e.g. “roster”).
- **Agency is on by default (v1 scope)**: when the coordinator invokes a participant, that participant is expected to be able to act on the machine by default (tools + repo edits), with the human using mute/pause/prod controls + monitoring to steer.
- **Invites can be authored by participants**: any participant may invite/initialize other participants into a thread (this is essential to multi-agent collaboration).
- **Spawned-agent primer**: newly-invoked agents start with a minimal “how to operate on Agent Bridge” primer (simple + unconstraining); role-specific constraints can be layered later.

## Decisions (proposed)

- **Vocabulary**: prefer “thread” over “room” in specs; keep UI wording as legacy until changed.
- **Automation framing**: describe automation as optional “coordination”, not a mandatory “orchestrator”.

## Open questions (next interview)

1) **Control schema**: do we keep `type="control"` with structured `content`, or introduce subtypes like `control.mute`?
2) **Profile persistence**: which profile fields (if any) should be persisted as events by default vs only published ephemerally via presence `details`?
3) **Scaling heuristics**: when does a thread become “large”, and what default behaviors change at that threshold?
4) **Invite schema**: exact `control` `content` shape for invite/initialize, required fields, and how `participant_id` is assigned.
5) **Model selection**: how `{client, model}` choices are surfaced in UI and mapped to harness invocation in the coordinator/adapters.
6) **Small-thread “alive” mode**: what is the minimal per-thread control shape to enable auto-invoking invited participants for `from="user"` + `to="all"` messages (and what, if any, throttling/limits apply)?
