# Coordinator (Always-On)

This document specifies the “always-on” component that removes the need for human nudging by watching thread events and invoking configured harnesses.

Terminology note:
- We use **coordinator** to avoid implying a hidden intermediary that speaks “for” participants.
- The coordinator must behave as a **visible participant** when it writes to a thread.

## Goal

- When a message in a thread targets an agent (e.g., `to="claude-code"`), the system should be able to invoke that agent automatically and append its reply back into the same thread log.
- A thread can start empty: humans/agents can invite participants into the conversation, and only invited participants are invoked in that thread.

## Non-goals (v1 coordinator)

- No “task/result” workflow layer (defer; v1 is `message/control/presence` only).
- No attempt to drive already-running interactive UIs unless a harness exposes a stable API.
- No hidden summarization; if any summary is produced, it must be appended as a visible message from the coordinator identity.

## Operational rule (ironclad)

If you are an agent/implementer participating in this project:
- **Before making any code edits or taking any action that changes the repo, read the bridge thread first.**
- Treat the thread as the coordination plane; do not “go off and implement” based only on local inference.

## Trigger rules (v1)

Given an incoming thread event `evt`:

- The coordinator MUST ignore events where `evt.to == "user"`.
- The coordinator SHOULD ignore events authored by the coordinator itself.
- The coordinator SHOULD invoke the target participant when:
  - `evt.type == "message"` AND `evt.to` matches a configured participant id.

Practical implication:
- If you want an agent to auto-respond, send a message with `to="<agent-id>"` (e.g., `to="codex"`).

Participant invites (v1 direction):
- A thread SHOULD treat participants as invited/initialized via a `control` event (see `docs/invites.md`).
- The coordinator SHOULD only invoke participants that are invited in that thread.

### Mentions (recommended, conservative by default)

To keep conversation flow natural without introducing a “workflow protocol”, the coordinator supports optional mention-based targeting for broadcast messages.

Default behavior:
- If `evt.to == "all"` and the message content contains `@...`, the coordinator MAY treat that as explicit targeting.
- Mentions are enabled by default for the **human** sender (by convention `from="user"`).
- Mentions from non-human participants are disabled by default and require an explicit thread control (see “Discussion mode”).

This avoids forcing the human to always fill a separate `to` field, while still preventing “everyone responds to everything.”

#### Mention targets

Mentions may target:
- a `participant_id` (stable handle)
- a `nickname`
- a `role`
- a `client` (e.g. `@codex`, `@claude`)
- a `model` (e.g. `@gpt-5.2-codex`)

Resolution notes:
- v0 behavior is limited: `@<agent-id>` where `<agent-id>` exactly matches a configured agent id.
- v1 intent is richer: the coordinator resolves mentions against known participant profiles (published via presence and/or persisted events). If a mention is ambiguous, the coordinator should ask for clarification rather than guessing.

### Broadcast fanout (opt-in, off by default)

To avoid reintroducing orchestration-like behavior or runaway chatter:
- If `evt.to == "all"` and there are **no mentions**, the coordinator MUST NOT auto-invoke everyone by default.
- Optional fanout can be enabled explicitly per thread via a control event, and should remain bounded.

## Discussion mode (opt-in, bounded policy loosening)

By default, the coordinator treats agent-to-agent triggers as dangerous because they can create infinite loops.

To allow more “human-like” collaboration (agents can tap in other agents), use an explicit control event in the thread:

```json
{
  "type": "control",
  "from": "user",
  "to": "all",
  "content": {
    "discussion": {
      "on": true,
      "allow_agent_mentions": true
    }
  }
}
```

Behavior (v1):
- When `discussion.allow_agent_mentions` is enabled, non-human participants MAY wake other participants via `@...` mentions in `to="all"` messages.
- Broadcast fanout (agents responding to every agent message) remains disabled unless explicitly configured.

Naming note:
- The key is called `allow_agent_mentions` in v0; v1 intent is “allow non-human participant mentions”.
  - If `allow_agent_mentions` is omitted, implementations MAY treat it as the same value as `discussion.on` (i.e., `on: true` implies mentions are allowed unless explicitly disabled).

Optional (future):
- react to `control` events like `prod`

## Delivery model

The coordinator delivers a targeted message to a participant by invoking an adapter for that participant.

The adapter contract is:
- input: `{thread_id, event_id, from, to, content, context_window}`
- output: a text reply (stdout) and an exit code

The coordinator then appends a new thread event:
- `type="message"`
- `from=<participant id>`
- `to="all"`
- `content=<adapter stdout (possibly truncated)>`
- `meta.reply_to=<original event id>` (recommended)

Transparency requirement:
- Messages appended via the coordinator SHOULD include a marker in metadata (e.g. `meta.tags` includes `coordinator`, and/or `meta.via=<coordinator_id>`).

## Presence (v1)

Presence/thinking/typing is **ephemeral by default**:
- The coordinator MAY expose “agent is running” as ephemeral presence when the server supports it.
- The coordinator MUST NOT spam the thread log with heartbeat/presence events.

Invite-friendly default:
- The coordinator SHOULD NOT mark every configured agent as present in every thread.
- Presence SHOULD reflect invited participants and real activity (listening/thinking transitions).

## Idempotency and reliability

- At-least-once delivery is acceptable.
- The coordinator SHOULD avoid duplicate invocations for the same event id.
- Restart behavior: the coordinator SHOULD persist cursors per thread so it can resume without replaying the full history.

### Startup mode

To avoid replaying old messages on restart (which can feel like “spam”):
- `startup_mode="end"` seeks to the latest event in every thread at startup and begins from there.
- `startup_mode="resume"` preserves stored cursors and resumes from them.

## Configuration

The coordinator reads a local config file mapping participant ids to adapter commands.

Proposed file:
- `coordinator.config.json`

Example:

```json
{
  "bridge_url": "http://localhost:5111",
  "coordinator_id": "bridge-coordinator",
  "enable_mentions": true,
  "mention_prefix": "@",
  "mention_senders": ["user"],
  "enable_broadcast": false,
  "broadcast_senders": ["user"],
  "broadcast_agents": [],
  "agents": {
    "claude-code": {
      "command": ["./adapters/claude_code.sh"]
    },
    "codex": {
      "command": ["./adapters/codex.sh"]
    }
  }
}
```

Adapter commands are executed as subprocesses. They receive a JSON payload on stdin and must write the reply to stdout.

Rationale:
- Different harnesses have different invocation shapes; wrappers keep the coordinator generic.

Note (shell aliases/functions):
- The coordinator (especially under `launchd`) does not run inside your interactive shell.
- Do not rely on shell aliases/functions like `codex_secure`; adapters should call real executables (e.g., `codex`, `claude`).

## Testing

This repo includes `adapters/echo.sh` as a trivial adapter for smoke-testing the coordinator loop without integrating a real harness.

## Agent primer (v1)

Newly-invoked agents SHOULD receive a minimal, unconstraining “bridge primer” so their behavior matches the conversation-first intent.

Reference:
- `docs/bridge-agent-primer.md`

## Always-on on macOS (launchd)

To keep the coordinator running without manual nudging:

1) Copy and edit the example plist:
- `launchd/com.agent-bridge.coordinator.plist.example`

2) Install it:

```bash
cp launchd/com.agent-bridge.coordinator.plist.example ~/Library/LaunchAgents/com.agent-bridge.coordinator.plist
launchctl load -w ~/Library/LaunchAgents/com.agent-bridge.coordinator.plist
```

3) Logs:
- `/tmp/agent-bridge-coordinator.log`
- `/tmp/agent-bridge-coordinator.err.log`

## Always-on Agent Bridge server (launchd)

The coordinator needs the bridge server running.

1) Copy and edit:
- `launchd/com.agent-bridge.server.plist.example`

2) Install:

```bash
cp launchd/com.agent-bridge.server.plist.example ~/Library/LaunchAgents/com.agent-bridge.server.plist
launchctl load -w ~/Library/LaunchAgents/com.agent-bridge.server.plist
```

3) Logs:
- `/tmp/agent-bridge-server.log`
- `/tmp/agent-bridge-server.err.log`

## Scope boundaries (v1)

- Local-only on `localhost` for a single user.
- `from` is a participant label by convention (not a verified identity).
