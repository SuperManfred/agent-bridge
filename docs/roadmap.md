# Roadmap

This roadmap is organized as “base camps”: each is a usable system even if later camps are never built.

## Base camp 0 (today): shared thread + audit log + UI

Acceptance criteria:
- Create a thread and append message events.
- Tail events via SSE (with polling fallback).
- Threads can be discovered and named via UI or API.

## Base camp 1: spec-first cleanup

Acceptance criteria:
- `docs/spec.md` and `docs/api.md` agree on an explicit “v0 vs v1” boundary.
- “Room vs thread” naming decision recorded.
- Clear “what counts as v1 complete” checklist.
- Terminology aligned with Codex/Claude Code where applicable.

## v1 definition of done (daily-usable)

- Human can have a conversation with 2+ agents without copy/paste relaying.
- Any participant can see who is present/thinking (ephemeral presence).
- Human can mute/prod agents when a thread gets noisy.
- Full conversation is reconstructable from append-only logs.

## Base camp 2: richer participation signals (optional)

Goal:
- Reduce talking-over / improve turn-taking with presence/thinking signals.

Acceptance criteria (tentative):
- At least one visible (ephemeral) signal in the UI that a participant is “thinking” or “active”.

## Base camp 3: automation (optional, but likely)

Goal:
- Agents can respond without the human copy/paste loop.

Important:
- This should preserve transparency and not become an opaque middleman.

Open question:
- What minimal automation still feels like “participants talking”, not “a coordinator speaking for them”.

Acceptance criteria (v1 coordinator):
- A local always-on process can watch thread events and auto-invoke configured harness wrappers for targeted messages.
- The invoked harness reply is appended back into the same thread with `meta.reply_to` referencing the triggering message.

## Base camp 4: invited thread feels “alive” (opt-in)

Goal:
- Make small threads feel like real conversation without reintroducing global fanout.

Acceptance criteria:
- A per-thread control enables “auto-invoke invited participants” for `from="user"` + `to="all"` messages with no explicit `@mentions`.
- Default remains conservative: off by default, enabled explicitly per thread.
- Coordinator still invokes **only** invited participants, and respects mute/pause/discussion.
- UI makes the mode visible and easy to toggle in-thread.

## Base camp 5: invite bootstraps agents (no manual copy/paste)

Goal:
- Inviting a participant should also make it easy to actually initialize a running client/session.

Acceptance criteria:
- UI client/model choices are populated from local ai-registry (with fallback to free-text).
- UI can generate a “Join this thread” command/prompt per invited participant (copy-first MVP).
- Optionally: one-click “Open Terminal” can be added later, but copy-first must be excellent.

## Base camp 6: readability + response formatting

Goal:
- Make long-lived threads scannable and comfortable to use.

Acceptance criteria:
- UI clearly shows replies (`meta.reply_to`) and coordinator-assisted messages (`meta.tags`).
- Add an “automatic response formatting” policy (role-aware templates) that keeps thread outputs compact and consistent without becoming rigid.
