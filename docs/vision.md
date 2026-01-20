# Vision

## Problem statement

When working with multiple LLM “agents” (different harnesses, models, or skill profiles), the human becomes a copy/paste bottleneck. This makes collaboration stop-and-go, context-jarring, and less productive than a small group of humans collaborating fluidly.

Agent Bridge exists to provide a shared, auditable conversation substrate where:
- humans and agents can participate without manual relaying between participants
- participants can “listen in” and join when it makes sense
- the system avoids devolving into chaotic, unbounded chatter

In other words: it aims to feel closer to a small group of humans collaborating (fluid turn-taking, “tap on the shoulder” to invite input) than today’s rigid request/response loops.

## North star + constraints (v1)

- **Domain-general conversation medium**: not “a software-dev workflow tool”, but a substrate that can support software work well.
- **Human-like fluidity**: default toward natural, self-organising conversation rather than rigid speaking order.
- **No orchestrator**: avoid a central intermediary that mediates or “speaks for” participants; any automation must be a visible participant.
- **Policy ≠ transport**: the bridge stores/moves events; participation rules are optional, adjustable, and explicit.
- **Perception primitives first**: prioritise presence + “who is doing what” cues (listening/thinking/typing) so participants can coordinate without heavy protocol.
- **Default safety**: coordinator auto-actions are conservative by default (explicit `to=<id>` and human mentions); broader fanout is opt-in per thread.
- **Side-channels are explicit**: allow separate threads for focused detail, link back with a short summary, and avoid accidental context consumption.
- **Cacophony control without rigidity**: use lightweight escape hatches (mute/pause/prod) and scoping to reduce noise without forcing a workflow.

## Core goals (v1)

1. **Shared audit trail**
   - A canonical, append-only event log per conversation thread.
   - Everything important is reconstructable from the log.
2. **Low-friction multi-participant collaboration**
   - Multiple agents with different specialties can contribute to the same thread.
3. **Anti-cacophony controls**
   - Mechanisms to reduce talking-over / runaway output when needed.
   - Human retains practical ability to steer and pause participation.
   - Positive framing: make it easy for participants to coordinate turn-taking (e.g., seeing who is “thinking”).
4. **Local-first**
   - Designed for “me on localhost” initially (no SaaS assumptions).

## Principles

- **Transparency over cleverness**: prefer readable logs and predictable behavior.
- **Append-only as default**: edits are new events, not mutations of history.
- **Policy is separate from transport**: the bridge moves and stores events; participation policy is tunable.
- **Small steps**: prove “fluid, multi-agent conversation” with 1 human + 2–3 agents before scaling.

## Non-goals (v1)

- Multi-tenant security, public internet exposure, or enterprise-grade auth.
- Perfect “human-like” conversational overlap; we aim for practical, usable fluidity.
- Driving every harness as a fully interactive session (some will always be “job mode”).
