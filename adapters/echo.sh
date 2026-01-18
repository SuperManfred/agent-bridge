#!/usr/bin/env bash
set -euo pipefail

# A simple adapter for smoke-testing the coordinator.
# Reads coordinator JSON payload on stdin and prints a trivial reply on stdout.

payload="$(cat)"
content="$(python3 -c 'import json,sys; d=json.loads(sys.argv[1]); print(d.get("trigger",{}).get("content",""))' "$payload")"
echo "echo-adapter reply: ${content}"
