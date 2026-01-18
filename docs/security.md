# Security (v1 scope)

## Threat model (current target)

- Single-user on localhost.
- No public exposure.
- No strong identity model; `from` is a string provided by the client.

## Implications

- Any local process can spoof participant identities unless an auth mechanism is added.
- CORS is enabled, which is convenient for local UI but expands browser-origin access.
  - Evidence: `server.py:27`

## Future considerations (deferred)

- If exposed beyond localhost, add authentication and origin restrictions.
- Consider separating “read” and “write” capabilities per client/participant.

