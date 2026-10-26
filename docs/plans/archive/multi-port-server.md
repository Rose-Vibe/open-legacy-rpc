# Multi-Port RakNet Server

## Goal

Allow the TS `RakNetServer` to listen on multiple UDP ports simultaneously,
with dynamic add/remove and per-port control. All ports feed into the same
server instance (shared session pool, player indices, events).

## Motivation

distance-server needs to expose the game server on multiple ports (e.g.
a primary game port + a spectator port with different permissions). Ports
should be addable/removable at runtime without restarting the server.

## Design

### API Surface

```typescript
// Construction — ports array (empty accepted)
const server = new RakNetServer({
  ports: [7777, 7778],       // initial ports to bind, or [] / omitted
  password: '...',
  viewIdStride: 50,
});

await server.start();        // binds all initial ports, starts tick loop

// Dynamic port management
await server.addPort(7779);
await server.removePort(7778, { mode: 'DisconnectClientsOnPort' });

// Per-port control (separate from removal)
server.setPortAccepting(7778, false);  // reject new connections on this port
server.setPortAccepting(7778, true);   // resume accepting

// Query
server.getSessionsByPort(7778): readonly ClientSession[]

// ClientSession exposes which port the client connected through
interface ClientSession {
  // ...existing...
  readonly localPort: number;
}
```

### `addPort` semantics

- Creates and binds a new `UdpSocket`, wires it into the server.
- **Throws if the port is already bound** (duplicate guard).
- New port starts in accepting=true state.

### `removePort` semantics

- The `mode` parameter is **required** — forces callers to acknowledge the
  disconnect behavior. Type is a string literal union with one member today:
  `'DisconnectClientsOnPort'`.
- Disconnects all sessions on that port **synchronously** (sends
  DISCONNECTION_NOTIFICATION, fires handlers, removes from maps).
- **Then** awaits `socket.close()` — this ordering ensures no in-flight
  `sendTo` calls race against the closed socket.
- Frees the OS port.
- Throws if the port isn't currently bound.

### `passwordPredicate` option

```typescript
passwordPredicate?: (session: ClientSession, password: string) => boolean;
```

- When provided, called during `ID_CONNECTION_REQUEST` processing with the
  session (which already has `localPort`, `address`, `perGameLaunchId`) and
  the password string the client sent.
- Return `true` to accept, `false` to reject (session removed).
- Takes priority over the static `password` string.
- Enables per-port passwords, token validation, rate limiting, etc.

### `setPortAccepting` semantics

- When a port is not accepting, incoming `ID_OPEN_CONNECTION_REQUEST` packets
  on that port are silently dropped — **no reply sent, no session created**.
  The check occurs before any session creation or reply logic.
- Already-connected sessions on that port continue normally.
- Default state after `addPort` is accepting=true.

### Internal changes to `connection.ts`

1. Replace `private socket: UdpSocket` with `private sockets: Map<number, UdpSocket>`.
2. Add `private portAccepting: Map<number, boolean>` for accept control.
3. Add `private sessionSockets: Map<string, UdpSocket>` keyed by session `addrKey`
   — tracks which socket to send replies through.
4. Add `localPort: number` to `ClientSession` interface (readonly).
5. `handleOpenConnectionRequest` receives the socket as a parameter, stores it
   in `sessionSockets`, and sets `localPort` on the new session.
6. `tick()` iterates sessions and sends via `sessionSockets.get(addrKey)`.
7. `disconnectClient()` and other send paths use the session's socket.
8. `start()` binds all ports from the `ports` option.
   `stop()` iterates all sockets in the map, disconnects sessions, closes each.
9. The `port: number` constructor option becomes `ports?: number[]` with
   backward compat: if `port` is passed (old API), treat as `ports: [port]`.
10. `CONNECTION_REQUEST_ACCEPTED` reply uses `session.localPort` instead of
    `this.port`.

### Socket lifecycle

- `UdpSocket` stays unchanged — one instance per port.
- `addPort(n)` creates a new `UdpSocket`, binds it, wires `onMessage` into
  `handlePacket` (passing the socket ref), adds to `sockets` map.
- `removePort(n, {mode})` disconnects sessions, removes from `sockets`,
  closes the socket.

### Backward compatibility

- Existing `new RakNetServer(socket, { port })` constructor is the internal
  detail used by tests. Migrate to the new shape: the server creates its own
  sockets. Old tests that pass a socket can use a compat overload or be updated.
- `UnityServer` (the higher-level class in `ts/src/unity/server.ts`) passes
  through `ports` and exposes `addPort`/`removePort`/`setPortAccepting`/
  `getSessionsByPort`.

## Exit Criteria

1. `RakNetServer` accepts `ports: number[]` in options.
2. `addPort(port)` binds a new listener dynamically.
3. `removePort(port, { mode: 'DisconnectClientsOnPort' })` disconnects clients
   and frees the port.
4. `setPortAccepting(port, bool)` controls new-connection acceptance per port.
5. `getSessionsByPort(port)` returns sessions connected through that port.
6. `ClientSession.localPort` is populated correctly.
7. All existing tests still pass (single-port behavior unchanged).
8. New tests cover: multi-port connect, port removal with disconnect, port
   accepting toggle, getSessionsByPort query.
9. TypeScript compiles cleanly with no type errors.
10. `passwordPredicate` receives session+password and controls auth decisions.
11. `passwordPredicate` takes priority over static `password` option.
