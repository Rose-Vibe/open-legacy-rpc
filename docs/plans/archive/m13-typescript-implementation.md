# M13: TypeScript Implementation of Unity Legacy Networking

## Goal

Build a production-quality TypeScript implementation of the Unity legacy
networking protocol (RakNet 3.731 + Unity framing). The end state is a
TypeScript server that Unity 2018.1.6f1 clients can connect to, and a
TypeScript client that can connect to Unity servers.

The primary consumer is the distance-server, which needs:
- Server-authoritative message routing (no automatic forwarding)
- Multi-client support across ports
- Typed RPC/state sync with raw access available
- ViewID allocation and object state tracking

## Architecture

```
┌─────────────────────────────────────┐
│  Application (distance-server)      │  TypeScript objects, game logic
├─────────────────────────────────────┤
│  UnityServer / UnityClient          │  Connection mgmt, event dispatch
│  ├─ RpcCodec                        │  Encode/decode RPCs (typed + raw)
│  ├─ StateSyncCodec                  │  State sync encode/decode + delta
│  ├─ ViewIdAllocator                 │  ViewID assignment service
│  └─ ObjectStateTracker              │  Per-view state tracking
├─────────────────────────────────────┤
│  RakNetPeer                         │  Reliability, ordering, fragmentation
│  └─ UDP Socket (node:dgram)         │
└─────────────────────────────────────┘
```

## Implementation Sections

Each section has its own plan file with detailed scope, exit criteria,
and conformance test mapping.

### Section 0: Project Setup
`docs/plans/m13s0-project-setup.md`

TypeScript project structure, tooling config (tsconfig, eslint, prettier),
test infrastructure, conformance test bridge. Mirrors home-finder's strict
TypeScript configuration.

### Section 1: BitStream and Encoding Primitives
`docs/plans/m13s1-bitstream.md`

BitStream class (bit-level read/write), Huffman codec, WriteCompressed,
address encoding. Foundation for everything above.

**Conformance tests:** bitstream, bitstreamRead, writeCompressed,
readCompressed, huffman, huffmanDecode, addressEncode, addressDecode

### Section 2: RakNet Transport
`docs/plans/m13s2-raknet-transport.md`

UDP socket wrapper, RakNet packet framing (message IDs, reliability header),
reliability layer (RELIABLE, UNRELIABLE, SEQUENCED, ORDERED), ACK/NAK,
split packet assembly/disassembly, retransmission.

**Conformance tests:** Tier 2 handshake (transport-level)

### Section 3: RakNet Connection
`docs/plans/m13s3-raknet-connection.md`

Connection state machine (DISCONNECTED → CONNECTING → CONNECTED),
open connection request/reply handshake, password authentication,
ping/pong keepalive, disconnect handling.

**Conformance tests:** Tier 2 handshake (all presets)

### Section 4: Unity Protocol Layer
`docs/plans/m13s4-unity-protocol.md`

RPC encoding/decoding (first-use + subsequent-use), method hash computation,
state sync (unreliable + reliable delta compressed), ViewID encoding (48-bit
and 16-bit packed), Unity message framing (0x1b msg_id).

**Conformance tests:** rpcEncode, rpcDecode, rpcFirstUse, rpcFirstUseDecode,
methodHash, methodIndex, stateSync, stateSyncDecode, deltaStateSync,
deltaSyncDecode, viewId, viewIdParam

### Section 5: Server and Client
`docs/plans/m13s5-server-client.md`

UnityServer (listen, accept connections, dispatch events, send to clients),
UnityClient (connect, send RPCs, receive state sync). Event-driven API
with typed events. Multi-client session management. No automatic forwarding.

**Conformance tests:** Tier 2 peer tests (rpc, stateSync, multiClient)

### Section 6: Services and Utilities
`docs/plans/m13s6-services.md`

ViewID allocator (per-client stride-based allocation), ObjectStateTracker
(field-level dirty tracking for delta sync), typed serialization helpers
(BitStream ↔ TypeScript objects), cross-port client bridging utilities.

**Conformance tests:** Tier 2 peer tests (edgeCases)

## Validation Strategy

Each section is validated by running the M12 conformance tests:
- **Tier 1 (serde):** `legacy-net-serde-test generate <cat> basic | ts-impl | legacy-net-serde-test validate`
- **Tier 2 (peer):** `legacy-net-peer-test run < scenario.json` with the TS server/client as the peer
- **Tier 3 (Unity):** `legacy-net-peer-test unity <scenario>` against real Unity binaries

## Excluded: Master Server

The master server protocol (registration, querying, host lists) is
explicitly out of scope. The user's primary need is the game server
protocol. This excludes 11 conformance test categories:

- Serde: cell, cellDecode, updateRow, updateRowDecode, queryRequest,
  queryRequestDecode, queryReply, queryReplyDecode, removeRow,
  removeRowDecode
- Peer: masterServer

No Unity protocol features depend on master server code — the exclusion
is clean. Master server support can be added later as a separate section.

## Implementation Order

Strictly sequential — each section depends on the one before it:
0 → 1 → 2 → 3 → 4 → 5 → 6

Section 0 establishes the project; sections 1–4 build the protocol stack
bottom-up; section 5 assembles the user-facing API; section 6 adds
distance-server-specific services.
