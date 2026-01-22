#!/usr/bin/env bash
set -euo pipefail

# Adapter for Claude Code CLI.
# Reads JSON payload on stdin, builds prompt, invokes claude -p, outputs reply.

claude_bin="${CLAUDE_BIN:-claude}"

if ! command -v "$claude_bin" >/dev/null 2>&1; then
  echo "claude-code adapter error: '$claude_bin' not found in PATH" >&2
  echo "  PATH=$PATH" >&2
  echo "  Set CLAUDE_BIN to override" >&2
  exit 127
fi

# Read payload to temp file
tmp_payload="$(mktemp -t agent-bridge-payload.XXXXXX)"
trap 'rm -f "$tmp_payload"' EXIT

cat > "$tmp_payload"

# Guard: fail early if no payload
if [ ! -s "$tmp_payload" ]; then
  echo "claude-code adapter error: no stdin payload received" >&2
  exit 2
fi

# Build prompt from payload using Python
read_result="$(python3 - "$tmp_payload" <<'PYSCRIPT'
import json
import sys

payload_file = sys.argv[1]
with open(payload_file, 'r') as f:
    d = json.load(f)

thread_id = d.get("thread", {}).get("id")
trigger = d.get("trigger", {}) or {}
ctx = d.get("context_window", []) or []
participant = d.get("participant", {}) or {}
profile = participant.get("profile", {}) if isinstance(participant, dict) else {}
model = profile.get("model") if isinstance(profile, dict) else None

def fmt_event(e):
    ts = e.get("ts", "")
    fr = e.get("from", "")
    to = e.get("to", "")
    ty = e.get("type", "")
    content = e.get("content", "")
    if isinstance(content, (dict, list)):
        content = json.dumps(content, ensure_ascii=False)
    return f"[{ts}] {fr} -> {to} ({ty}): {content}"

lines = []
lines.append("You are Claude Code participating in an Agent Bridge thread.")
lines.append("Reply ONCE with your best contribution.")
lines.append("Keep it concise and actionable.")
lines.append("")
lines.append(f"Thread: {thread_id}")
lines.append(f"Replying to event: {trigger.get('id')} from {trigger.get('from')}")
lines.append(f"Participant: {participant.get('id')}")
lines.append("")
primer = ""
try:
    with open("docs/bridge-agent-primer.md", "r") as primer_file:
        primer = primer_file.read().strip()
except OSError:
    primer = ""
if primer:
    lines.append("Bridge primer:")
    lines.append(primer)
    lines.append("")
lines.append("Recent context (most recent last):")
for e in ctx[-25:]:
    if isinstance(e, dict):
        lines.append(fmt_event(e))
lines.append("")
lines.append("Message to respond to:")
content = trigger.get("content", "")
if isinstance(content, (dict, list)):
    content = json.dumps(content, ensure_ascii=False)
lines.append(str(content))
print(thread_id or "")
print(model or "")
print("\n".join(lines))
PYSCRIPT
)"

thread_id="$(echo "$read_result" | head -1)"
model="$(echo "$read_result" | sed -n '2p')"
prompt="$(echo "$read_result" | tail -n +3)"

claude_model_args=()
if [ -n "${model:-}" ]; then
  claude_model_args=(--model "$model")
fi

printf "%s" "$prompt" | "$claude_bin" -p --output-format text --permission-mode bypassPermissions --tools "default" "${claude_model_args[@]}" --no-session-persistence
