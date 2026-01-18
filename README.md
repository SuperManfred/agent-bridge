# Agent Bridge

HTTP server for multi-agent communication. Agents use this as a tool - they don't work in this directory.

## Setup

```bash
cd ~/GITHUB/.agent-bridge
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python server.py
```

Server runs on `http://localhost:5111`

## Usage

See [AGENTS.md](./AGENTS.md)

## Always-on coordinator (no nudges)

The HTTP server is a log + UI. To remove “nudging” (manual relaying), run the coordinator:

1) Create a config:
- Copy `coordinator.config.example.json` → `coordinator.config.json`
- Edit adapter commands under `agents` to match your local harnesses

2) Run:

```bash
python coordinator.py
```

See `docs/coordinator.md` for behavior/spec.
