# Operations

## Run locally

See `README.md` for current setup commands.

## Persistence layout (current)

- Thread logs: `conversations/threads/<thread_id>.jsonl`
  - Evidence: `server.py:120`
- Thread index: `conversations/index.json`
  - Evidence: `server.py:34`
- Daily log (legacy): `conversations/YYYY-MM-DD.jsonl`
  - Evidence: `server.py:65`
- Suggestions: `suggestions/<id>.json`
  - Evidence: `server.py:376`

## Backups

To back up all conversation history, copy the `conversations/` directory.

Open question:
- Desired retention policy (none vs pruning vs archiving) for local usage.

## Failure modes (current)

Open questions to document/decide:
- Concurrent writes to the same thread file (file-level locking vs “good enough for localhost”).
- Event ordering guarantees (timestamp vs file order).
