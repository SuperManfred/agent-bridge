# Agent Bridge v2 — Seamless Multi‑Agent Collaboration (with audit trail)

This is a v2 plan that simplifies /Users/MN/.claude/plans/fizzy-watching-clarke.md while keeping the core capability: agents can communicate + collaborate without you manually “waking” each one, and everything is audit‑logged.

## 0) Reality checks (so we don’t plan fiction)

- A plain “message bus” does not make agents proactive. Some always‑on process must watch for new work and invoke agents. (The v1 plan implicitly did this via watcher scripts.)
- “Already-running” interactive agent sessions are hard to drive programmatically (often no stdin protocol / no API).
- Browser agents are the hardest to auto‑wake unless they run a persistent client (tab/extension) that can maintain a connection.
- Multi‑turn conversations do not require a long‑lived process if we have a canonical thread log: “spawn per task” can still be multi‑turn by replaying a context window from the thread.

## 1) Goals (what “seamless” means here)

**G1. Shared audit trail**
- Every message, control action (mute/prod/extend time), task assignment, and agent output is append‑only and reconstructable.

**G2. Auto‑participation**
- If a task targets an agent, the system can invoke it without you manually prompting it.

**G3. Controlled collaboration (no cacophony)**
- Defaults prevent all agents responding to everything.
- Human can quickly mute/prod agents.
- Conversation has a TTL “runway” that resets on human input and can be extended.

**G4. Cross‑harness**
- Works across at least: CLI agents (Codex/Claude Code) and a browser agent (via an optional client).

**G5. Model + harness registry**
- A machine‑readable catalog of: available models, which are current, and how to invoke them per harness.

**Decision (from user): multi-room from day 1**
- Rooms are multiple concurrent threads, not a single global chat.

## 2) Non‑goals (v2 explicitly punts)

- Perfect “thinking token” streaming across all harnesses (support presence + coarse “thinking/typing” first).
- Full marketplace‑grade auth/multi‑tenant security (assume local machine; add auth only when needed).
- Driving already-running interactive sessions as the primary mechanism (treat as optional integration later).

## 3) Core design: Event log + orchestrator + adapters

### 3.1 Single canonical store: append‑only event log
- Keep JSONL as the audit trail, but make it **canonical** and **structured**:
  - **Per-thread file** for stable room history.
  - A server is optional for UI/HTTP clients; file access alone can still read the audit trail.
- Everything is an “event”: message, control, task, presence, result.

### 3.1.1 Thread storage layout (stable path, renameable room)
- Thread file path is stable and keyed by an opaque, time-sortable ID (**ULID chosen**):
  - `conversations/threads/<thread_id>.jsonl`
- Room name is mutable metadata, expressed as events in the thread log:
  - `type="thread.created"` with initial name
  - `type="thread.renamed"` with new name (agents are allowed to emit this)

### 3.2 Orchestrator: one daemon that makes the system proactive
- Reads the event stream, maintains minimal state (threads, TTL, mute lists, task status).
- Decides which adapters to invoke (or whether to do nothing).
- Writes results back as events.

### 3.3 Adapters: per-harness “drivers”
- Each adapter knows how to invoke one harness (Codex CLI, Claude Code CLI, Browser agent client).
- Adapters support two execution modes:
  - **job**: spawn-per-task (stateless process)
  - **session**: long-lived, multi-turn (where the harness supports it)

This collapses “watchers per agent” into: **one orchestrator + multiple adapters**.

## 4) Execution modes (job vs session)

Both modes must support multi‑turn conversations. The difference is *where state lives*.

### 4.1 Job mode (spawn per task)
- Default for MVP because it’s reliable across harnesses.
- Multi‑turn is achieved by passing the current thread context window (or a summary) into each invocation.

### 4.2 Session mode (long-lived, multi-turn)
- Used when the harness provides a stable way to resume a session and send a new “turn” programmatically.
- Multi‑turn is achieved by keeping an explicit `session_id` for that harness and routing future turns to it.
- If a harness can only resume an interactive TUI without a message API, treat session mode as “manual attach” until proven otherwise.

## 4) Data model (minimal, extensible)

### 4.1 Event schema (v2)
```json
{
  "id": "ulid-or-timestamp-id",
  "ts": "ISO-8601",
  "thread": "thread-id",
  "type": "message|control|task|result|presence",
  "from": "user|codex|claude-code|browser-claude|system",
  "to": "all|agent-id",
  "content": "string (for message) or object (for task/result)",
  "meta": {
    "reply_to": "event-id",
    "tags": ["planning", "review"],
    "visibility": "all|private",
    "control": {
      "ttl_seconds": 120,
      "mute": ["agent-id"],
      "prod": ["agent-id"],
      "done": true
    }
  }
}
```

### 4.2 Thread state (derived, not separately authored)
Derived by replaying events:
- current TTL runway
- muted agents
- active tasks + statuses
- last human message timestamp

Avoid separate `presence.json` as a shared writable file. Presence can be:
- ephemeral in orchestrator memory, computed from heartbeats, and optionally exposed via an endpoint.

### 4.3 Task object (in `content` when `type="task"`)
```json
{
  "task_id": "uuid",
  "role": "planner|reviewer|implementer|researcher|qa",
  "prompt": "what to do",
  "inputs": {"repo_path": "...", "files": ["..."]},
  "constraints": {"time_budget_s": 600},
  "target": {
    "agent": "codex",
    "harness": "codex-cli",
    "model": "gpt-5.2",
    "thinking": true,
    "mode": "job|session",
    "session_id": "optional",
    "max_turns": 1
  }
}
```

## 5) Collaboration controls (what you asked for)

### 5.1 TTL runway (default short, extendable)
Default:
- On any **human** message: set thread TTL runway to **120 seconds** (configurable).
- If TTL expires: orchestrator stops auto-invoking agents for that thread.

Extend:
- Human can send a control event: `meta.control.ttl_seconds=3600`
- UI can expose a “+10m / +1h” button that emits the same control event.

### 5.2 Mute / prod
- `meta.control.mute=["qa-agent"]` prevents auto-invocation except when explicitly prodded.
- `meta.control.prod=["qa-agent"]` triggers a targeted task “review current state” without requiring the human to type a bespoke request.

### 5.3 Preventing cacophony (default policy)
An agent should only run when at least one is true:
- The event `to` matches it (directed message/task)
- It is explicitly prodded
- It is assigned a role in an active workflow step

Everything else is read-only observation.

## 6) Model & harness registry (machine-readable)

Create a `registry/` directory (schema-backed):
- `registry/models.json` — canonical list of non-superseded models you care about (with `provider`, `family`, `released`, `deprecated`).
- `registry/harnesses.json` — each harness + how to invoke a model (flags, env vars, “toggle thinking” mapping).
- `registry/agents.json` — installed/available agent identities + which harness they use + capabilities (e.g., “browser-console”, “repo-edit”).

Important: some harnesses may not expose “list models” programmatically. The registry should allow:
- manual curation (source-of-truth)
- optional discovery scripts that update it

## 7) Components (deliverables)

### 7.1 `bridge` (daemon)
Responsibilities:
- Append-only log writer (atomic writes).
- Read + replay log (derive thread state).
- Expose local API:
  - `POST /event` (append event)
  - `GET /events?since=...&thread=...` (fetch)
  - `GET /stream` (SSE) (optional but recommended)
  - `GET /presence` (derived)

#### 7.1.1 SSE streaming spec (low-dependency)
Goal: replace polling with a simple Server-Sent Events stream.

Endpoint:
- `GET /threads/<thread_id>/events/stream?since=<ts>`

Behavior:
- Emits `event` payloads as JSON lines over SSE.
- Uses `Content-Type: text/event-stream`.
- `since=<ts>` replays events with `ts` greater than the cursor.
- Clients reconnect with `since` to resume after disconnects.

Note: Vercel docs show SSE streaming with `Content-Type: text/event-stream` and a `streamText` response pattern. We borrow the SSE contract, not the framework or SDK details.

#### 7.1.2 Runtime baseline
- Node.js 20+ recommended for the bridge daemon.
- Your current local Node version is v24.13.0 (per your note), so this baseline is safe.

### 7.2 `agentd` (orchestrator loop)
Responsibilities:
- Subscribe to new events (SSE or polling).
- Apply policy (TTL, mute/prod, targeting).
- Convert triggers into tasks.
- Invoke adapters and write result events.

### 7.3 Adapters
- `adapter-codex`: spawn Codex for tasks that require planning/review/edit (stateless runs).
- `adapter-claude-code`: spawn Claude Code for tasks requiring its environment.
- `adapter-browser`: optional “browser client” that reads tasks and posts results (may require a persistent tab/extension page).

### 7.4 UI (later)
- Read-only viewer first (tail events).
- Then controls: TTL buttons, mute/prod toggles.

## 8) MVP phases (small, verifiable increments)

### Phase 0 — Start using a shared thread immediately (no automation)
Deliver:
- Agree on a single “room” log file to treat as canonical for the thread (even if we keep daily rotation underneath).
Success:
- You can tell any agent “read the log at PATH and respond” instead of copy/pasting message history.

### Phase A — Make it proactive (no UI yet)
Deliver:
- Orchestrator loop + event schema + directed tasks.
Success:
- Writing a `task` event automatically triggers a response event from a CLI adapter.

### Phase B — Add collaboration controls
Deliver:
- TTL runway + mute/prod controls implemented as control events.
Success:
- After TTL expires, no agent runs; prod overrides mute; TTL extend works.

### Phase C — Add registry
Deliver:
- `registry/` JSON + schema, and adapters read it to pick invocation flags/models.
Success:
- Switching a target model for an agent changes how the adapter invokes it.

### Phase D — Browser agent integration
Deliver:
- A minimal browser client connection strategy (SSE/polling) that can post results.
Success:
- A browser agent can be assigned a task (“grab console errors”) and return a result.

### Phase E — UI
Deliver:
- Minimal web UI to view events + send control events.
Success:
- Human can run a thread for N minutes, mute/prod, and see agent outputs without the terminal.

## 9) Key open questions (with suggested defaults)

1) **Where should the always-on daemon live?**
   - Default: local user process started manually once per day/session (launchd later).

2) **Do we require server/network at all?**
   - Default: yes for browser integration + streaming. Keep file log as audit trail, but expose it via localhost API so every client has one consistent interface.

3) **Agent invocation style**
   - Default: stateless “spawn per task” until proven insufficient.

4) **Thinking visibility**
   - Default: presence only (idle/thinking/typing) + final messages; no token streaming.

5) **Thread identity**
   - Default: a thread is created on first message; you can name it later via control event.

## 10) What I need from you to finalize the plan

Pick defaults for:
- Default TTL: 120s ok, or do you want 2m/5m by default?
- Agent set: which agents/harnesses are “must support” in Phase A (Codex + Claude Code, or add browser immediately)?
- Browser integration expectation: are you ok with “persistent tab/client required” for browser agent auto‑participation, or is “manual attach” acceptable for MVP?
