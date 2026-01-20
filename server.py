#!/usr/bin/env python3
"""
Agent Bridge Server - HTTP bridge for multi-agent communication.

Usage:
    python server.py [--port PORT]

Endpoints:
    GET  /ping      - Health check
    POST /message   - Send a message
    GET  /messages  - Get messages (?since=, ?for=, ?visibility=)
    GET  /latest    - Get most recent message
    POST /broadcast - User message to all agents
    POST /suggest   - Submit improvement suggestion for the bridge itself
    GET  /suggestions - List suggestions
"""

import json
import os
import secrets
import sys
import time
from datetime import datetime
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory, Response, stream_with_context, make_response
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "conversations"
SUGGESTIONS_DIR = BASE_DIR / "suggestions"
THREADS_DIR = DATA_DIR / "threads"
THREADS_INDEX = DATA_DIR / "index.json"

DATA_DIR.mkdir(exist_ok=True)
SUGGESTIONS_DIR.mkdir(exist_ok=True)
THREADS_DIR.mkdir(exist_ok=True)

PRESENCE_TTL_SECONDS = 120
# Ephemeral presence stored in-memory only: {thread_id: {participant_id: {state, updated_at, details?}}}
PRESENCE: dict[str, dict[str, dict]] = {}


BASE32_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _encode_base32(value: int, length: int) -> str:
    """Encode an integer into Crockford Base32 with fixed length."""
    chars = []
    for _ in range(length):
        chars.append(BASE32_ALPHABET[value & 0x1F])
        value >>= 5
    return "".join(reversed(chars))


def ulid() -> str:
    """Generate a ULID-like identifier (48-bit time + 80-bit randomness)."""
    timestamp_ms = int(time.time() * 1000)
    time_part = _encode_base32(timestamp_ms, 10)
    rand_part = _encode_base32(secrets.randbits(80), 16)
    return f"{time_part}{rand_part}"


def get_conversation_file():
    today = datetime.now().strftime("%Y-%m-%d")
    return DATA_DIR / f"{today}.jsonl"


def write_message(message: dict) -> dict:
    now = datetime.now()
    entry = {
        "id": ulid(),
        "timestamp": now.isoformat(),
        "visibility": message.get("visibility", "all"),
        **message
    }
    with open(get_conversation_file(), "a") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def load_threads_index() -> dict:
    if not THREADS_INDEX.exists():
        return {"threads": []}
    with open(THREADS_INDEX, "r") as f:
        return json.load(f)


def save_threads_index(index: dict) -> None:
    tmp_path = THREADS_INDEX.with_suffix(".tmp")
    with open(tmp_path, "w") as f:
        json.dump(index, f, indent=2)
    tmp_path.replace(THREADS_INDEX)


def update_thread_index(thread_id: str, name: str = None) -> dict:
    now = datetime.now().isoformat()
    index = load_threads_index()
    threads = index.get("threads", [])
    for t in threads:
        if t["id"] == thread_id:
            if name is not None:
                t["name"] = name
            t["updated_at"] = now
            save_threads_index(index)
            return t
    entry = {
        "id": thread_id,
        "name": name or "Untitled",
        "created_at": now,
        "updated_at": now
    }
    threads.append(entry)
    index["threads"] = threads
    save_threads_index(index)
    return entry


def thread_file(thread_id: str) -> Path:
    return THREADS_DIR / f"{thread_id}.jsonl"


def write_thread_event(thread_id: str, event: dict) -> dict:
    now = datetime.now().isoformat()
    entry = {
        "id": ulid(),
        "ts": now,
        "thread": thread_id,
        **event
    }
    with open(thread_file(thread_id), "a") as f:
        f.write(json.dumps(entry) + "\n")
    if entry.get("type") == "thread.created":
        update_thread_index(thread_id, name=entry.get("content") or "Untitled")
    if entry.get("type") == "thread.renamed":
        update_thread_index(thread_id, name=entry.get("content") or "Untitled")
    return entry


def read_thread_events(thread_id: str, since: str = None) -> list:
    filepath = thread_file(thread_id)
    if not filepath.exists():
        return []
    events = []
    with open(filepath, "r") as f:
        for line in f:
            if line.strip():
                evt = json.loads(line)
                if since and evt.get("ts", "") <= since:
                    continue
                events.append(evt)
    return events


def read_messages(since: str = None, for_agent: str = None, visibility: str = None) -> list:
    filepath = get_conversation_file()
    if not filepath.exists():
        return []

    messages = []
    with open(filepath, "r") as f:
        for line in f:
            if line.strip():
                msg = json.loads(line)
                if since and msg["timestamp"] <= since:
                    continue
                msg_vis = msg.get("visibility", "all")
                if visibility and msg_vis != visibility and msg_vis != "all":
                    continue
                if for_agent:
                    msg_to = msg.get("to", "all")
                    if msg_to != "all" and msg_to != for_agent:
                        continue
                messages.append(msg)
    return messages


def format_sse_event(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"

def _parse_control_content(evt: dict) -> dict | None:
    content = evt.get("content")
    if isinstance(content, str) and content.strip().startswith("{"):
        try:
            content = json.loads(content)
        except json.JSONDecodeError:
            return None
    if not isinstance(content, dict):
        return None
    return content

def _derive_thread_state(events: list[dict]) -> dict:
    state = {
        "paused": False,
        "muted": set(),
        "discussion": {"on": False, "allow_agent_mentions": False},
    }
    for evt in events:
        if not isinstance(evt, dict):
            continue
        if str(evt.get("type") or "") != "control":
            continue
        if str(evt.get("from") or "") != "user":
            continue
        content = _parse_control_content(evt)
        if not content:
            continue

        mute = content.get("mute")
        if isinstance(mute, dict):
            mode = str(mute.get("mode") or "hard")
            targets = mute.get("targets")
            if mode == "hard" and isinstance(targets, list):
                for t in targets:
                    participant_id = str(t).strip()
                    if participant_id:
                        state["muted"].add(participant_id)

        unmute = content.get("unmute")
        if isinstance(unmute, dict):
            targets = unmute.get("targets")
            if isinstance(targets, list):
                for t in targets:
                    participant_id = str(t).strip()
                    if participant_id:
                        state["muted"].discard(participant_id)

        pause = content.get("pause")
        if isinstance(pause, dict):
            state["paused"] = bool(pause.get("on", True))

        discussion = content.get("discussion")
        if isinstance(discussion, dict):
            on = bool(discussion.get("on", True))
            allow_agent_mentions = bool(discussion.get("allow_agent_mentions", on))
            state["discussion"] = {"on": on, "allow_agent_mentions": allow_agent_mentions}
    return state

def _error_409(code: str, message: str, thread_id: str, participant_id: str):
    return jsonify({
        "error": {
            "code": code,
            "message": message,
            "thread": thread_id,
            "participant": participant_id,
        }
    }), 409

def get_thread_state_snapshot(thread_id: str) -> dict:
    events = read_thread_events(thread_id)
    state = _derive_thread_state(events)
    muted = state.get("muted", set())
    if not isinstance(muted, set):
        muted = set()
    discussion = state.get("discussion")
    if not isinstance(discussion, dict):
        discussion = {"on": False, "allow_agent_mentions": False}
    return {
        "thread": thread_id,
        "state": {
            "paused": bool(state.get("paused")),
            "muted": sorted(muted),
            "discussion": {
                "on": bool(discussion.get("on")),
                "allow_agent_mentions": bool(discussion.get("allow_agent_mentions")),
            },
        },
    }

def set_presence(thread_id: str, participant_id: str, state: str, details: dict | None = None) -> dict:
    now = datetime.now().isoformat()
    thread_presence = PRESENCE.setdefault(thread_id, {})
    existing = thread_presence.get(participant_id) if isinstance(thread_presence.get(participant_id), dict) else {}
    entry = {"state": state, "updated_at": now}
    if details is None:
        # Preserve existing profile/details on state updates so presence transitions
        # (e.g. thinking -> listening) don't erase identity.
        existing_details = existing.get("details") if isinstance(existing, dict) else None
        if isinstance(existing_details, dict):
            entry["details"] = existing_details
    else:
        entry["details"] = details
    thread_presence[participant_id] = entry
    return {"thread": thread_id, "participant": participant_id, **entry}

def get_presence_snapshot(thread_id: str) -> dict:
    now = datetime.now()
    thread_presence = PRESENCE.get(thread_id, {})
    participants = []
    for participant_id, entry in thread_presence.items():
        updated_at = entry.get("updated_at")
        stale = False
        if isinstance(updated_at, str):
            try:
                ts = datetime.fromisoformat(updated_at)
                stale = (now - ts).total_seconds() > PRESENCE_TTL_SECONDS
            except ValueError:
                stale = False
        participants.append({
            "id": participant_id,
            "state": entry.get("state"),
            "updated_at": updated_at,
            "stale": stale,
            "details": entry.get("details"),
        })
    participants.sort(key=lambda p: (p.get("stale") is True, p.get("id") or ""))
    return {"thread": thread_id, "ttl_seconds": PRESENCE_TTL_SECONDS, "participants": participants}

def stream_thread_events(thread_id: str, since: str = None):
    last_ts = since
    if last_ts is None:
        # Start at the end when no cursor is provided.
        events = read_thread_events(thread_id)
        if events:
            last_ts = events[-1].get("ts")
    last_heartbeat = time.time()
    while True:
        events = read_thread_events(thread_id, since=last_ts)
        for evt in events:
            yield format_sse_event(evt)
            last_ts = evt.get("ts") or last_ts
        if time.time() - last_heartbeat >= 15:
            yield ": keep-alive\n\n"
            last_heartbeat = time.time()
        time.sleep(1)


@app.route("/ping", methods=["GET"])
def ping():
    return jsonify({
        "status": "ok",
        "server": "agent-bridge",
        "version": "0.3.0",
        "timestamp": datetime.now().isoformat()
    })


@app.route("/message", methods=["POST"])
def post_message():
    data = request.json
    if not data:
        return jsonify({"error": "No JSON body"}), 400
    if "from" not in data:
        return jsonify({"error": "Missing 'from'"}), 400
    if "content" not in data:
        return jsonify({"error": "Missing 'content'"}), 400

    entry = write_message(data)
    print(f"[{entry['timestamp']}] {data['from']} → {data.get('to', 'all')}: {data['content'][:80]}")
    return jsonify({"received": True, "id": entry["id"], "timestamp": entry["timestamp"]})


@app.route("/threads", methods=["GET"])
def list_threads():
    return jsonify(load_threads_index())


@app.route("/threads", methods=["POST"])
def create_thread():
    data = request.json or {}
    name = data.get("name") or "Untitled"
    thread_id = ulid()
    update_thread_index(thread_id, name=name)
    write_thread_event(thread_id, {
        "type": "thread.created",
        "from": data.get("from", "user"),
        "to": "all",
        "content": name
    })
    return jsonify({"id": thread_id, "name": name})


@app.route("/threads/<thread_id>/events", methods=["GET"])
def get_thread_events(thread_id: str):
    events = read_thread_events(thread_id, since=request.args.get("since"))
    return jsonify({"events": events, "count": len(events)})

@app.route("/threads/<thread_id>/state", methods=["GET"])
def get_thread_state(thread_id: str):
    return jsonify(get_thread_state_snapshot(thread_id))


@app.route("/threads/<thread_id>/events", methods=["POST"])
def post_thread_event(thread_id: str):
    data = request.json
    if not data:
        return jsonify({"error": "No JSON body"}), 400
    if "from" not in data:
        return jsonify({"error": "Missing 'from'"}), 400
    if "content" not in data and data.get("type") == "message":
        return jsonify({"error": "Missing 'content'"}), 400
    if data.get("type") == "message":
        participant_id = str(data.get("from") or "")
        if participant_id != "user":
            events = read_thread_events(thread_id)
            state = _derive_thread_state(events)
            muted = state.get("muted", set())
            if participant_id in muted:
                return _error_409(
                    "participant_muted",
                    "Participant is muted for this thread.",
                    thread_id,
                    participant_id,
                )
            if state.get("paused"):
                return _error_409(
                    "thread_paused",
                    "Thread is paused for non-user participants.",
                    thread_id,
                    participant_id,
                )
    entry = write_thread_event(thread_id, data)
    return jsonify({"received": True, "event": entry})


@app.route("/threads/<thread_id>/events/stream", methods=["GET"])
def get_thread_events_stream(thread_id: str):
    since = request.args.get("since")
    response = Response(
        stream_with_context(stream_thread_events(thread_id, since=since)),
        mimetype="text/event-stream"
    )
    response.headers["Cache-Control"] = "no-cache"
    response.headers["Connection"] = "keep-alive"
    response.headers["X-Accel-Buffering"] = "no"
    return response

@app.route("/threads/<thread_id>/presence", methods=["GET"])
def get_thread_presence(thread_id: str):
    return jsonify(get_presence_snapshot(thread_id))

@app.route("/threads/<thread_id>/presence", methods=["POST"])
def post_thread_presence(thread_id: str):
    data = request.json
    if not data:
        return jsonify({"error": "No JSON body"}), 400
    participant_id = data.get("from")
    state = data.get("state")
    if not participant_id:
        return jsonify({"error": "Missing 'from'"}), 400
    if not state:
        return jsonify({"error": "Missing 'state'"}), 400
    details = data.get("details")
    if details is not None and not isinstance(details, dict):
        return jsonify({"error": "'details' must be an object"}), 400
    entry = set_presence(thread_id, str(participant_id), str(state), details=details)
    return jsonify({"received": True, "presence": entry})

@app.route("/messages", methods=["GET"])
def get_messages():
    messages = read_messages(
        since=request.args.get("since"),
        for_agent=request.args.get("for"),
        visibility=request.args.get("visibility")
    )
    return jsonify({"messages": messages, "count": len(messages)})


@app.route("/latest", methods=["GET"])
def get_latest():
    messages = read_messages(for_agent=request.args.get("for"))
    if not messages:
        return jsonify({"message": None})
    return jsonify({"message": messages[-1]})


@app.route("/broadcast", methods=["POST"])
def broadcast():
    data = request.json
    if not data or "content" not in data:
        return jsonify({"error": "Missing 'content'"}), 400

    entry = write_message({
        "from": "user",
        "to": "all",
        "visibility": "all",
        "type": "broadcast",
        "content": data["content"],
        "context": data.get("context"),
    })
    print(f"[BROADCAST] {data['content'][:80]}")
    return jsonify({"broadcast": True, "id": entry["id"], "timestamp": entry["timestamp"]})


# Suggestions are specifically for improving THIS bridge system
def write_suggestion(suggestion: dict) -> dict:
    now = datetime.now()
    suggestion_id = now.strftime("%Y%m%d%H%M%S%f")
    entry = {
        "id": suggestion_id,
        "timestamp": now.isoformat(),
        "status": "pending",
        **suggestion
    }
    filepath = SUGGESTIONS_DIR / f"{suggestion_id}.json"
    with open(filepath, "w") as f:
        json.dump(entry, f, indent=2)
    return entry


def read_suggestions(status: str = None) -> list:
    suggestions = []
    for filepath in sorted(SUGGESTIONS_DIR.glob("*.json")):
        with open(filepath) as f:
            s = json.load(f)
            if status is None or s.get("status") == status:
                suggestions.append(s)
    return suggestions


@app.route("/suggest", methods=["POST"])
def post_suggestion():
    data = request.json
    if not data:
        return jsonify({"error": "No JSON body"}), 400
    for field in ["from", "title", "description"]:
        if field not in data:
            return jsonify({"error": f"Missing '{field}'"}), 400

    entry = write_suggestion(data)
    print(f"[SUGGESTION] {data['from']}: {data['title']}")
    return jsonify({"submitted": True, "id": entry["id"], "timestamp": entry["timestamp"]})


@app.route("/suggestions", methods=["GET"])
def get_suggestions():
    suggestions = read_suggestions(status=request.args.get("status"))
    return jsonify({"suggestions": suggestions, "count": len(suggestions)})


@app.route("/", methods=["GET"])
def index():
    return jsonify({
        "name": "Agent Bridge",
        "version": "0.3.0",
        "endpoints": {
            "GET /ping": "Health check",
            "POST /message": "Send message (from, to?, content, visibility?)",
            "GET /messages": "Get messages (?since=, ?for=, ?visibility=)",
            "GET /latest": "Get most recent (?for=)",
            "POST /broadcast": "User broadcast (content, context?)",
            "POST /suggest": "Suggest bridge improvement (from, title, description)",
            "GET /suggestions": "List suggestions (?status=)"
        }
    })


def _add_no_cache_headers(response):
    """Add no-cache headers for development - ensures UI changes are always fresh."""
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@app.route("/ui", methods=["GET"])
def ui_index():
    resp = make_response(send_from_directory(BASE_DIR / "ui", "index.html"))
    return _add_no_cache_headers(resp)

@app.route("/ui/rooms/<thread_id>", methods=["GET"])
def ui_room(thread_id: str):
    resp = make_response(send_from_directory(BASE_DIR / "ui", "index.html"))
    return _add_no_cache_headers(resp)

@app.route("/ui/rooms/<thread_id>/messages/<event_id>", methods=["GET"])
def ui_room_message(thread_id: str, event_id: str):
    resp = make_response(send_from_directory(BASE_DIR / "ui", "index.html"))
    return _add_no_cache_headers(resp)


@app.route("/ui/<path:path>", methods=["GET"])
def ui_assets(path: str):
    resp = make_response(send_from_directory(BASE_DIR / "ui", path))
    return _add_no_cache_headers(resp)


if __name__ == "__main__":
    port = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else 5111
    debug = False
    if "--debug" in sys.argv:
        debug = True
    if "--no-debug" in sys.argv:
        debug = False
    if os.environ.get("AGENT_BRIDGE_DEBUG") is not None:
        debug = os.environ.get("AGENT_BRIDGE_DEBUG", "").strip().lower() in ("1", "true", "yes", "on")
    print(f"Agent Bridge v0.3.0 on http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=debug)
