# Agent Bridge Docs

These docs capture product intent and a v1 specification for Agent Bridge (local-first, single user) independent of the current implementation details.

## Reading order

1. `docs/vision.md` — why this exists, principles, non-goals
2. `docs/concepts.md` — shared vocabulary
3. `docs/spec.md` — normative v1 spec (data model + semantics)
4. `docs/api.md` — current HTTP/SSE surface (v0) + intended direction
5. `docs/coordinator.md` — always-on component (removes nudges)
5. `docs/operations.md` — how to run + how data is stored
6. `docs/security.md` — trust boundaries (local-only)
7. `docs/roadmap.md` — milestones and acceptance criteria
8. `docs/decisions.md` — decisions + open questions

## Status

- These docs are intentionally “spec-first”: they describe the intended behavior and constraints, then map to the current implementation where it exists.
- Anything tagged “Open question” is a prompt for a follow-up interview / decision.
