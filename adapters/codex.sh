#!/usr/bin/env bash
set -euo pipefail

# Adapter for Codex CLI.
# Reads JSON payload on stdin, builds prompt, invokes codex exec, outputs reply.
# Supports session resumption via XDG-based isolation per thread.

# Error trap for debugging
trap 'echo "[codex adapter] failed at line $LINENO, exit code $?" >&2' ERR

codex_bin="${CODEX_BIN:-codex}"
homes_base="${CODEX_HOMES_BASE:-/tmp/agent-bridge-homes}"

if ! command -v "$codex_bin" >/dev/null 2>&1; then
  echo "codex adapter error: '$codex_bin' not found in PATH" >&2
  echo "  PATH=$PATH" >&2
  echo "  Set CODEX_BIN to override" >&2
  exit 127
fi

# Read payload to temp file
tmp_payload="$(mktemp -t agent-bridge-payload.XXXXXX)"
tmp_out="$(mktemp -t agent-bridge-codex-last.XXXXXX)"
tmp_stderr="$(mktemp -t agent-bridge-codex-stderr.XXXXXX)"
trap 'rm -f "$tmp_payload" "$tmp_out" "$tmp_stderr"; echo "[codex adapter] cleanup done" >&2' EXIT

cat > "$tmp_payload"

# Guard: fail early if no payload
if [ ! -s "$tmp_payload" ]; then
  echo "codex adapter error: no stdin payload received" >&2
  exit 2
fi

# Extract thread_id and build prompt from payload
read_result="$(python3 - "$tmp_payload" <<'PYSCRIPT'
import json
import sys

payload_file = sys.argv[1]
with open(payload_file, 'r') as f:
    d = json.load(f)

thread_id = d.get("thread", {}).get("id") or "unknown"
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
lines.append("You are Codex participating in an Agent Bridge thread.")
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

# Output thread_id on first line, prompt on rest
print(thread_id)
print(model or "")
print("\n".join(lines))
PYSCRIPT
)"

thread_id="$(echo "$read_result" | head -1)"
model="$(echo "$read_result" | sed -n '2p')"
prompt="$(echo "$read_result" | tail -n +3)"

# Per-thread isolation via XDG directories
# This isolates Codex's "last" session state per thread
thread_home="$homes_base/$thread_id"
mkdir -p "$thread_home/.config" "$thread_home/.local/state" "$thread_home/.local/share"

# Copy essential Codex config (auth) if not present
# Codex uses ~/.codex (relative to HOME), NOT XDG_CONFIG_HOME
# When running under launchd, HOME might be / or something unexpected
# So we try multiple locations to find the original codex config
original_codex_dir=""
for candidate in "$HOME/.codex" "/Users/${USER:-$(whoami)}/.codex" "/Users/MN/.codex"; do
  if [ -d "$candidate" ]; then
    original_codex_dir="$candidate"
    break
  fi
done

if [ ! -f "$thread_home/.codex/config.toml" ] && [ -n "$original_codex_dir" ]; then
  mkdir -p "$thread_home/.codex"
  # Copy auth if exists
  [ -f "$original_codex_dir/auth.json" ] && cp "$original_codex_dir/auth.json" "$thread_home/.codex/" 2>/dev/null || true
  # Copy config.toml if exists
  [ -f "$original_codex_dir/config.toml" ] && cp "$original_codex_dir/config.toml" "$thread_home/.codex/" 2>/dev/null || true
  # Copy config.json if exists
  [ -f "$original_codex_dir/config.json" ] && cp "$original_codex_dir/config.json" "$thread_home/.codex/" 2>/dev/null || true
  echo "[codex adapter] copied config from $original_codex_dir to $thread_home/.codex" >&2
elif [ -z "$original_codex_dir" ]; then
  echo "[codex adapter] WARNING: could not find original codex config directory" >&2
fi

export HOME="$thread_home"
export XDG_CONFIG_HOME="$thread_home/.config"
export XDG_STATE_HOME="$thread_home/.local/state"
export XDG_DATA_HOME="$thread_home/.local/share"

# Check if we have an existing session for this thread
session_marker="$thread_home/.has_codex_session"
use_resume=false
if [ -f "$session_marker" ]; then
  use_resume=true
fi

echo "[codex adapter] thread=$thread_id use_resume=$use_resume HOME=$HOME" >&2

codex_model_args=()
if [ -n "${model:-}" ]; then
  codex_model_args=(-m "$model")
fi

if $use_resume; then
  # Resume previous session
  echo "[codex adapter] running: codex exec resume --last ..." >&2
  printf "%s" "$prompt" | "$codex_bin" exec --sandbox workspace-write ${codex_model_args[@]+"${codex_model_args[@]}"} -C "$(pwd)" --output-last-message "$tmp_out" resume --last - 2>>"$tmp_stderr" || {
    echo "[codex adapter] resume failed, trying fresh session" >&2
    rm -f "$session_marker"
    printf "%s" "$prompt" | "$codex_bin" exec --sandbox workspace-write ${codex_model_args[@]+"${codex_model_args[@]}"} -C "$(pwd)" --output-last-message "$tmp_out" - 2>>"$tmp_stderr"
  }
else
  # Fresh session
  echo "[codex adapter] running: codex exec ..." >&2
  printf "%s" "$prompt" | "$codex_bin" exec --sandbox workspace-write ${codex_model_args[@]+"${codex_model_args[@]}"} -C "$(pwd)" --output-last-message "$tmp_out" - 2>>"$tmp_stderr"
fi

# Mark that this thread now has a session that can be resumed
touch "$session_marker"

# Check if output was produced
if [ ! -s "$tmp_out" ]; then
  echo "[codex adapter] warning: no output produced" >&2
  echo "[codex adapter] stderr was:" >&2
  cat "$tmp_stderr" >&2
fi

cat "$tmp_out"
