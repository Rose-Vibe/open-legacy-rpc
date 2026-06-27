# M13 Section 5: Server and Client

## Goal

Assemble the protocol stack into a user-facing `UnityServer` and
`UnityClient` API. The server is event-driven with no automatic
forwarding — the application decides what to relay.

## Modules

### `src/unity/server.ts` — UnityServer

```ts
interface ClientSession {
  readonly id: string;              // unique session ID
  readonly address: AddressInfo;    // { host, port }
  readonly playerIndex: number;
  readonly viewIdBase: number;
  readonly connected: boolean;
  readonly connectionTime: number;  // monotonic timestamp
}

class UnityServer extends EventEmitter {
  constructor(options: ServerOptions);

  start(): void;
  stop(): void;

  readonly clients: ReadonlyMap<string, ClientSession>;

  // Send to specific client(s)
  sendRpc(target: ClientSession, method: string, params: RpcParam[],
          options?: { viewId?: ViewId; mode?: RpcMode }): void;
  sendStateSync(target: ClientSession, viewId: number, data: BitStream,
                options?: { isFirst?: boolean }): void;
  sendDeltaStateSync(target: ClientSession, viewId: number,
                     tracker: ObjectStateTracker): void;
  sendRaw(target: ClientSession, payload: Uint8Array,
          reliability: Reliability): void;

  // Broadcast helpers (convenience — application controls the target list)
  broadcast(method: string, params: RpcParam[],
            options?: { exclude?: ClientSession; viewId?: ViewId }): void;

  // Events
  on(event: 'connect', handler: (client: ClientSession) => void): this;
  on(event: 'disconnect', handler: (client: ClientSession, reason: string) => void): this;
  on(event: 'rpc', handler: (client: ClientSession, rpc: RpcMessage) => void): this;
  on(event: 'stateSync', handler: (client: ClientSession, sync: StateSyncMessage) => void): this;
  on(event: 'rawMessage', handler: (client: ClientSession, msg: IncomingMessage) => void): this;
}

interface ServerOptions {
  port: number;
  password?: string;
  tickRate?: number;       // default 15
  viewIdStride?: number;   // default 50
  maxClients?: number;     // default 32
}
```

**Key design decisions:**
- No automatic RPC forwarding. When a client sends `RPCMode.Others`, the
  server fires an `rpc` event. The application decides which other clients
  (if any) receive it.
- `ClientSession` is a lightweight handle. The heavy state (reliability
  layer, RakNet connection) is internal.
- `sendRaw` allows passthrough of messages the application doesn't want
  to decode/re-encode (performance optimization for relay).

### `src/unity/client.ts` — UnityClient

```ts
class UnityClient extends EventEmitter {
  connect(host: string, port: number, options?: ConnectOptions): Promise<void>;
  disconnect(): void;

  readonly connected: boolean;
  readonly playerIndex: number;
  readonly viewIdBase: number;

  sendRpc(method: string, params: RpcParam[],
          options?: { viewId?: ViewId; mode?: RpcMode }): void;

  on(event: 'connect', handler: () => void): this;
  on(event: 'disconnect', handler: (reason: string) => void): this;
  on(event: 'rpc', handler: (rpc: RpcMessage) => void): this;
  on(event: 'stateSync', handler: (sync: StateSyncMessage) => void): this;
}

interface ConnectOptions {
  password?: string;
  timeout?: number;  // default 5000ms
}
```

### Internal Tick Loop

Both server and client run an internal tick loop (configurable rate,
default 15 Hz):
- Flush outgoing packets from reliability layer
- Check retransmission timers
- Send keepalive pings
- Process incoming messages

The tick loop is `setInterval`-based. For high-performance use, the
application can call `tick()` manually and disable the internal loop.

## Conformance Test Mapping

| Test Category | What it validates |
|---------------|-------------------|
| Tier 2 `rpc` preset #1–8 | All RPC parameter types |
| Tier 2 `rpc` preset #9 | Bidirectional (server→client and back) |
| Tier 2 `stateSync` preset #1–4 | State sync delivery |
| Tier 2 `multiClient` #1–4 | Multi-client sessions |

These tests run by starting a TS server, connecting the Python reference
client (or vice versa), and executing the step sequences.

## Exit Criteria

- [ ] UnityServer accepts connections from Python client
- [ ] UnityClient connects to Python server
- [ ] RPC send/receive works in both directions
- [ ] State sync delivery works
- [ ] Multi-client: 2+ clients connected simultaneously
- [ ] Graceful disconnect with event notification
- [ ] Internal tick loop with configurable rate
- [ ] All Tier 2 `rpc`, `stateSync`, and `multiClient` presets pass
- [ ] `pnpm typecheck` and `pnpm lint` pass
