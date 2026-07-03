# Per-Session GUID Identity

## Why

`ClientSession.id` is currently `"{ip}:{port}"` (ts/src/raknet/
connection.ts:160). Consumers (the Distance brain) use it as the public
client identifier, which means surfacing it in any outward-facing
context (web UI, logs shared with players) leaks other players' IP
addresses. The id should be an opaque per-connection GUID.

Investigation findings (2026-07-03) this plan is built on:

- The id's *content* matters in exactly one place: `RakNetServer.sessions`
  is the **datagram routing table** — incoming packets look up their
  session by the address-derived key (connection.ts:160-167). Everywhere
  else in the library (unity/server.ts peer indices, view-id-allocator,
  network-groups, disconnect cleanup) the id is an opaque map key.
  Nothing parses it back into ip/port; all sends use `session.address`.
- The master-server module builds its own address keys from
  `session.address`, never from `.id`.
- The `ip:port` format has no wire significance — RakNet identifies
  peers by remote address (and offline-packet GUIDs); the string was a
  server-side convenience.
- **Trap**: `sessions.delete(session.id)` (connection.ts:253, 316) only
  works because id == address key today. A naive id swap makes those
  deletes silent no-ops → leaked sessions + ghost routing entries.
- The Python implementation keys everything by raw `addr` tuples and has
  no string session id — **this change is TS-only**; Python needs no
  parity work.

## What

In `ts/src/raknet/connection.ts`:

1. Separate the two roles of `sessions`:
   - `private sessionsByAddr: Map<string, ClientSession>` — internal
     datagram routing table, keyed `"{host}:{port}"` exactly as today.
     A private `addrKey(remote: AddressInfo)` helper is the only place
     that builds the key.
   - `private sessionsById: Map<string, ClientSession>` — public
     identity map, keyed by the new GUID.
   Both maps are mutated together in exactly three places: session
   creation, the password-reject delete (:253), and disconnect (:316).
   `stop()`'s `sessions.clear()` clears both.
2. Session creation sets `id: crypto.randomUUID()` (node:crypto —
   collision-safe, unlike the file's `Math.random`-based `randomGuid()`,
   which stays as-is for the RakNet offline-packet GUID).
3. Public surface speaks GUID: `getSession(id)` and `get clients` read
   `sessionsById`. Their signatures don't change.
4. Doc comment on `ClientSession.id`: "Opaque per-connection GUID —
   NOT derived from the client's address. Use `session.address` for
   the remote endpoint."

Reconnect semantics change deliberately: a client reconnecting from the
same ip:port gets a NEW id (it is a new session). Today the open-
connection handler skips creation if the addr key exists
(connection.ts:228 `if (!this.sessions.has(sessionId))`) — that skip
keeps working against `sessionsByAddr` and preserves current behavior
for retransmitted open-connection requests (same session object, id
unchanged). Only a full disconnect+reconnect mints a new id.

## Consumers

- The Distance brain treats the id as opaque (branded `SessionId`,
  verified by audit) — zero code changes. `playerIdOwner`'s
  `lastIndexOf(':')` parse of `{sessionId}:{counter}` works with GUIDs
  (which contain no colons; this also removes a latent IPv6 ambiguity).
- Brain log lines that print `client.session.id` will show GUIDs
  instead of addresses — cosmetic, and the point of the change.
  brain/scripts/connect.sh greps player names, not ids — unaffected.

## Tests

New TS unit test(s) in the library:

- Session id is a UUID (format check), not equal to `"{host}:{port}"`.
- `getSession(id)` and `clients` are keyed by that id.
- Datagram from a known remote still routes to its session (existing
  integration tests cover this implicitly; they must stay green).
- Disconnect removes the session from BOTH maps (no leak): after
  `disconnectClient`, `getSession(id)` is undefined and a fresh
  connection from the same address gets a different id.
- Password-reject path also cleans both maps.

## Exit criteria

- Library: `npm test` green (209 existing + new), `npm run build` clean.
- No remaining internal use of `session.id` as an address (grep:
  `sessions.delete(session.id)` gone; routing reads only `sessionsByAddr`).
- Brain: `npm test` green against the rebuilt library; E2E connect flow
  (start-dev-server.sh + connect.sh) passes with the real game client;
  server log shows a GUID in "Client ready".
- Python suite untouched and green (no Python changes).
