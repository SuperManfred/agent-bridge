# Decisions and Open Questions

## Decisions (confirmed)

- **Docs format**: Option A (“small but complete” multi-file docs).
- **Scope**: single-user localhost; avoid premature auth/complexity.
- **Presence/thinking**: ephemeral by default; optionally persist state transitions if needed.
- **v1 event types**: focus on `message` / `control` / `presence`; defer `task` / `result` as a later layer.
- **Terminology**: align terms with Codex and Claude Code docs where possible (avoid redefining common words like “task”, “session”, “agent”).
  - Local sources to treat as reference: `/Users/MN/GITHUB/.knowledge/curated-docs-repo/ericbuess-claude-code-docs`, `/Users/MN/GITHUB/.knowledge/curated-code-repo/openai-codex`.
- **Thread naming**: keep `thread.created` / `thread.renamed` as in-log events; keep an index/metadata view as derived cache.
- **Turn-taking defaults**: permissive by default, with a human “escape hatch” (pause/mute/prod) available when needed.
- **Daily log vs threads**: keep both for now; revisit after real usage indicates convergence is desirable.

## Decisions (proposed)

- **Vocabulary**: prefer “thread” over “room” in specs; keep UI wording as legacy until changed.
- **Automation framing**: describe automation as optional “coordination”, not a mandatory “orchestrator”.

## Open questions (next interview)

1) **Control schema**: do we keep `type="control"` with structured `content`, or introduce subtypes like `control.mute`?
2) **Presence signal shape**: what is the minimal, interoperable representation for “thinking/typing/idle” that works across harnesses?
3) **Scaling heuristics**: when does a thread become “large”, and what default behaviors change at that threshold?
