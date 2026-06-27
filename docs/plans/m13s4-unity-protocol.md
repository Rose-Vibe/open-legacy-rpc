# M13 Section 4: Unity Protocol Layer

## Goal

Implement Unity's application-layer protocol on top of RakNet: RPC
encoding/decoding, state sync, ViewID encoding, and method hash
computation. After this section, the TypeScript implementation can
encode and decode every Unity protocol message.

## Modules

### `src/unity/rpc.ts` — RPC Codec

**Subsequent-use format** (normal RPCs after first exchange):
- Method index (compressed u32)
- ViewID (48-bit)
- RPC counter (compressed u32)
- RPCMode (3 bits)
- Parameters (type-specific encoding)

**First-use format** (first RPC of a new method):
- Same as subsequent-use but prefixed with method hash (MD5-derived)
  and class GUID

**Parameter types:**
- `int` — 32-bit signed BE
- `float` — IEEE 754 32-bit BE
- `string` — Huffman-encoded
- `byte[]` — length-prefixed
- `Vector3` — 3 × float
- `Quaternion` — 4 × float
- `NetworkViewID` — 16-bit packed
- `NetworkPlayer` — 16-bit

```ts
interface RpcMessage {
  methodName: string;
  methodIndex: number;
  viewId: ViewId;
  rpcCounter: number;
  mode: RpcMode;
  params: RpcParam[];
  raw: Uint8Array;  // original payload for passthrough
  bitLength: number;
}

function encodeRpc(msg: RpcEncodeOptions): { data: Uint8Array; bitLength: number };
function decodeRpc(data: Uint8Array, bitLength: number): RpcMessage;
function encodeRpcFirstUse(msg: RpcEncodeOptions): { data: Uint8Array; bitLength: number };
```

Port from: `protocol/unity_protocol.py` (RPC functions) + `protocol/unity_rpc_decode.py`

### `src/unity/method-hash.ts` — Method Hash

Unity's method identification uses an MD5-based hash:
- Class GUID: `MD5("MonoBehaviour")` (16 bytes)
- Method hash: `MD5(methodName)` (first 4 bytes)
- Method index: derived from RID and interface method count

```ts
function computeMethodHash(methodName: string): { classGuid: Uint8Array; methodHash: Uint8Array };
function computeMethodIndex(methodRid: number, interfaceMethodCount: number): number;
```

Port from: `protocol/unity_protocol.py` (method hash functions)

### `src/unity/state-sync.ts` — State Sync Codec

**Unreliable state sync** (UNRELIABLE_SEQUENCED):
- ViewID (48-bit)
- Timestamp (16-bit)
- Is-first flag
- Data payload (arbitrary BitStream)

**Reliable delta compressed** (RELIABLE_ORDERED):
- Same header
- Dirty flags (1 bit per field)
- Only changed field values included

```ts
function encodeStateSync(options: StateSyncOptions): { data: Uint8Array; bitLength: number };
function decodeStateSync(data: Uint8Array, bitLength: number): StateSyncMessage;
function encodeDeltaStateSync(options: DeltaSyncOptions): { data: Uint8Array; bitLength: number };
function decodeDeltaStateSync(data: Uint8Array, bitLength: number, context: DeltaContext): DeltaSyncMessage;
```

Port from: `protocol/unity_protocol.py` (state sync functions)

### `src/unity/view-id.ts` — ViewID Encoding

Two ViewID formats:
- **48-bit** (in RPC/state sync headers): scope (1 bit) + ID (variable)
- **16-bit packed** (in RPC NetworkViewID parameters): scope + ID packed into u16

```ts
interface ViewId {
  scope: 'scene' | 'allocated';
  id: number;
}

function encodeViewId(viewId: ViewId): Uint8Array;
function decodeViewId(data: Uint8Array): ViewId;
function encodeViewId16(viewId: ViewId): number;
function decodeViewId16(value: number): ViewId;
```

Port from: `protocol/unity_protocol.py` (ViewID functions)

## Conformance Test Mapping

| Category | Module |
|----------|--------|
| `rpcEncode` | `rpc.ts` — `encodeRpc` |
| `rpcDecode` | `rpc.ts` — `decodeRpc` |
| `rpcFirstUse` | `rpc.ts` — `encodeRpcFirstUse` |
| `rpcFirstUseDecode` | `rpc.ts` — `decodeRpc` (detects first-use) |
| `methodHash` | `method-hash.ts` |
| `methodIndex` | `method-hash.ts` |
| `stateSync` | `state-sync.ts` — `encodeStateSync` |
| `stateSyncDecode` | `state-sync.ts` — `decodeStateSync` |
| `deltaStateSync` | `state-sync.ts` — `encodeDeltaStateSync` |
| `deltaSyncDecode` | `state-sync.ts` — `decodeDeltaStateSync` |
| `viewId` | `view-id.ts` — `encodeViewId` |
| `viewIdParam` | `view-id.ts` — `encodeViewId16` |

All 12 categories must pass in both basic and random modes.

## Exit Criteria

- [ ] RPC encode/decode for all parameter types
- [ ] First-use and subsequent-use RPC formats
- [ ] Method hash computation matches Python reference
- [ ] State sync encode/decode (unreliable)
- [ ] Delta state sync encode/decode (reliable)
- [ ] ViewID 48-bit and 16-bit encoding
- [ ] All 12 conformance test categories pass
- [ ] `pnpm typecheck` and `pnpm lint` pass
