# Vision

## Problem statement

When working with multiple LLM “agents” (different harnesses, models, or skill profiles), the human becomes a copy/paste bottleneck. This makes collaboration stop-and-go, context-jarring, and less productive than a small group of humans collaborating fluidly.

Agent Bridge exists to provide a shared, auditable conversation substrate where:
- humans and agents can participate without manual relaying between participants
- participants can “listen in” and join when it makes sense
- the system avoids devolving into chaotic, unbounded chatter

In other words: it aims to feel closer to a small group of humans collaborating (fluid turn-taking, “tap on the shoulder” to invite input) than today’s rigid request/response loops.

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
