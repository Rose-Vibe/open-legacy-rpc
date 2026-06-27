# M13 Section 3: RakNet Connection

## Goal

Implement the RakNet + Unity connection handshake state machine. After this
section, a TypeScript server can accept connections from Unity clients and
a TypeScript client can connect to Unity servers.

## Modules

### `src/raknet/connection.ts` — Connection State Machine

**States:**
```
DISCONNECTED → CONNECTING → CONNECTED → DISCONNECTING → DISCONNECTED
```

**Handshake sequence (server accepting client):**
1. Client → Server: `OPEN_CONNECTION_REQUEST` (0x05) with magic bytes
2. Server → Client: `OPEN_CONNECTION_REPLY` (0x06) with magic bytes
3. Client → Server: `CONNECTION_REQUEST` (0x09) with password
4. Server → Client: `CONNECTION_REQUEST_ACCEPTED` (0x10) with system addresses
5. Client → Server: `NEW_INCOMING_CONNECTION` (0x13)
6. Server → Client: Unity ViewID block (0x81) with player index + ViewID range

**Key class:**
```ts
class RakNetConnection {
  readonly state: ConnectionState;
  readonly address: AddressInfo;
  readonly playerIndex: number;
  readonly viewIdBase: number;

  // Used by RakNetServer/RakNetClient to drive the state machine
  handleMessage(messageId: number, payload: Uint8Array): OutgoingMessage[];
  getKeepalivePackets(): OutgoingMessage[];  // ping/pong
}
```

### `src/raknet/server.ts` — RakNet Server

Manages multiple connections:
- Listens on a UDP port
- Handles offline messages (open connection request/reply)
- Creates per-client `RakNetConnection` + `ReliabilityLayer`
- Dispatches connected messages to the Unity layer
- Player index allocation (1-based, reusable)
- ViewID stride allocation

```ts
class RakNetServer {
  constructor(options: { port: number; password?: string; viewIdStride?: number });
  start(): void;
  stop(): void;
  
  on(event: 'connect', handler: (connection: RakNetConnection) => void): void;
  on(event: 'disconnect', handler: (connection: RakNetConnection) => void): void;
  on(event: 'message', handler: (connection: RakNetConnection, msg: IncomingMessage) => void): void;
  
  sendTo(connection: RakNetConnection, payload: Uint8Array, reliability: Reliability): void;
}
```

### `src/raknet/client.ts` — RakNet Client

Single-connection client:
```ts
class RakNetClient {
  connect(host: string, port: number, options?: { password?: string; timeout?: number }): Promise<void>;
  disconnect(): void;
  
  readonly connected: boolean;
  readonly playerIndex: number;
  readonly viewIdBase: number;
  
  on(event: 'message', handler: (msg: IncomingMessage) => void): void;
  on(event: 'disconnect', handler: () => void): void;
  
  send(payload: Uint8Array, reliability: Reliability): void;
}
```

## Password Authentication

Unity's password is sent in the `CONNECTION_REQUEST` packet as a
length-prefixed string. The server validates it before sending
`CONNECTION_REQUEST_ACCEPTED`. On mismatch, the server sends
`CONNECTION_ATTEMPT_FAILED` and drops the connection.

## Unity ViewID Block (0x81)

After the RakNet handshake completes, the server sends a Unity-specific
message (0x81) containing:
- Player index (u16)
- ViewID allocation base (u32)
- ViewID allocation end (u32)

This is part of the connection handshake — the client isn't "fully connected"
until it receives this block.

## Conformance Test Mapping

| Test | What it validates |
|------|-------------------|
| Tier 2 `handshake` basic #1 | Full handshake completes |
| Tier 2 `handshake` basic #3 | Password authentication |
| Tier 2 `handshake` basic #4 | Wrong password rejected |
| Tier 2 `handshake` basic #5 | Player index = 1 |
| Tier 2 `handshake` basic #6 | Two clients, indices 1 and 2 |

## Exit Criteria

- [ ] Server accepts connections from the Python reference client
- [ ] Client connects to the Python reference server
- [ ] Password authentication works (correct, wrong, missing)
- [ ] Player index allocation (sequential, 1-based)
- [ ] ViewID block sent/received correctly
- [ ] Graceful disconnect with notification
- [ ] Ping/pong keepalive
- [ ] All Tier 2 `handshake` preset tests pass
- [ ] `pnpm typecheck` and `pnpm lint` pass
