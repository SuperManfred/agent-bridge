# Agent Bridge

This is a communication tool. You USE it from your project. You do NOT work inside this directory unless explicitly told to improve the bridge itself.

## Are you here to improve the bridge or use it?

**If your working directory is NOT `~/GITHUB/.agent-bridge/`:** You're using the bridge as a tool. Read only the "Using the Bridge" section below.

**If your working directory IS `~/GITHUB/.agent-bridge/`:** You're here to improve the bridge itself. The user should have given you specific instructions.

---

## Using the Bridge

Server: `http://localhost:5111`

### Create a thread
```bash
curl -X POST http://localhost:5111/threads \
  -H "Content-Type: application/json" \
  -d '{"name":"My thread","from":"user"}'
```

### Send a thread event
```bash
curl -X POST http://localhost:5111/threads/{THREAD_ID}/events \
  -H "Content-Type: application/json" \
  -d '{"type":"message","from":"your-participant-id","to":"all","content":"Your message","meta":{}}'
```

### Read thread events
```bash
curl "http://localhost:5111/threads/{THREAD_ID}/events"
```

### From browser (JavaScript)
```javascript
fetch('http://localhost:5111/threads/{THREAD_ID}/events', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({type: 'message', from: 'browser-claude', to: 'all', content: 'Hello', meta: {}})
})
```

### Agent identifiers
Use consistently:
- `claude-code` - Claude Code CLI
- `browser-claude` - Claude Chrome extension
- `codex` - Codex CLI
- `user` - Human participant (by convention)

---

## If improving the bridge

Only if explicitly asked to work on the bridge itself:

### Submit improvement suggestion
```bash
curl -X POST http://localhost:5111/suggest \
  -H "Content-Type: application/json" \
  -d '{"from":"your-agent-id","title":"Short title","description":"What and why"}'
```

Suggestions go to `suggestions/` for human review.
