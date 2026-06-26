# M8: Protocol Completeness

## Goal

Close all remaining gaps in the Unity legacy networking wire format spec and
reference implementation so that an implementer can build a compatible
server/client from the spec alone, without access to a running Unity instance.

## Context

The core protocol (RPC, state sync, handshake, groups, ViewID allocation) is
fully reversed and implemented. What remains are:

- **Derivation algorithms** — how Unity computes method hashes, class GUIDs,
  and method indices from C# source. Without these, implementers must capture
  each value from a live Unity instance.
- **Missing parameter/serialization types** — NetworkPlayer, NetworkViewID as
  RPC params; double/ulong/string/byte[]/enum in state sync.
- **Password authentication** — how `Network.incomingPassword` is transmitted.
- **Network.Instantiate** — wire format for dynamic object spawning.

## Security Constraint

`Network.InitializeSecurity()` must NEVER be called in experiments.

---

## Milestone 8a: Method Hash Derivation ✅ COMPLETE

### Result

The method "hash" is the Huffman encoding of the method name using RakNet's
StringCompressor with `englishCharacterFrequencies`. Algorithm:

1. Huffman-encode the full method name → N bits
2. Total bytes = ceil(N / 8)
3. Content = 00 (2 zero bits) + Huffman(method_name)
4. Pad or truncate to total_bytes × 8 bits
5. First 6 bytes = "class GUID", remaining = "method hash"

The Huffman tree uses specific tie-breaking: leaf nodes sorted by
(weight ascending, char index descending), combined nodes inserted before
the first node with weight >= combined weight.

All 10 known hashes reproduced exactly. Implementation in
`protocol/unity_protocol.py::compute_method_id()`. Spec updated in
`docs/research/unity-legacy-networking-wire-format.md` §3.3.2.

The `method_tag` (4-bit field) derivation remains unknown, but 0 is
confirmed as a safe default — Unity accepts it.

### Exit Criteria Met

- ✅ Algorithm documented in wire format spec
- ✅ Reproduces all 10 known hashes
- ✅ Python implementation (`compute_method_id`, `method_hash_hex`)
- ✅ method_tag: 0 confirmed safe, derivation unknown (non-critical)

---

## Milestone 8b: Class GUID Derivation ✅ COMPLETE (resolved by 8a)

### Result

The "class GUID" is NOT a separate class-derived identifier. It is simply the
first 6 bytes of the Huffman-encoded method name (with 2-bit prefix). All
methods sharing a common name prefix (e.g. all starting with `"RPC_"`) produce
the same GUID because the first 48 bits encode the same characters.

This was discovered during 8a: the entire method_id field is a single
Huffman-encoded string, and the GUID/hash split is just a byte boundary.

A second MonoBehaviour whose methods use a different prefix (e.g. `"Net_"`)
would produce a different GUID. The GUID is determined by the method name,
not the class name.

### Exit Criteria Met

- ✅ Algorithm documented (§3.3.2 of wire format spec)
- ✅ Verified: all 10 methods with `RPC_` prefix produce GUID `0c93b276d5b1`
- ✅ Python implementation: `compute_method_id()` returns both GUID and hash
- ✅ Wire format spec updated

### Remaining Verification

A second MonoBehaviour with different method name prefixes would confirm that
different prefixes produce different GUIDs. This can be done opportunistically
during milestone 8c (method index) experiments.

---

## Milestone 8c: Method Index Derivation ✅ COMPLETE

### Result

The method index formula is:

```
method_index = (method_RID - 1 - interface_method_count_before_RID) × 4
```

Where K=8 in `(RID - K) * 4` decomposes as `K = 1 + 7` where 7 is the
number of interface methods (IExperiment) in the assembly before the
Loader's RPC methods.

This is equivalent to: the 0-based position in the MethodDef table after
removing all interface methods, multiplied by 4.

Verified against all 7 observed subsequent-use indices. Python implementation
in `compute_method_index()` and `register_method_index_table()`.

### Exit Criteria Met

- ✅ Formula documented in wire format spec §3.2.1
- ✅ Verified against all 7 observed indices
- ✅ Python implementation with `compute_method_index()` and
  `register_method_index_table()` for arbitrary assemblies

### Remaining Verification

- Needs verification with a second MonoBehaviour class to confirm the
  interface-exclusion rule applies generally (not just for our test assembly)
- The 7-bit field limits indices to 0-127, which may truncate methods at
  high RIDs (e.g. RPC_Gamma at predicted index 0x80 = 128)

---

## Milestone 8d: Network.SetLevelPrefix ✅ COMPLETE

### Result

SetLevelPrefix does NOT modify the wire format. RPCs with different level
prefixes are wire-identical to baseline RPCs. SetLevelPrefix is purely a
receiver-side filtering mechanism — no prefix value appears on the wire.

### Exit Criteria Met

- ✅ Wire behavior documented in spec §11
- ✅ No wire representation → no protocol implementation needed
- ✅ Server implementation guidance documented (receiver-side filtering)

---

## Milestone 8e: NetworkPlayer and NetworkViewID as RPC Parameters ✅ PARTIAL

### Result

**NetworkViewID as RPC param**: Uses 16-bit encoding (not the 48-bit encoding
from message headers). Observed: SceneID:1 = 0x0004, AllocatedID:50 = 0x4C80.
The encoding is opaque — not a simple integer. Method hash and index confirmed:
hash = `310ba632fd579053a8ce`, index = 0x74.

**NetworkPlayer as RPC param**: The NetworkPlayer RPC was lost due to timing
(sent before connection was established). Deferred to future experiment.

### Exit Criteria

- ✅ NetworkViewID 16-bit wire encoding documented in spec §14
- ✅ Method hash/index for RPC_NetworkViewID confirmed
- ⬜ NetworkPlayer encoding not yet captured (timing issue)
- ⬜ Full encode/decode not implemented (encoding is opaque)

---

## Milestone 8f: Additional State Sync Types ✅ PARTIAL

### Result

Captured state sync with NetworkPlayer + NetworkViewID. The data payload
is 66 bits (hex: `000480000000c00100`). The encoding is partially decoded:
the first 16 bits match the NetworkViewID 16-bit encoding (0x0004 for
SceneID:1). Full decoding deferred pending resolution of the 16-bit
NetworkViewID encoding.

### Exit Criteria

- ✅ Capture obtained with NetworkPlayer + NetworkViewID
- ⬜ Full decoding pending (depends on 16-bit ViewID encoding)
- ⬜ double type not yet tested

---

## Milestone 8g: Network.Instantiate Wire Format ✅ PARTIAL

### Result

Network.Instantiate uses the internal RPC `__RPCNetworkInstantiate` (not a
dedicated msg_id). Key findings:

1. **Internal RPC**: Uses same 0x1b format with constant=0x0000 (vs 0x0002
   for user RPCs). GUID=`2ad8d5b1324e`, hash=`c9da62174c65fea2ddb15a3585`.

2. **Parameter layout** (421 bits):
   - Bits 0-148 (149): Pre-transform data (ViewID + prefab identifier)
   - Bits 149-244 (96): Position Vector3 as 3 × float32 BE ✓
   - Bits 245-372 (128): Rotation Quaternion as 4 × float32 BE (x,y,z,w) ✓
   - Bits 373-420 (48): Post-transform data (int32=1 + 16 bits)

3. **Prefab encoding**: Not Huffman text, not ASCII. The 133-bit prefab
   identifier uses an unknown encoding (possibly a hash or serialized path).

4. **ViewID allocation**: 0x83/0x81 handshake allocates ViewID ranges
   (base=50 for player 1, stride=50 per player).

### Exit Criteria Met

- ✅ Wire format documented in spec §12-13
- ✅ Internal RPC mechanism documented
- ✅ Position/rotation encoding verified
- ⬜ Prefab identifier encoding not fully decoded (needs more experiments)

---

## Milestone 8h: Password Authentication ✅ COMPLETE

### Result

Password is **plaintext ASCII bytes** appended to the connection request
(msg_id 0x04). This is a RakNet transport-level feature, not Unity framing.

- Baseline 0x04: 25 bytes (200 bits)
- Password "secret123": 34 bytes (272 bits) = 25 + 9 bytes
- Password bytes: `73 65 63 72 65 74 31 32 33` = ASCII "secret123"

### Exit Criteria Met

- ✅ Password format documented in spec §2.2 and §10
- ✅ Encoding is trivial (plaintext append) — implementation is straightforward
- ⬜ Wrong-password rejection not captured (would need separate experiment)

---

## Implementation Order

```
8a (Method Hash)          — static analysis first, experiments if needed
8b (Class GUID)           — requires new Unity class, rebuild
8c (Method Index)          — pairs with 8b (share the rebuilt project)
8d (SetLevelPrefix)        — independent experiment
8e (NP/NVID RPC params)   — uses existing Loader RPCs
8f (State Sync types)      — new experiment with extra types
8g (Network.Instantiate)   — independent experiment
8h (Password Auth)         — independent experiment
```

8a can start immediately with static analysis. 8b and 8c should be done
together since both benefit from adding a second MonoBehaviour class.
8d–8h are independent experiments that can be done in any order.

## Notes

- **Buffered RPCs**: `RPCMode.OthersBuffered` (5) and `RPCMode.AllBuffered` (6)
  use the same `0x1b` wire format as unbuffered RPCs — only the RPCMode field
  value differs. Buffering is purely server-side bookkeeping (store sent RPCs,
  replay to late joiners). No additional wire format work needed. Confirm
  during 8e experiments by sending a buffered RPC and verifying it's identical
  except for the mode nibble.

- **Disconnect wire format**: Clean disconnects use RakNet's
  `ID_DISCONNECTION_NOTIFICATION` (0x15) sent as RELIABLE_ORDERED. This is
  already implemented in `raknet_connection.py`. No additional Unity-layer
  disconnect message has been observed. Will confirm opportunistically during
  other experiments.

## Decisions

- **RakNet encryption**: Deferred to a future milestone. Not required for
  client connectivity.
- **SetLevelPrefix**: Included for spec completeness even though Distance
  doesn't use it. If the experiment shows it's purely local (like groups),
  the milestone is just documentation.
- **Network.Instantiate**: Included for spec completeness. If the wire format
  is complex, we document what we find and implement decode-only.
