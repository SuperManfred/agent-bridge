#!/usr/bin/env python3
"""
Coordinator (always-on) for Agent Bridge.

Watches thread events and invokes configured agent adapters for targeted messages.

Config:
  coordinator.config.json (see docs/coordinator.md)

Adapter contract:
  - stdin: JSON payload (thread + triggering event + recent context)
  - stdout: agent reply (text)
  - exit code: 0 success; non-zero failure (coordinator posts an error message)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = BASE_DIR / "coordinator.config.json"
DEFAULT_STATE_PATH = BASE_DIR / "conversations" / "coordinator_state.json"


@dataclass(frozen=True)
class AgentConfig:
    command: list[str]
    cwd: str | None = None
    env: dict[str, str] | None = None


def _http_json(method: str, url: str, payload: dict[str, Any] | None = None, timeout_s: int = 10) -> Any:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        body = resp.read().decode("utf-8")
        if not body:
            return None
        return json.loads(body)


def _load_json_file(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _save_json_file(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(value, f, indent=2, sort_keys=True)
    tmp.replace(path)


def _now_iso() -> str:
    # server.py uses datetime.now().isoformat(); keep consistent enough
    import datetime as _dt

    return _dt.datetime.now().isoformat()


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 20] + "\n\n[truncated]\n"

def _extract_mentions(content: Any, mention_prefix: str) -> set[str]:
    if not isinstance(content, str):
        return set()
    prefix = mention_prefix or "@"
    if not prefix:
        prefix = "@"
    mentions: set[str] = set()
    for token in content.split():
        if token.startswith(prefix) and len(token) > len(prefix):
            mention = token[len(prefix) :]
            # strip common trailing punctuation
            mention = mention.rstrip(".,:;!?)]}\"'")
            if mention:
                mentions.add(mention.lower())
    return mentions

def _thread_discussion_policy(events: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Derive discussion policy from append-only control events.

    Expected control content shape (recommended):
      {"discussion": {"on": true, "allow_agent_mentions": true}}

    The latest matching control event wins.
    """
    policy = {"on": False, "allow_agent_mentions": False}
    for evt in reversed(events):
        if not isinstance(evt, dict):
            continue
        if str(evt.get("type") or "") != "control":
            continue
        content = evt.get("content")
        if isinstance(content, str) and content.strip().startswith("{"):
            try:
                content = json.loads(content)
            except json.JSONDecodeError:
                continue
        if not isinstance(content, dict):
            continue
        discussion = content.get("discussion")
        if not isinstance(discussion, dict):
            continue
        on = bool(discussion.get("on", True))
        allow_agent_mentions = bool(discussion.get("allow_agent_mentions", on))
        policy = {"on": on, "allow_agent_mentions": allow_agent_mentions}
        break
    return policy


def _read_sse_stream(url: str, timeout_s: int = 60):
    """
    Minimal SSE reader.

    Yields decoded JSON payloads from lines like: "data: {...}"
    Ignores comments/keep-alives.
    """
    req = urllib.request.Request(url, headers={"Accept": "text/event-stream"})
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        for raw in resp:
            try:
                line = raw.decode("utf-8", errors="replace").strip()
            except Exception:
                continue
            if not line:
                continue
            if line.startswith(":"):
                continue
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if not data:
                continue
            try:
                yield json.loads(data)
            except json.JSONDecodeError:
                continue


def _thread_events_url(bridge_url: str, thread_id: str, since: str | None) -> str:
    base = bridge_url.rstrip("/")
    qs = ""
    if since:
        qs = "?since=" + urllib.parse.quote(since)
    return f"{base}/threads/{thread_id}/events{qs}"


def _thread_stream_url(bridge_url: str, thread_id: str, since: str | None) -> str:
    base = bridge_url.rstrip("/")
    qs = ""
    if since:
        qs = "?since=" + urllib.parse.quote(since)
    return f"{base}/threads/{thread_id}/events/stream{qs}"


def _list_threads(bridge_url: str) -> list[dict[str, Any]]:
    data = _http_json("GET", bridge_url.rstrip("/") + "/threads")
    return list(data.get("threads", [])) if isinstance(data, dict) else []


def _fetch_events(bridge_url: str, thread_id: str, since: str | None) -> list[dict[str, Any]]:
    data = _http_json("GET", _thread_events_url(bridge_url, thread_id, since))
    events = data.get("events", []) if isinstance(data, dict) else []
    return list(events)


def _append_event(bridge_url: str, thread_id: str, event: dict[str, Any]) -> dict[str, Any]:
    base = bridge_url.rstrip("/")
    return _http_json("POST", f"{base}/threads/{thread_id}/events", payload=event)


def _build_context_window(events: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    if limit <= 0:
        return []
    return events[-limit:]


def _run_agent_adapter(agent_id: str, cfg: AgentConfig, payload: dict[str, Any], timeout_s: int) -> tuple[int, str, str]:
    env = os.environ.copy()
    if cfg.env:
        env.update({str(k): str(v) for k, v in cfg.env.items()})

    proc = subprocess.run(
        cfg.command,
        input=json.dumps(payload).encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=cfg.cwd or None,
        env=env,
        timeout=timeout_s,
        check=False,
    )
    return proc.returncode, proc.stdout.decode("utf-8", errors="replace"), proc.stderr.decode("utf-8", errors="replace")

def _post_presence(bridge_url: str, thread_id: str, participant_id: str, state: str) -> None:
    try:
        _http_json(
            "POST",
            bridge_url.rstrip("/") + f"/threads/{thread_id}/presence",
            payload={"from": participant_id, "state": state},
            timeout_s=2,
        )
    except Exception:
        # Presence is best-effort; ignore failures.
        return


def main() -> int:
    config_path = Path(os.environ.get("BRIDGE_COORDINATOR_CONFIG", str(DEFAULT_CONFIG_PATH)))
    state_path = Path(os.environ.get("BRIDGE_COORDINATOR_STATE", str(DEFAULT_STATE_PATH)))

    cfg_raw = _load_json_file(config_path, default=None)
    if not isinstance(cfg_raw, dict):
        print(f"Missing/invalid config: {config_path}", file=sys.stderr)
        print("See docs/coordinator.md for coordinator.config.json format.", file=sys.stderr)
        return 2

    bridge_url = str(cfg_raw.get("bridge_url", "http://localhost:5111"))
    coordinator_id = str(cfg_raw.get("coordinator_id", "bridge-coordinator"))
    max_reply_chars = int(cfg_raw.get("max_reply_chars", 8000))
    context_window_size = int(cfg_raw.get("context_window_size", 25))
    adapter_timeout_s = int(cfg_raw.get("adapter_timeout_s", 600))
    poll_threads_s = float(cfg_raw.get("poll_threads_s", 5))
    startup_mode = str(cfg_raw.get("startup_mode", "end")).strip().lower() or "end"
    enable_mentions = bool(cfg_raw.get("enable_mentions", True))
    mention_prefix = str(cfg_raw.get("mention_prefix", "@"))
    mention_senders = cfg_raw.get("mention_senders", ["user"])
    if not isinstance(mention_senders, list) or not all(isinstance(x, str) for x in mention_senders):
        mention_senders = ["user"]
    enable_broadcast = bool(cfg_raw.get("enable_broadcast", True))
    broadcast_senders = cfg_raw.get("broadcast_senders", ["user"])
    if not isinstance(broadcast_senders, list) or not all(isinstance(x, str) for x in broadcast_senders):
        broadcast_senders = ["user"]
    broadcast_agents = cfg_raw.get("broadcast_agents", [])
    if not isinstance(broadcast_agents, list) or not all(isinstance(x, str) for x in broadcast_agents):
        broadcast_agents = []

    agents_raw = cfg_raw.get("agents", {})
    agents: dict[str, AgentConfig] = {}
    if isinstance(agents_raw, dict):
        for agent_id, a in agents_raw.items():
            if not isinstance(a, dict):
                continue
            cmd = a.get("command")
            if not isinstance(cmd, list) or not all(isinstance(x, str) and x for x in cmd):
                continue
            agents[str(agent_id)] = AgentConfig(
                command=[str(x) for x in cmd],
                cwd=str(a["cwd"]) if "cwd" in a and a["cwd"] is not None else None,
                env={str(k): str(v) for k, v in (a.get("env") or {}).items()} if isinstance(a.get("env"), dict) else None,
            )

    if not agents:
        print("No valid agents configured under config.agents", file=sys.stderr)
        return 2

    state = _load_json_file(state_path, default={"threads": {}})
    if not isinstance(state, dict):
        state = {"threads": {}}
    if "threads" not in state or not isinstance(state["threads"], dict):
        state["threads"] = {}

    processed_ids: dict[str, set[str]] = {}

    print(f"[{_now_iso()}] coordinator starting", flush=True)
    print(f"- bridge_url: {bridge_url}", flush=True)
    print(f"- coordinator_id: {coordinator_id}", flush=True)
    print(f"- agents: {', '.join(sorted(agents.keys()))}", flush=True)
    print(f"- startup_mode: {startup_mode}", flush=True)

    # By default, start "from end" so the system feels alive now rather than
    # grinding through historical backlog.
    if startup_mode not in ("end", "resume"):
        print(f"[{_now_iso()}] invalid startup_mode={startup_mode!r}; using 'end'", file=sys.stderr, flush=True)
        startup_mode = "end"
    if startup_mode == "end":
        try:
            threads = _list_threads(bridge_url)
            for t in threads:
                thread_id = t.get("id")
                if not isinstance(thread_id, str) or not thread_id:
                    continue
                try:
                    events = _fetch_events(bridge_url, thread_id, since=None)
                except Exception:
                    continue
                if not events:
                    continue
                last_ts = events[-1].get("ts")
                if isinstance(last_ts, str) and last_ts:
                    state["threads"].setdefault(thread_id, {})
                    state["threads"][thread_id]["last_ts"] = last_ts
            _save_json_file(state_path, state)
        except Exception as e:
            print(f"[{_now_iso()}] startup seek failed: {e}", file=sys.stderr, flush=True)

    while True:
        try:
            threads = _list_threads(bridge_url)
        except Exception as e:
            print(f"[{_now_iso()}] error listing threads: {e}", file=sys.stderr, flush=True)
            time.sleep(2)
            continue

        for t in threads:
            thread_id = t.get("id")
            if not isinstance(thread_id, str) or not thread_id:
                continue

            thread_state = state["threads"].setdefault(thread_id, {})
            since = thread_state.get("last_ts")
            if since is not None and not isinstance(since, str):
                since = None

            # Pull recent window for context + also to handle cases where SSE isn't used.
            try:
                events = _fetch_events(bridge_url, thread_id, since=None)
            except Exception as e:
                print(f"[{_now_iso()}] error fetching events for {thread_id}: {e}", file=sys.stderr, flush=True)
                continue
            discussion = _thread_discussion_policy(events)

            # Process only new events relative to persisted cursor.
            new_events: list[dict[str, Any]] = []
            if since:
                for evt in events:
                    if isinstance(evt, dict) and str(evt.get("ts", "")) > since:
                        new_events.append(evt)
            else:
                # no cursor => start at end, do not back-process history
                if events:
                    thread_state["last_ts"] = str(events[-1].get("ts") or thread_state.get("last_ts") or "")
                continue

            if not new_events:
                continue

            seen = processed_ids.setdefault(thread_id, set())
            for evt in new_events:
                if not isinstance(evt, dict):
                    continue
                evt_id = str(evt.get("id") or "")
                if not evt_id or evt_id in seen:
                    continue
                seen.add(evt_id)
                # Cap in-memory seen set
                if len(seen) > 5000:
                    # cheap pruning
                    seen.clear()

                evt_type = str(evt.get("type") or "")
                evt_to = str(evt.get("to") or "all")
                evt_from = str(evt.get("from") or "")
                if evt_from == coordinator_id:
                    continue
                if evt_type != "message":
                    continue
                if evt_to == "user":
                    continue

                target_agents: list[str] = []
                if evt_to != "all":
                    if evt_to in agents:
                        target_agents = [evt_to]
                    else:
                        continue
                else:
                    # Broadcast message. Two options:
                    # - mentions: "@agent-id" in content to target specific agents
                    # - broadcast: invoke configured agents on any user broadcast (small-thread default)
                    mentions: set[str] = set()
                    allow_mentions_from_sender = evt_from in mention_senders
                    if discussion.get("allow_agent_mentions") and evt_from in agents:
                        allow_mentions_from_sender = True
                    if enable_mentions and allow_mentions_from_sender:
                        mentions = _extract_mentions(evt.get("content"), mention_prefix=mention_prefix)
                    if mentions:
                        for m in sorted(mentions):
                            if m in agents:
                                target_agents.append(m)
                    else:
                        if not enable_broadcast:
                            continue
                        if evt_from not in broadcast_senders:
                            continue
                        if broadcast_agents:
                            for a in broadcast_agents:
                                if a in agents:
                                    target_agents.append(a)
                        else:
                            target_agents = sorted(agents.keys())

                    if not target_agents:
                        continue

                context = _build_context_window(events, limit=context_window_size)
                for agent_id in target_agents:
                    agent_cfg = agents[agent_id]
                    adapter_payload = {
                        "bridge": {"url": bridge_url},
                        "thread": {"id": thread_id},
                        "trigger": {
                            "id": evt_id,
                            "ts": evt.get("ts"),
                            "type": evt_type,
                            "from": evt_from,
                            "to": evt_to,
                            "content": evt.get("content"),
                        },
                        "context_window": context,
                    }

                    print(f"[{_now_iso()}] invoke {agent_id} for thread={thread_id} event={evt_id}", flush=True)
                    _post_presence(bridge_url, thread_id, agent_id, "thinking")
                    try:
                        rc, out, err = _run_agent_adapter(agent_id, agent_cfg, adapter_payload, timeout_s=adapter_timeout_s)
                    except subprocess.TimeoutExpired:
                        rc, out, err = 124, "", f"adapter timeout after {adapter_timeout_s}s"
                    except Exception as e:
                        rc, out, err = 125, "", f"adapter error: {e}"
                    finally:
                        _post_presence(bridge_url, thread_id, agent_id, "idle")

                    if rc == 0:
                        reply = _truncate(out.strip(), max_chars=max_reply_chars).strip()
                        if not reply:
                            reply = "[no output]"
                        _append_event(
                            bridge_url,
                            thread_id,
                            {
                                "type": "message",
                                "from": agent_id,
                                "to": "all",
                                "content": reply,
                                "meta": {"reply_to": evt_id, "tags": ["coordinator"]},
                            },
                        )
                    else:
                        _append_event(
                            bridge_url,
                            thread_id,
                            {
                                "type": "message",
                                "from": coordinator_id,
                                "to": "all",
                                "content": _truncate(
                                    f"Adapter failed for {agent_id} (exit {rc}).\n\nstderr:\n{err.strip()}\n\nstdout:\n{out.strip()}",
                                    max_chars=4000,
                                ),
                                "meta": {"reply_to": evt_id, "tags": ["coordinator", "error"]},
                            },
                        )

                # advance cursor opportunistically per processed event
                ts = evt.get("ts")
                if isinstance(ts, str) and ts:
                    thread_state["last_ts"] = ts

            _save_json_file(state_path, state)

        time.sleep(poll_threads_s)


if __name__ == "__main__":
    raise SystemExit(main())
