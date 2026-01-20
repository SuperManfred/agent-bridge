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
    profile: dict[str, Any] | None = None


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

def _parse_control_content(evt: dict[str, Any]) -> dict[str, Any] | None:
    content = evt.get("content")
    if isinstance(content, str) and content.strip().startswith("{"):
        try:
            content = json.loads(content)
        except json.JSONDecodeError:
            return None
    if not isinstance(content, dict):
        return None
    return content

def _default_control_state() -> dict[str, Any]:
    return {
        "paused": False,
        "muted": set(),
        "discussion": {"on": False, "allow_agent_mentions": False},
    }

def _apply_control_content_to_state(state: dict[str, Any], content: dict[str, Any]) -> None:
    # Mute/unmute are incremental so multiple participants can be muted.
    mute = content.get("mute")
    if isinstance(mute, dict):
        mode = str(mute.get("mode") or "hard")
        targets = mute.get("targets")
        if mode == "hard" and isinstance(targets, list):
            muted: set[str] = state.setdefault("muted", set())
            for t in targets:
                participant_id = str(t).strip()
                if participant_id:
                    muted.add(participant_id)

    unmute = content.get("unmute")
    if isinstance(unmute, dict):
        targets = unmute.get("targets")
        if isinstance(targets, list):
            muted = state.setdefault("muted", set())
            for t in targets:
                participant_id = str(t).strip()
                if participant_id:
                    muted.discard(participant_id)

    # Pause/discussion are last-write-wins.
    pause = content.get("pause")
    if isinstance(pause, dict):
        state["paused"] = bool(pause.get("on", True))

    discussion = content.get("discussion")
    if isinstance(discussion, dict):
        on = bool(discussion.get("on", True))
        allow_agent_mentions = bool(discussion.get("allow_agent_mentions", on))
        state["discussion"] = {"on": on, "allow_agent_mentions": allow_agent_mentions}

def _control_state_before_event(events: list[dict[str, Any]], event_id: str) -> dict[str, Any]:
    state = _default_control_state()
    for evt in events:
        if not isinstance(evt, dict):
            continue
        if str(evt.get("id") or "") == event_id:
            break
        if str(evt.get("type") or "") != "control":
            continue
        if str(evt.get("from") or "") != "user":
            continue
        content = _parse_control_content(evt)
        if not content:
            continue
        _apply_control_content_to_state(state, content)
    return state

def _fetch_presence(bridge_url: str, thread_id: str) -> dict[str, Any] | None:
    try:
        return _http_json("GET", bridge_url.rstrip("/") + f"/threads/{thread_id}/presence")
    except Exception:
        return None

def _build_participant_index(
    agents: dict[str, AgentConfig],
    presence_snapshot: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    participants: dict[str, dict[str, Any]] = {agent_id: {} for agent_id in agents.keys()}
    if not isinstance(presence_snapshot, dict):
        return participants
    for entry in presence_snapshot.get("participants", []):
        if not isinstance(entry, dict):
            continue
        participant_id = str(entry.get("id") or "")
        if not participant_id:
            continue
        details = entry.get("details")
        if not isinstance(details, dict):
            details = {}
        profile = details.get("profile") if isinstance(details.get("profile"), dict) else details
        if not isinstance(profile, dict):
            profile = {}
        participants[participant_id] = profile
    return participants

def _resolve_mentions(
    mentions: set[str],
    participants: dict[str, dict[str, Any]],
) -> tuple[set[str], dict[str, list[str]], set[str]]:
    reserved = {"all", "everyone", "here"}
    reserved_hits: set[str] = set()
    target_ids: set[str] = set()
    ambiguous: dict[str, list[str]] = {}

    id_map = {pid.lower(): pid for pid in participants.keys()}
    nickname_map: dict[str, list[str]] = {}
    role_map: dict[str, set[str]] = {}
    client_map: dict[str, set[str]] = {}
    model_map: dict[str, set[str]] = {}

    for pid, profile in participants.items():
        nickname = profile.get("nickname")
        if isinstance(nickname, str) and nickname.strip():
            nickname_map.setdefault(nickname.lower(), []).append(pid)
        client = profile.get("client")
        if isinstance(client, str) and client.strip():
            client_map.setdefault(client.lower(), set()).add(pid)
        model = profile.get("model")
        if isinstance(model, str) and model.strip():
            model_map.setdefault(model.lower(), set()).add(pid)
        roles = profile.get("roles")
        if isinstance(roles, list):
            for role in roles:
                if isinstance(role, str) and role.strip():
                    role_map.setdefault(role.lower(), set()).add(pid)

    for mention in sorted(mentions):
        if mention in reserved:
            reserved_hits.add(mention)
            continue
        if mention in id_map:
            target_ids.add(id_map[mention])
            continue
        if mention in nickname_map:
            ids = sorted(nickname_map[mention])
            if len(ids) == 1:
                target_ids.add(ids[0])
            else:
                ambiguous[mention] = ids
            continue
        category_targets: set[str] = set()
        if mention in role_map:
            category_targets.update(role_map[mention])
        if mention in client_map:
            category_targets.update(client_map[mention])
        if mention in model_map:
            category_targets.update(model_map[mention])
        if category_targets:
            target_ids.update(category_targets)
    return target_ids, ambiguous, reserved_hits

def _participant_display(participant_id: str, profile: dict[str, Any]) -> str:
    nickname = profile.get("nickname")
    if isinstance(nickname, str) and nickname.strip():
        nick = nickname.strip()
        client = profile.get("client")
        model = profile.get("model")
        if isinstance(client, str) and client.strip() and isinstance(model, str) and model.strip():
            return f"{nick} ({client.strip()}/{model.strip()})"
        if isinstance(client, str) and client.strip():
            return f"{nick} ({client.strip()})"
        if isinstance(model, str) and model.strip():
            return f"{nick} ({model.strip()})"
        return nick
    client = profile.get("client")
    model = profile.get("model")
    if isinstance(client, str) and client.strip() and isinstance(model, str) and model.strip():
        return f"{client.strip()}/{model.strip()}"
    if isinstance(client, str) and client.strip():
        return client.strip()
    if isinstance(model, str) and model.strip():
        return model.strip()
    return participant_id


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

def _post_presence(
    bridge_url: str,
    thread_id: str,
    participant_id: str,
    state: str,
    details: dict[str, Any] | None = None,
) -> None:
    try:
        payload: dict[str, Any] = {"from": participant_id, "state": state}
        if details is not None:
            payload["details"] = details
        _http_json(
            "POST",
            bridge_url.rstrip("/") + f"/threads/{thread_id}/presence",
            payload=payload,
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
    enable_broadcast = bool(cfg_raw.get("enable_broadcast", True))
    broadcast_senders = cfg_raw.get("broadcast_senders", ["user"])
    if not isinstance(broadcast_senders, list) or not all(isinstance(x, str) for x in broadcast_senders):
        broadcast_senders = ["user"]
    broadcast_agents = cfg_raw.get("broadcast_agents", [])
    if not isinstance(broadcast_agents, list) or not all(isinstance(x, str) for x in broadcast_agents):
        broadcast_agents = []
    presence_heartbeat_s = float(cfg_raw.get("presence_heartbeat_s", 10))
    if presence_heartbeat_s < 0:
        presence_heartbeat_s = 10

    agents_raw = cfg_raw.get("agents", {})
    agents: dict[str, AgentConfig] = {}
    if isinstance(agents_raw, dict):
        for agent_id, a in agents_raw.items():
            if not isinstance(a, dict):
                continue
            cmd = a.get("command")
            if not isinstance(cmd, list) or not all(isinstance(x, str) and x for x in cmd):
                continue
            profile = a.get("profile")
            profile_out: dict[str, Any] | None = None
            if isinstance(profile, dict):
                profile_out = {}
                for k in ("client", "model", "nickname"):
                    v = profile.get(k)
                    if isinstance(v, str) and v.strip():
                        profile_out[k] = v.strip()
                roles = profile.get("roles")
                if isinstance(roles, list):
                    profile_out["roles"] = [str(r).strip() for r in roles if str(r).strip()]
            agents[str(agent_id)] = AgentConfig(
                command=[str(x) for x in cmd],
                cwd=str(a["cwd"]) if "cwd" in a and a["cwd"] is not None else None,
                env={str(k): str(v) for k, v in (a.get("env") or {}).items()} if isinstance(a.get("env"), dict) else None,
                profile=profile_out,
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
    active_invocations: set[tuple[str, str]] = set()
    last_presence_heartbeat = 0.0

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

        now_s = time.time()
        if presence_heartbeat_s and now_s - last_presence_heartbeat >= presence_heartbeat_s:
            for t in threads:
                thread_id = t.get("id")
                if not isinstance(thread_id, str) or not thread_id:
                    continue
                # Make agents visible in every thread by default (local-first UX).
                for agent_id, agent_cfg in agents.items():
                    if (thread_id, agent_id) in active_invocations:
                        continue
                    details = agent_cfg.profile if agent_cfg.profile else None
                    _post_presence(bridge_url, thread_id, agent_id, "listening", details=details)
                _post_presence(
                    bridge_url,
                    thread_id,
                    coordinator_id,
                    "listening",
                    details={"client": "agent-bridge", "model": "coordinator", "nickname": "coordinator"},
                )
            last_presence_heartbeat = now_s

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

            if not since:
                # no cursor => start at end, do not back-process history
                if events:
                    thread_state["last_ts"] = str(events[-1].get("ts") or thread_state.get("last_ts") or "")
                continue

            seen = processed_ids.setdefault(thread_id, set())
            control_state = _default_control_state()

            for evt in events:
                if not isinstance(evt, dict):
                    continue
                ts = evt.get("ts")
                if not isinstance(ts, str) or not ts:
                    continue

                is_new = ts > since

                # Apply authoritative user controls as we scan so "future" controls
                # never affect earlier messages.
                if str(evt.get("type") or "") == "control" and str(evt.get("from") or "") == "user":
                    content = _parse_control_content(evt)
                    if content:
                        _apply_control_content_to_state(control_state, content)
                    if is_new:
                        thread_state["last_ts"] = ts
                    continue

                if not is_new:
                    continue

                # Always advance cursor for any new event, even if we ignore it.
                thread_state["last_ts"] = ts

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
                paused = bool(control_state.get("paused"))
                if paused:
                    continue

                if evt_to != "all":
                    if evt_to in agents:
                        target_agents = [evt_to]
                    else:
                        continue
                else:
                    # Mentions only; no broadcast fanout.
                    mentions: set[str] = set()
                    discussion = control_state.get("discussion", {"on": False, "allow_agent_mentions": False})
                    allow_mentions_from_sender = evt_from == "user" or (
                        discussion.get("on") and discussion.get("allow_agent_mentions")
                    )
                    if enable_mentions and allow_mentions_from_sender:
                        mentions = _extract_mentions(evt.get("content"), mention_prefix=mention_prefix)
                    if not mentions:
                        continue

                    presence_snapshot = _fetch_presence(bridge_url, thread_id)
                    participants = _build_participant_index(agents, presence_snapshot)
                    resolved, ambiguous, reserved_hits = _resolve_mentions(mentions, participants)
                    # Prevent "self-wake" loops (an agent mentioning itself in its reply).
                    resolved = {pid for pid in resolved if pid.lower() != evt_from.lower()}

                    if evt_from == "user" and reserved_hits:
                        reserved_list = ", ".join(f"@{m}" for m in sorted(reserved_hits))
                        _append_event(
                            bridge_url,
                            thread_id,
                            {
                                "type": "message",
                                "from": coordinator_id,
                                "to": "user",
                                "content": (
                                    f"Reserved mention(s) {reserved_list} are not supported. "
                                    "Please mention specific participants (e.g. @codex) or use to=<participant_id>."
                                ),
                                "meta": {"reply_to": evt_id, "tags": ["coordinator"]},
                            },
                        )

                    if ambiguous:
                        lines = []
                        for mention, ids in sorted(ambiguous.items()):
                            labels = [f"{pid} — {_participant_display(pid, participants.get(pid, {}))}" for pid in ids]
                            lines.append(f"@{mention}: {', '.join(labels)}")
                        _append_event(
                            bridge_url,
                            thread_id,
                            {
                                "type": "message",
                                "from": coordinator_id,
                                "to": "user",
                                "content": (
                                    "Nickname ambiguity. Please clarify by re-sending with to=<participant_id> "
                                    "or @<participant_id>:\n" + "\n".join(lines)
                                ),
                                "meta": {"reply_to": evt_id, "tags": ["coordinator"]},
                            },
                        )

                    if resolved:
                        target_agents = sorted([a for a in resolved if a in agents])
                    else:
                        target_agents = []

                    if not target_agents:
                        continue

                muted_targets = control_state.get("muted", set())
                if muted_targets:
                    target_agents = [a for a in target_agents if a not in muted_targets]
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
                    active_invocations.add((thread_id, agent_id))
                    _post_presence(bridge_url, thread_id, agent_id, "thinking")
                    try:
                        rc, out, err = _run_agent_adapter(agent_id, agent_cfg, adapter_payload, timeout_s=adapter_timeout_s)
                    except subprocess.TimeoutExpired:
                        rc, out, err = 124, "", f"adapter timeout after {adapter_timeout_s}s"
                    except Exception as e:
                        rc, out, err = 125, "", f"adapter error: {e}"
                    finally:
                        active_invocations.discard((thread_id, agent_id))
                        _post_presence(bridge_url, thread_id, agent_id, "listening")

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

            _save_json_file(state_path, state)

        time.sleep(poll_threads_s)


if __name__ == "__main__":
    raise SystemExit(main())
