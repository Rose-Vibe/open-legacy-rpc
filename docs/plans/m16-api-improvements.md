# M16: API Improvements for Consumer Ergonomics

## Motivation

The TS library has complete protocol-level support (RPC encode/decode, state
sync, master server) but lacks consumer-facing niceties. The distance-server
— our primary consumer — needs typed RPC serde, network group filtering, and
a complete barrel export. This milestone adds those without over-engineering
for hypothetical consumers.

## Deliverables

### D1: Barrel Export for Master Server

**What:** Add `MasterServer`, `MasterClient`, `HostInfo`, `RegisterOptions`,
and `MasterServerOptions` to `ts/src/index.ts`.

`Table` is not exported — it's an implementation detail of `MasterServer`.

**Exit criteria:** Importing from the package root gives access to all master
server public types. Serialization internals and `Table` stay unexported.

### D2: Zod-Based Typed RPC Schema & Handlers

**What:** A `defineRpc()` helper that lets consumers declare an RPC's
parameter types using zod schemas paired with the existing `ParamType`
string literals, then use it for typed `onRpc()` handlers and typed
`sendRpc()` calls. The library handles conversion between zod-validated
JS values and Unity's wire-format `RpcParam[]`.

**Why zod:** Familiar API; gives both a TypeScript type and runtime
validation from a single definition. Beyond just matching ParamType, zod
lets consumers add receive-side constraints on untrusted client data
(`z.number().int().min(0).max(100)`, `z.string().max(32)`). Structured
validation errors are useful for logging malformed input.

**Design:**

```ts
import { z } from 'zod';
import { defineRpc } from 'unity-legacy-networking';

// Consumer defines the RPC shape.
// Each field has a ParamType (for wire encoding) and a zod schema
// (for validation + type inference).
// Field order determines wire parameter position.
const SetServerName = defineRpc('SetServerName', {
  serverName: { param: 'string', schema: z.string().max(64) },
});

const Damage = defineRpc('Damage', {
  targetViewId: { param: 'int', schema: z.number().int() },
  amount: { param: 'float', schema: z.number().nonnegative() },
});

const SendBitStream = defineRpc('SendBitStream', {
  data: { param: 'bytes', schema: z.instanceof(Uint8Array) },
});

// Server typed receive — handler gets (session, args)
// args is inferred as { serverName: string }
server.onTypedRpc(SetServerName, (session, args) => {
  console.log(args.serverName);
});

// Server typed send — type error if args don't match schema
server.sendTypedRpc(target, SetServerName, { serverName: 'My Server' });

// Client typed receive — handler gets (args) only, no session
client.onTypedRpc(Damage, (args) => {
  console.log(args.targetViewId, args.amount);
});

// Client typed send
client.sendTypedRpc(Damage, { targetViewId: 5, amount: 10.5 });
```

**Type mapping** (enforced by zod schemas, wire format uses ParamType):

| ParamType          | Expected zod base type               |
|--------------------|--------------------------------------|
| `'int'`            | `z.number()`                         |
| `'float'`          | `z.number()`                         |
| `'string'`         | `z.string()`                         |
| `'bytes'`          | `z.instanceof(Uint8Array)`           |
| `'Vector3'`        | `z.tuple([z.number(), ...])`         |
| `'Quaternion'`     | `z.tuple([z.number(), ...])`         |
| `'NetworkViewID'`  | `z.number()`                         |
| `'NetworkPlayer'`  | `z.number()`                         |

**Implementation details:**

- Uses the existing `ParamType` string union from `rpc.ts` — no new enum.
  Each field descriptor is `{ param: ParamType; schema: z.ZodType<T> }`.
- `defineRpc(name, fields)` returns an `RpcDefinition<T>` object containing:
  - `name: string` — the method name
  - `paramTypes: ParamType[]` — ordered array derived from field `param` values
  - `fieldNames: string[]` — ordered array of field keys
  - `zodSchema: z.ZodObject<...>` — combined zod schema for validation
- On construction, `defineRpc()` calls `registerMethodNames([name])` to
  register the method name for hash computation, and adds the `ParamType[]`
  signature to `METHOD_SIGNATURES` so `decodeRpc()` can decode incoming
  params for this RPC. This is critical — without it, incoming
  consumer-defined RPCs would arrive with empty params.
- **`rpcSentMethods` fix:** Consumer-defined RPCs added to
  `METHOD_SIGNATURES` must NOT end up in `rpcSentMethods` initial set,
  because they have no `METHOD_INDEX_MAP` entry and would crash
  `encodeRpcSubsequent()`. Fix: change `rpcSentMethods` initialization
  (in both `UnityServer.onConnect` and `UnityClient` constructor) to only
  include RPCs that have `METHOD_INDEX_MAP` entries. Export a function
  `getBuiltinMethodNames()` from `rpc.ts` that returns only the hardcoded
  loader RPCs. Consumer-defined RPCs always go through
  `encodeRpcFirstUse()` on first send to each client, which uses
  hash-based identification and works without `METHOD_INDEX_MAP`.
- `onTypedRpc()` is added to both `UnityServer` and `UnityClient`:
  - **Server:** handler signature is `(session: ClientSession, args: T) => void`
  - **Client:** handler signature is `(args: T) => void`
  - This matches the existing asymmetry in untyped `onRpc()`.
  - Internally registers an untyped `onRpc()` handler that maps the decoded
    `unknown[]` params to a named object, validates with zod, and calls
    the typed handler. Validation failures are caught and logged (don't
    crash the server).
- `sendTypedRpc()` is added to both `UnityServer` and `UnityClient`:
  - **Server:** `sendTypedRpc(target, def, args, options?)` 
  - **Client:** `sendTypedRpc(def, args, options?)`
  - Validates args with zod (throws on programmer error), then converts
    the named args object to an ordered `RpcParam[]` array.
- The untyped `onRpc()` / `sendRpc()` remain unchanged.

**New file:** `ts/src/services/rpc-schema.ts` — contains `defineRpc()`,
`RpcDefinition<T>`, type helpers.

**Dependencies:** Add `zod` to `ts/package.json` as a regular dependency.

**Exit criteria:**
- `defineRpc()` produces correct `RpcDefinition<T>` with inferred types
- `onTypedRpc()` on server receives `(session, typedArgs)`
- `onTypedRpc()` on client receives `(typedArgs)`
- `sendTypedRpc()` type-checks args and encodes correctly
- Round-trip test: define schema → send → receive → validate matches
- All 8 Unity param types are supported
- Zod validation errors on receive don't crash the server
- Consumer-defined RPCs are registered in `METHOD_SIGNATURES` so
  `decodeRpc()` can decode their params
- Existing untyped API still works unchanged

### D3: Network Group Filtering

**What:** A `NetworkGroups` utility class that tracks per-view group
membership and per-client group subscriptions, with helpers for
group-filtered broadcast.

**Why:** Unity's `NetworkGroup` system controls which clients receive RPCs
and state sync for views in a given group. Distance uses this for visibility
control. The server needs to filter outgoing messages by group membership.

**Design:**

```ts
import { NetworkGroups } from 'unity-legacy-networking';

const groups = new NetworkGroups();

// Assign a view to a group
groups.setViewGroup(viewId, 0);  // group 0 = default
groups.setViewGroup(carViewId, 1);  // group 1 = gameplay

// Subscribe a client to groups
groups.subscribe(session, 0);  // client sees group 0
groups.subscribe(session, 1);  // client sees group 1
groups.unsubscribe(session, 1);  // client no longer sees group 1

// Check visibility
groups.canReceive(session, viewId);  // true if client is subscribed
                                     // to the view's group

// Get all clients that should receive for a view
groups.getReceivers(viewId);  // ClientSession[] subscribed to that group

// Cleanup
groups.removeClient(session);  // unsubscribe from all groups
groups.removeView(viewId);     // remove view from its group
```

**Implementation details:**

- `viewGroups: Map<number, number>` — viewId → groupId
- `clientSubscriptions: Map<string, Set<number>>` — sessionId → set of groupIds
- `clientSessions: Map<string, ClientSession>` — sessionId → session (for getReceivers)
- `addClient(session)` subscribes the client to group 0 (Unity default).
  The consumer calls this from their `onConnect` handler.
- This is a data structure, not wired into `UnityServer` — the consumer
  composes it with their send logic. This keeps it flexible for different
  routing patterns.

**New file:** `ts/src/services/network-groups.ts`

**Exit criteria:**
- View-to-group assignment works
- Client subscribe/unsubscribe works
- `canReceive()` correctly checks group membership
- `getReceivers()` returns correct session list
- `removeClient()` cleans up all subscriptions
- `removeView()` cleans up group assignment
- Default group 0 subscription on client add

### D4: Player ID — Already Done (Documentation Only)

Player ID assignment is already built into `RakNetServer.handlePlayerReady()`
(line 251 of `ts/src/raknet/connection.ts`). Each connecting client gets
`session.playerIndex` set to an incrementing integer (server = 0, first
client = 1, etc.) and a view ID range (`viewIdBase` to `viewIdEnd`).

`UnityClient.playerIndex` and `UnityClient.viewIdBase` are already exposed.

No code changes needed. This deliverable is satisfied by the existing
implementation.

## Non-Goals

- **Structured state sync / auto-delta:** Distance uses RPC-based state
  transport (TransceiverBase pattern), not Unity's OnSerializeNetworkView
  for most state. The existing `sendStateSync()` / `sendDeltaStateSync()`
  are sufficient for the few objects that do use it.
- **Custom message dispatch beyond Unity's:** Distance uses only Unity's
  RPC name-based dispatch. No custom framing layer needed.
- **Server lifecycle orchestration:** The consumer composes `UnityServer`,
  `MasterClient`, etc. themselves. No `GameServer` wrapper.
- **Tick loop:** The consumer manages their own update loop. `RakNetServer`
  already has an internal tick for packet retransmission.
- **Destroy messages:** Not a Unity protocol concept. Application-level.

## Implementation Order

1. D1 (barrel export) — trivial, no dependencies
2. D2 (typed RPC schema) — install zod, implement `defineRpc()` + typed
   methods on server/client
3. D3 (network groups) — standalone utility, no dependencies on D2

D2 and D3 could be done in parallel but are ordered for cleaner commits.

## Test Plan

- D1: Build succeeds, import from package root works
- D2: Unit tests for `defineRpc()`, round-trip encode/decode with typed
  schemas, validation error handling, all 8 param types
- D3: Unit tests for group assignment, subscription, visibility checks,
  cleanup
