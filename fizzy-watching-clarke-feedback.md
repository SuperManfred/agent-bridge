# Feedback on fizzy-watching-clarke plan (simplify without losing capability)

This feedback is based on /Users/MN/.claude/plans/fizzy-watching-clarke.md.

## What to keep
- Shared audit trail with append-only messages.
- Multiple agent participation with presence and "thinking" signals.
- A simple UI later, not required for initial collaboration.

## Simplifications that preserve functionality
1) Avoid "no orchestrator" wording when watchers are intermediaries.
   - The plan says agents decide themselves when to speak, but watcher scripts
     still invoke the agents (plan lines 7 and 67). Rename watchers to adapters
     and state they only relay events; agent judgment stays inside the prompt.

2) Prefer stateless “spawn per task” over long-lived sessions (for MVP).
   - Keeping interactive sessions alive is brittle and hard to automate across
     harnesses; it also increases drift risk (plan lines 133 and 149).
   - Simplify by spawning an agent per directed task, capturing output, and
     writing it back to the audit log.

3) Single-writer audit log to avoid file locking.
   - The plan has multiple participants writing shared files and already calls
     out file locking risk (plan lines 16-33 and 147-150).
   - Simplify by routing all writes through the server. The JSONL file remains
     the audit trail, but agents write via HTTP, not directly to disk.

4) Collapse presence.json into the message stream or server-owned state.
   - The plan introduces a separate presence.json (plan lines 55-65) plus
     /presence endpoints (plan lines 113-118).
   - Simplify by recording presence as message events (type=presence) or by
     keeping presence as server-owned state updated via /presence POST.

5) Replace per-agent shell scripts with a single adapter daemon.
   - The plan adds a watcher script for each agent (plan lines 67-98).
   - A single agentd with a config file (agent name, command, prompt) cuts
     duplication and still allows per-agent behavior.

6) Add a minimal "control" envelope to the message schema.
   - The current schema is minimal (plan lines 43-51) but the open questions
     need controls for mute, prod, ttl, and "done" (plan lines 133-141).
   - Add meta.control fields instead of more files/endpoints.

7) Build adapters before UI.
   - If the goal is seamless collaboration, the event loop and adapters should
     be verified before UI (plan lines 154-159).

## Proposed minimal schema (v2)
```json
{
  "id": "timestamp-based-id",
  "timestamp": "ISO-8601",
  "from": "codex|claude-code|browser-claude|user",
  "to": "all|agent-id",
  "type": "message|presence|control|task",
  "content": "text or task payload",
  "thread_id": "uuid",
  "meta": {
    "control": {
      "ttl_seconds": 120,
      "mute": ["agent-id"],
      "prod": ["agent-id"],
      "done": true
    }
  }
}
```

## Minimal workflow to satisfy your new requirements
- Default TTL is short (eg 120s) and resets after each human message.
- Human can extend TTL via control message or a UI button.
- Human can mute/prod agents without sending a typed message.
- Agent responds only when targeted, prodded, or explicitly asked.
- Presence is updated on any agent activity, but "thinking" streaming is opt-in.

## MVP sequence (simplified)
1) Server owns all writes; JSONL remains the audit log.
2) Add /presence (or presence events) and /control handling in the server.
3) Build a single agentd adapter with per-agent config.
4) Add basic CLI or HTML view after the loop works.
