# M13 Section 6: Services and Utilities

## Goal

Build the application-level services that distance-server needs on top
of the protocol stack: ViewID allocation, object state tracking, typed
serialization helpers, and cross-port bridging.

## Modules

### `src/services/view-id-allocator.ts` — ViewID Allocation

Manages ViewID ranges for clients and server-owned objects.

```ts
class ViewIdAllocator {
  constructor(options?: { stride?: number });

  // Allocate a ViewID for a client-owned object
  allocateForClient(session: ClientSession): number;

  // Allocate a server-owned ViewID (scene scope)
  allocateScene(): number;

  // Release all ViewIDs for a disconnected client
  releaseClient(session: ClientSession): void;

  // Query
  getOwner(viewId: number): ClientSession | 'server' | undefined;
  getViewIdsForClient(session: ClientSession): number[];
}
```

Unity's ViewID scheme: scene ViewIDs are low numbers (0, 1, 2...),
allocated ViewIDs are in per-client ranges. The server assigns each
client a base ViewID = `playerIndex * stride`. Clients allocate from
their assigned range.

**Boundary with Section 3:** RakNetServer (S3) handles the wire-level
ViewID block announcement (0x81 message with base/end range). This
allocator handles application-level tracking — which objects exist,
who owns them, cleanup on disconnect.

### `src/services/object-state-tracker.ts` — Object State Tracking

Tracks per-view field values for delta sync.

```ts
interface FieldDef {
  name: string;
  type: 'int' | 'float' | 'Vector3' | 'Quaternion' | 'short' | 'bool';
  width?: number;  // bit width for delta, default from type
}

class ObjectStateTracker {
  constructor(viewId: number, fields: FieldDef[]);

  // Update field values, returns dirty flags
  update(values: Record<string, number | number[] | boolean>): boolean[];

  // Get current state
  getValues(): Record<string, number | number[] | boolean>;

  // Serialize for state sync
  toBitStream(): BitStream;  // full state
  toDeltaBitStream(): { data: Uint8Array; bitLength: number } | null;  // delta (null if clean)

  // Mark all fields as clean (after successful send)
  markClean(): void;

  // Reset (e.g., on new connection — next send is full state)
  reset(): void;
}
```

### `src/services/serialization.ts` — Typed Serialization Helpers

Utilities for converting between TypeScript objects and BitStream data,
going beyond what the raw BitStream provides.

```ts
// Serialize/deserialize typed objects from a BitStream
interface Serializer<T> {
  write(bs: BitStream, value: T): void;
  read(bs: BitStream): T;
}

// Built-in serializers
const Serializers = {
  int32: Serializer<number>,
  float32: Serializer<number>,
  string: Serializer<string>,      // Huffman-encoded
  bytes: Serializer<Uint8Array>,   // length-prefixed
  vector3: Serializer<[number, number, number]>,
  quaternion: Serializer<[number, number, number, number]>,
  viewId: Serializer<ViewId>,
  networkPlayer: Serializer<number>,
} as const;

// Compose serializers for custom message types
function createMessageSerializer<T>(schema: MessageSchema<T>): Serializer<T>;
```

This gives the application two modes:
1. **Typed:** Define a schema, get type-safe serialization
2. **Raw:** Use BitStream directly for full control

### `src/services/multi-port.ts` — Cross-Port Bridging

Utility for running multiple UnityServer instances on different ports
and bridging clients between them.

```ts
class ServerCluster {
  addServer(name: string, server: UnityServer): void;
  removeServer(name: string): void;

  // Get all connected clients across all servers
  getAllClients(): Map<string, { server: UnityServer; session: ClientSession }>;

  // Forward an RPC from one server's client to another server's client
  forward(from: { server: UnityServer; client: ClientSession },
          to: { server: UnityServer; client: ClientSession },
          rpc: RpcMessage): void;

  // Broadcast an RPC to all clients on all servers
  broadcastAll(method: string, params: RpcParam[],
               options?: { exclude?: ClientSession }): void;
}
```

This is a thin coordination layer — the application still decides what
gets forwarded. The cluster just provides the plumbing.

## Exit Criteria

- [ ] ViewIdAllocator: allocate, release, query by owner
- [ ] ObjectStateTracker: update, dirty flags, delta serialization, reset
- [ ] Serialization helpers: all built-in types, custom message schemas
- [ ] ServerCluster: multi-server bridging, cross-port forwarding
- [ ] Unit tests for all services
- [ ] Integration test: 2 servers, 1 client each, RPC forwarded across
- [ ] Tier 2 `edgeCases` presets pass
- [ ] `pnpm typecheck` and `pnpm lint` pass
- [ ] Public API is documented with JSDoc (the library entry point)
