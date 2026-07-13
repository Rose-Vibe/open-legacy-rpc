# Unity Legacy Networking Wire Format

Reference specification for Unity 2018.1.6f1's legacy networking protocol,
built on RakNet 3.731 transport. Derived from controlled experiments with
differential pcap analysis.

**Security note:** This spec covers the unencrypted wire format.
`Network.InitializeSecurity()` was never called during capture — all
payloads are plaintext.

---

## 1. Transport: RakNet 3.731

### 1.1 UDP Datagram Structure

Every connected datagram starts with a 12-byte header:

| Offset | Size | Field | Encoding |
|--------|------|-------|----------|
| 0 | 1 | flags | `0x84` = data, `0xC0` = ACK, `0xA0` = NAK |
| 1–4 | 4 | B/AS statistics | uint32 BE (always 0 in practice) |
| 5–8 | 4 | sender timestamp | uint32 BE (ms since connect) |
| 9–11 | 3 | datagram sequence | uint24 LE (data datagrams only) |
| 12+ | var | encapsulated messages | byte-aligned within datagram |

For ACK/NAK datagrams, bytes 9+ contain range lists (no sequence number).

### 1.2 ACK/NAK Range List

| Offset | Size | Field |
|--------|------|-------|
| 0–1 | 2 | range count (uint16 BE) |
| per range: | | |
| +0 | 1 | max_equals_min (bool) |
| +1..+3 | 3 | min sequence (uint24 LE) |
| +4..+6 | 3 | max sequence (uint24 LE, only if !max_equals_min) |

### 1.3 Encapsulated Message Header

Messages are byte-aligned within the datagram's message area:

| Offset | Size | Field |
|--------|------|-------|
| 0 | 1 | `(reliability << 5) \| (has_split << 4)` |
| 1–2 | 2 | bit_length (uint16 BE) — total payload bits |
| if reliable (rel ≥ 2): | 3 | reliable_msg_number (uint24 LE) |
| if ordered/sequenced (rel ∈ {1,3,4}): | 3 | ordering_index (uint24 LE) |
| | 1 | ordering_channel (uint8) |
| if has_split: | 4 | split_packet_count (uint32 BE) |
| | 2 | split_packet_id (uint16 BE) |
| | 4 | split_packet_index (uint32 BE) |
| payload | ⌈bit_length/8⌉ | message data |

**Reliability levels:**

| Value | Name | Fields present |
|-------|------|----------------|
| 0 | UNRELIABLE | (none) |
| 1 | UNRELIABLE_SEQUENCED | ordering_index, ordering_channel |
| 2 | RELIABLE | reliable_msg_number |
| 3 | RELIABLE_ORDERED | reliable_msg_number, ordering_index, ordering_channel |
| 4 | RELIABLE_SEQUENCED | reliable_msg_number, ordering_index, ordering_channel |

**Important:** Unity's RakNet 3.731 does NOT write a separate
`sequencing_index` field for sequenced reliabilities. Only
`ordering_index` + `ordering_channel` are present.

### 1.4 Split Packet Reassembly

Messages exceeding the MTU (~1200 bytes) are split. Fragments share the
same `split_packet_id` and have sequential `split_packet_index` values
from 0 to `split_packet_count - 1`. Reassemble by concatenating payloads
in index order once all fragments arrive.

### 1.5 IP Address Encoding

RakNet stores IPv4 addresses bitwise-inverted (XOR with 0xFFFFFFFF):
- `80 ff ff fe` = ~`7f 00 00 01` = 127.0.0.1
- `f5 37 fe fd` = ~`0a c8 01 02` = 10.200.1.2

Ports are stored as uint16 BE (e.g., `1e 61` = 7777).

---

## 2. Connection Handshake

### 2.1 Offline Phase

These are UDP packets with no connected datagram header:

1. **C→S:** `0x09` ID_OPEN_CONNECTION_REQUEST (padded to MTU_SIZE = 1464 bytes)
   ```
   Byte 0:     0x09 (msg_id)
   Byte 1:     0x0b (RakNet protocol version)
   Bytes 2-9:  client GUID (uint64 BE, random)
   Bytes 10-25: offline magic
   Bytes 26-31: server address (bitwise-inverted IP + port)
   Bytes 32+:  zero padding to MTU_SIZE
   ```
2. **S→C:** `0x0a` ID_OPEN_CONNECTION_REPLY (padded to MTU_SIZE = 1464 bytes)
   ```
   Byte 0:     0x0a (msg_id)
   Bytes 1-16: offline magic
   Bytes 17-20: cookie echo (first 4 bytes of client GUID)
   Bytes 21-24: server nonce (4 random bytes)
   Bytes 25-30: client address (bitwise-inverted IP + port)
   Bytes 31+:  zero padding to MTU_SIZE
   ```

The offline message magic is: `00 FF FF 00 FE FE FE FE FD FD FD FD 12 34 56 78`

### 2.2 Connected Phase (Standard RakNet)

After the offline handshake, connected datagrams begin:

3. **C→S:** `0x04` ID_CONNECTION_REQUEST (RELIABLE, 25+ bytes)
   ```
   Byte 0:     0x04 (msg_id)
   Bytes 1-16: offline magic
   Bytes 17-24: client GUID (uint64 BE)
   Bytes 25+:  password (raw ASCII bytes, if set)
   ```
   When `Network.incomingPassword` is set on the server, the client
   appends the password as plaintext ASCII bytes after the GUID. A
   baseline (no-password) request is 25 bytes (200 bits). A request
   with password "secret123" (9 bytes) is 34 bytes (272 bits). See §10.
4. **S→C:** `0x0e` ID_CONNECTION_REQUEST_ACCEPTED (RELIABLE_ORDERED, 69 bytes)
   - Layout: msg_id + remote_addr(4) + remote_port(2) + padding(2) + 
     local_addr(4) + local_port(2) + external_addr(4) + external_port(2) +
     8× empty_addr(4+2)
   - Addresses are bitwise-inverted
5. **C→S:** `0x11` ID_NEW_INCOMING_CONNECTION (RELIABLE_ORDERED, 67 bytes)
   - Layout: msg_id + server_addr(6) + client_addr(6) + external_addr(6) +
     8× empty_addr(6)
   - Note: server address comes FIRST, then client address

### 2.3 Unity Layer

After the RakNet handshake completes:

6. **C→S:** `0x83` Unity player ready (RELIABLE_ORDERED, 5 bytes)
   ```
   Byte 0:    0x83 (msg_id)
   Bytes 1-4: player_index (uint32 BE) — always 1 for first client
   ```

7. **S→C:** `0x81` Unity player assignment (RELIABLE_ORDERED, 29 bytes)
   ```
   Byte 0:    0x81 (msg_id)
   Bytes 1-4:   constant_1 (uint32 BE) = 1 (scene/level marker)
   Bytes 5-8:   constant_0 (uint32 BE) = 0
   Bytes 9-12:  player_index (uint32 BE) = 1-based, increments per client
   Bytes 13-16: viewid_stride (uint32 BE) = 50 (ViewIDs per block)
   Bytes 17-20: constant_2 (uint32 BE) = 2
   Bytes 21-24: block_start (uint32 BE) = player_index × 2 - 1
   Bytes 25-28: block_end (uint32 BE) = player_index × 2
   ```
   See §7.1 for the full field breakdown and multi-client observations.

### 2.4 Keepalive (Ongoing)

- **0x00** Internal ping (UNRELIABLE or RELIABLE, 9 bytes):
  payload is the ping timestamp
- **0x03** Connected pong (UNRELIABLE, 17 bytes):
  payload includes ping and pong timestamps

---

## 3. RPC Wire Format

RPCs use msg_id `0x1b` with RELIABLE_ORDERED reliability.

### 3.1 Common Header (bits 0–80)

| Bit Offset | Width | Field |
|------------|-------|-------|
| 0–7 | 8 | msg_id = `0x1b` (ID_TIMESTAMP) |
| 8–71 | 64 | u64 BE `senderRakNetGetTimeMS()` — server uptime in ms. RakNet's `ShiftIncomingTimestamp` reads this to produce `NetworkMessageInfo.timestamp` on the receiver. |
| 72–79 | 8 | constant `0x0b` (RPC sub-type marker; distinguishes RPCs from state sync which uses `0x80`/`0x7f`) |
| 80 | 1 | first_use flag (1 = includes method hash, 0 = cached index) |

### 3.2 Subsequent-Use Format (first_use = 0)

Used for the second and later invocations of a given RPC method. The
receiver has already cached the method from the first-use message.

**method_index < 128** (the common case — low/mid dispatch-table slots):

| Bit Offset | Width | Field |
|------------|-------|-------|
| 80 | 1 | first_use = 0 |
| 81–87 | 7 | method_index (low 7 bits) |
| 88–103 | 16 | reserved, always zero |
| 104–119 | 16 | remaining_bit_count = total_bit_length - 121 (uint16 BE; +5 if relayed) |
| 120–135 | 16 | user_rpc_constant (see §3.6) |
| 136–139 | 4 | RPCMode |
| 140 | 0 or 1 | target bit (present only when RPCMode = Player) |
| 140/141+ | var | parameters |
| after params | 0 or 5 | relay padding (see §3.7) |

**method_index ≥ 128** (dispatch-table slot needs bit 7): the header is 4
bits *wider*, not just repacked — every field from `remaining_bit_count`
onward shifts out by 4 bits, and `remaining_bit_count`'s formula changes
accordingly:

| Bit Offset | Width | Field |
|------------|-------|-------|
| 80 | 1 | first_use = 0 |
| 81–87 | 7 | method_index (low 7 bits) |
| 88 | 1 | zero |
| 89 | 1 | extension flag = 1 (method_index has bit 7 set, i.e. index ≥ 128) |
| 90–107 | 18 | reserved, always zero |
| 108–123 | 16 | remaining_bit_count = total_bit_length - 125 (uint16 BE; +5 if relayed) |
| 124–139 | 16 | user_rpc_constant (see §3.6) |
| 140–143 | 4 | RPCMode |
| 144 | 0 or 1 | target bit (present only when RPCMode = Player) |
| 144/145+ | var | parameters |
| after params | 0 or 5 | relay padding (see §3.7) |

This was discovered via a static-index-table sweep against a real Unity
client (`scripts/index-sweep-server.py`): forcing a subsequent-use send at
a computed index ≥ 128 using the fixed-width (non-extended) layout above
produced `Internal RPC error. Not enough data to read.` on the real
client, while a genuine real-Unity-to-real-Unity capture
(`captures/MethodIndexU2U-20260627-145136-*`) showed the real client
cleanly dispatching `RPC_Alpha` at wire index 132 using this wider
layout. Field-by-field comparison of that capture (`target_view` reads
the expected routing constant, `RPCMode` reads 0=Server matching the C#
source's explicit call, and the final parameter decodes to exactly the
sent value) confirmed the +4-bit-wide layout, and re-running the sweep
with it applied resolved all four previously-failing methods
(`NetworkViewID`=128, `Alpha`=132, `Beta`=136, `Gamma`=140) with zero
`Not enough data to read` errors remaining. The exact encoding of the
extra 4 bits beyond "bit 89 set" is unconfirmed above index 132 (no real
capture above that value exists) — see Known Issue in `spec-status.md`.
This ceiling is very unlikely to matter for real Distance traffic, which
has only 7 total `[RPC]`-attributed methods across the whole shipped
game, far under 128.

### 3.2.1 Method Index and First-Use/Subsequent-Use Protocol

When a peer calls an RPC method for the first time on a given connection,
it sends a **first-use** message (§3.3) containing the method's Huffman
hash. All further calls to the same method on that connection use
**subsequent-use** messages containing only a 7-bit `method_index`.

Both sides must agree on which index maps to which method. The mapping
is established via the **RPC Batch Index** protocol (msg_id `0x07`,
see §3.8) — a separate UNRELIABLE message sent by the receiver after
processing a first-use RPC.

The complete exchange for each method on a given connection:

1. Sender sends first-use for method M to Receiver (Huffman hash → name).
2. Receiver resolves the hash, looks up its own `method_index` for M.
3. Receiver sends an RPC Batch Index message (§3.8) back to Sender,
   containing: method_id + Receiver's own `method_index` I.
4. Sender receives the batch index, stores: "when encoding subsequent-use
   for method M to this peer, use index I."
5. Sender now sends subsequent-use with index I for all further calls.
6. Receiver decodes index I → method M using its own local mapping.

Each peer registers its **own** index with the other side — the sender
uses the **receiver's** registered index, not its own. This allows two
builds with different assemblies (and therefore different method indices)
to communicate correctly without pre-shared configuration.

Unity waits for the batch index response before switching from first-use
to subsequent-use. If the receiver never sends a batch index (e.g., a
non-Unity implementation), the sender continues using first-use.

A non-Unity implementation that always sends first-use (never
subsequent-use) is fully compatible — it just costs ~20 extra bytes per
RPC for the Huffman hash. No batch index exchange is required in this
case.

**Erratum (2026-07-13):** the "sender uses the receiver's registered
index" claim above is confirmed only for real-Unity-to-real-Unity traffic
(§3.2.1's cross-binary evidence, both sides genuinely running Unity's own
dispatch logic). When a **non-Unity implementation** is the sender — this
repo's Python server, sending first-use to a real Unity client — the real
client's own `0x07` reply does not match its own real dispatch slot for
any of 13 methods tested. Using the reported value for subsequent-use
encoding reliably produces either a silent non-dispatch or a misdispatch
to an unrelated method, depending on whether the sent parameter bytes
happen to fit that unrelated method's shape. The reliable approach for a
non-Unity sender is to compute the static per-method index directly (see
`docs/research/2026-07-13-subsequent-use-static-index-dispatch.md` and
§3.2.2 below) and use that instead of the peer-reported `0x07` value.
`protocol/unity_server.py`'s current reliance on the reported value
(`_peer_indices`) is a known production-code gap, tracked separately —
see `spec-status.md` Known Issue #5.

### 3.2.2 Method Index Derivation (Unity internals)

Unity computes the `method_index` deterministically from the .NET
assembly's MethodDef table. The exact formula has been partially
reverse-engineered but not fully pinned down.

**What is confirmed:**

- `method_index = position × 4` (stride of 4, values always `0x00`,
  `0x04`, `0x08`, ..., `0x7c`)
- The position is per-NetworkView: each NetworkView component has its
  own method table with its own positions
- Interface methods are excluded from the counting
- Non-MonoBehaviour types (delegates, plain classes) are excluded
- Private methods without `[RPC]` are NOT counted
- Adding `[RPC]` to a method inserts it into the counting and shifts
  all later methods up by one position
- There is a base offset of approximately 20, likely derived from
  MonoBehaviour's declared method count

**Approximate formula:**

```
position = base_offset + count([RPC] methods with lower MethodDef RID)
```

Where `base_offset ≈ 20` with a per-NetworkView adjustment that depends
on the component's class hierarchy. Observed base offsets:

| Component hierarchy | Base offset |
|---|---|
| SecondRpcBehaviour → MonoBehaviour | 20 |
| Loader → MonoBehaviour | 21 |
| InheritedRpcDerived → InheritedRpcBase → MonoBehaviour | 22 |

The adjustment correlates with the number of user MonoBehaviour subclass
constructors in the assembly but the exact rule is unconfirmed.

**Simple formula (single-class assemblies):**

For assemblies with one MonoBehaviour subclass and no other MB types,
the formula simplifies to:

```
method_index = (method_RID - 1 - interface_method_count) × 4
```

This was verified against a single-class test assembly:

| Method | RID | Interface methods before | Index |
|--------|-----|------------------------|-------|
| RPC_Int | 29 | 7 | `0x54` = (29-1-7)×4 |
| RPC_Float | 30 | 7 | `0x58` = (30-1-7)×4 |
| RPC_String | 31 | 7 | `0x5c` = (31-1-7)×4 |
| RPC_Quaternion | 33 | 7 | `0x64` = (33-1-7)×4 |
| RPC_Bytes | 34 | 7 | `0x68` = (34-1-7)×4 |
| RPC_IntFloatString | 35 | 7 | `0x6c` = (35-1-7)×4 |

This formula breaks when the assembly contains multiple MonoBehaviour
subclasses — each additional class shifts the indices of later methods.

**Multi-class assembly observations:**

With IRB (2 methods), IRD (2 methods), Loader (28 methods), and
SRB (2 methods) in one assembly:

| Method | NV | Wire idx | Position | Simple formula | Delta |
|---|---|---|---|---|---|
| RPC_Void | Primary | 0x5c | 23 | 25 | -2 |
| RPC_Int | Primary | 0x60 | 24 | 26 | -2 |
| ReceiveSerializeEvent | SecondRpc | 0x50 | 20 | — | — |
| BaseRpc | InheritedRpc | 0x58 | 22 | — | — |

The delta of -2 matches the 2 extra MonoBehaviour subclass constructors
(IRB.ctor, IRD.ctor) present in the multi-class assembly.

**Cecil patching proof:**

Adding `[RPC]` to 4 non-RPC Loader methods (Awake, Start, Update,
OnSerializeNetworkView) via Mono.Cecil assembly patching shifted
RPC_Void's position from 23 → 27 (up by exactly 4). The newly-tagged
Awake method appeared at position 23 (the old RPC_Void position).
This confirms the counting is [RPC]-aware, not RID-sequential.

**Unsolved anomaly:**

DerivedRpc on the InheritedRpc NV produces `idx=0x04` with
`reserved=0xc000`. No formula produces position 1 for this method.
The non-zero reserved field (normally always zero) may indicate
bit overflow or a special encoding for inherited [RPC] methods.

**Recommendation for implementers:**

Do not attempt to pre-compute method indices from assembly metadata.
Instead, use the first-use/subsequent-use learning protocol described
in §3.2.1. An implementation that always sends first-use is fully
compatible and avoids the formula entirely.

### 3.3 First-Use Format (first_use = 1)

Used for the first invocation of an RPC method. Includes the method
name hash so the receiver can register it.

| Bit Offset | Width | Field |
|------------|-------|-------|
| 80 | 1 | first_use = 1 |
| 81–87 | 7 | method ref bits |
| 88–103 | 16 | (varies) |
| 104 (= 13×8) | 8 | length_indicator: `method_id_bits / 4` |
| 112–159 | 48 | class GUID = `0c 93 b2 76 d5 b1` |
| 160+ | var | method hash (method_id_bits - 48 bits) |
| after hash +0 | 4 | method_tag (not derivable — must be captured empirically, see §3.3.1) |
| +4 | 16 | reserved (must be zero) |
| +20 | 16 | remaining_bit_count = param_bits + 19 + target_bits |
| +36 | 16 | user_rpc_constant (see §3.6) |
| +52 | 4 | RPCMode |
| +56 | 0 or 1 | target bit (present only when RPCMode = Player) |
| +56/57 | var | parameters |
| after params | 0 or 5 | relay padding (see §3.7) |

The `length_indicator` at bit 104 encodes the total size of the method
identifier in nibbles. The method identifier consists of a 48-bit class
GUID followed by a variable-length method hash.

First-use parameter start bit = `160 + (method_id_bits - 48) + 52 + 4 [+ 1 if Player]`
where the +4 accounts for the RPCMode field; params start after RPCMode
(and after the target bit for Player-mode RPCs).

### 3.3.1 First-Use Internal Metadata (52 bits)

The 52-bit metadata block after the method hash parallels the subsequent-use
format's suffix (both share the reserved + remaining_count + constant pattern):

| Offset | Width | Field | Description |
|--------|-------|-------|-------------|
| 0 | 4 | method_tag | Always one of 0x0, 0x4, 0x8, 0xC. **Not derivable** from `method_index`, method name, signature, or RID — no closed-form formula fits the known ground truth (see `docs/research/2026-07-12-method-tag-real-derivation.md`, which disproves the previously-assumed `method_index & 0x0F` formula for 12 of 13 tested methods). Must be captured empirically per compiled assembly from a real Unity-to-Unity pcap. |
| 4 | 16 | reserved | Must be zero; Unity rejects RPCs with non-zero values |
| 20 | 16 | remaining_bit_count | `param_bits + 19 + target_bits + relay_bits` (where target_bits = 1 for RPCMode.Player, 0 otherwise; relay_bits = 5 if relayed, 0 otherwise). Same formula as subsequent-use. |
| 36 | 16 | user_rpc_constant | Same value as subsequent-use (see §3.6) |

The `remaining_bit_count` tells the receiver how many bits follow after
a fixed reference point (19 bits before params = RPCMode(4) + constant(16) - 1).
This is the same value as `total_bits - 121` in subsequent-use encoding.
When the message is a relay (§3.7), add 5 to account for the relay padding.

Unity's *decoder* accepts `method_tag = 0` when receiving first-use RPCs —
it will not reject the packet. That is not the same as being safe to
ignore: distance-server's dispatch-matrix testing found that when two RPC
methods share a tag, a real Unity client can silently misdispatch a
first-use RPC to the wrong method's handler (the exact caching mechanism
behind this is not confirmed, but the effect is reproducible), and a
controlled test against a real Unity 2018.1.6f1 client confirmed a wrong
tag can also cause outright rejection (`Internal RPC error. Invalid RPC
index, function not registered.`) rather than just misdispatch. `method_tag`
must be captured empirically from a real Unity-to-Unity pcap for each
compiled assembly whose RPCs will be sent first-use to a real Unity
client — it is **not** derivable from `method_index` or any other static
property. See `docs/research/2026-07-12-method-tag-real-derivation.md` for
the ground-truth data, `docs/plans/method-tag-collision-guard.md` (erratum)
and `docs/plans/method-tag-real-derivation-fix.md` for the corrective plan,
and spec-status.md Known Issue #1.

### 3.3.2 Method Identifier Derivation (GUID + Hash)

The method identifier is **not** a cryptographic hash. It is the Huffman
encoding of the method name using RakNet's StringCompressor:

1. Huffman-encode the full method name (e.g. `"RPC_Int"`) using RakNet's
   `englishCharacterFrequencies` table → N bits
2. Total byte count = `ceil(N / 8)`
3. Content = `00` (2 zero-padding bits) + Huffman bits
4. If content exceeds `total_bytes × 8` bits, truncate the trailing bits.
   If shorter, pad with EncodeArray-style partial Huffman code bits.
5. First 6 bytes of the result = "class GUID"
6. Remaining bytes = "method hash"
7. `length_indicator` = `total_bytes × 2`

The "class GUID" is not class-specific — it is simply the first 48 bits of
the Huffman-encoded method name (with 2-bit prefix). Methods sharing a
common prefix (e.g. all starting with `"RPC_"`) produce the same GUID.

**Huffman tree construction** must match RakNet's exact algorithm:
- All 256 byte values are leaf nodes with `weight = max(frequency, 1)`
- Initial sort: ascending weight, descending byte value for ties
- Combined nodes are inserted **before** the first node with weight ≥
  the combined weight (stable insertion into a sorted list)

This produces different codes from a standard min-heap for characters
with equal frequencies (e.g. `V`/`6` at freq=14, `Q`/`3` at freq=7).

Example derivations:

| Method | Huffman bits | Total bytes | GUID (hex) | Hash (hex) |
|--------|-------------|-------------|------------|------------|
| RPC_Int | 61 | 8 | 0c93b276d5b1 | d456 |
| RPC_Float | 72 | 9 | 0c93b276d5b1 | 564a1a |
| RPC_String | 79 | 10 | 0c93b276d5b1 | ab2f2853 |
| RPC_Vector3 | 93 | 12 | 0c93b276d5b1 | 55e145c655e0 |
| RPC_Quaternion | 96 | 12 | 0c93b276d5b1 | 55dadac64920 |
| RPC_Bytes | 73 | 10 | 0c93b276d5b1 | a857636a |
| RPC_IntFloatString | 120 | 15 | 0c93b276d5b1 | d456ac9435d5979429 |
| RPC_Alpha | 74 | 10 | 0c93b276d5b1 | 54929865 |
| RPC_Beta | 66 | 9 | 0c93b276d5b1 | a80b65 |
| RPC_Gamma | 76 | 10 | 0c93b276d5b1 | 569b4d19 |

All 10 values are reproduced exactly by the algorithm. An implementer
can compute the GUID and hash for **any** method name without capturing
from a live Unity instance.

### 3.4 RPCMode Values

| Value | Name | Meaning |
|-------|------|---------|
| 0 | Server | Send to server only |
| 1 | Others | Send to all except sender |
| 2 | All | Send to all including sender |
| 3 | Player | Send to specific player (has 1-bit target field after mode) |
| 5 | OthersBuffered | Others + buffer for late joiners |
| 6 | AllBuffered | All + buffer for late joiners |

When RPCMode = Player (3), a 1-bit target field follows the mode nibble
before the parameters begin. Observed value is always 0 (target is
implicit from the transport address). This extra bit shifts the parameter
start by 1 for Player-mode RPCs.

### 3.5 Parameter Encoding

Parameters are written sequentially with no separators or alignment
padding between them.

| Type | Encoding | Size (bits) |
|------|----------|-------------|
| int | signed 32-bit big-endian | 32 |
| float | IEEE 754 32-bit big-endian | 32 |
| Vector3 | 3× float32 BE (x, y, z) | 96 |
| Quaternion | 4× float32 BE (x, y, z, w) | 128 |
| string | WriteCompressed\<uint32\>(bitLength) + Huffman data | variable |
| byte[] | uint32 BE (byte count) + raw bytes | 32 + N×8 |
| NetworkPlayer | int32 BE (player index) | 32 |
| NetworkViewID | 16-bit packed (see §14) | 16 |

### 3.6 RPC View Constant

The 16-bit field previously called "constant" is a **packed NetworkViewID**
that identifies which NetworkView the RPC is sent through. It uses a
different encoding than the 16-bit ViewID-as-parameter format (§14).

#### 3.6.1 Encoding

| View Type | Formula | Bit 13 |
|-----------|---------|--------|
| Internal RPC | `0x0000` | 0 |
| Scene-baked | `sceneViewIndex << 1` | 0 |
| Allocated | `0x2000 \| (allocatedID << 5)` | 1 |

Bit layout:
```
Scene:     [0 0 0 sceneViewIndex(12..1) 0]
Allocated: [0 0 1 allocatedID(10..5) 0 0 0 0 0]
```

Bit 13 is the scene/allocated discriminator: `0` = scene-baked,
`1` = allocated. This parallels (but differs from) bit 14 in the
16-bit ViewID-as-parameter encoding (§14).

**Scene-baked views:** `sceneViewIndex` is the 1-based index of the
NetworkView in the scene hierarchy. The first view produces `0x0002`,
the second `0x0004`, the third `0x0006`.

**Allocated views:** `allocatedID` is the numeric ID assigned by
`Network.AllocateViewID()`. The first allocated ID for player 1 is 50
(from block_start=1, stride=50), producing `0x2000 | (50 << 5) = 0x2640`.

#### 3.6.2 Decoding

```
if val == 0x0000:
    type = 'internal'
elif val & 0x2000:
    type = 'allocated'
    id = (val & 0x1FFF) >> 5
else:
    type = 'scene'
    id = val >> 1
```

#### 3.6.3 Verified Values

| View | Type | ID | Formula | Constant |
|------|------|----|---------|----------|
| Loader | Scene-baked | 1 | `1 << 1` | `0x0002` |
| SecondRpcBehaviour | Scene-baked | 2 | `2 << 1` | `0x0004` |
| InheritedRpcDerived | Scene-baked | 3 | `3 << 1` | `0x0006` |
| SecondRpcBehaviour | Allocated | 50 | `0x2000 \| (50 << 5)` | `0x2640` |
| SecondRpcBehaviour | Allocated | 51 | `0x2000 \| (51 << 5)` | `0x2660` |
| SecondRpcBehaviour | Allocated | 52 | `0x2000 \| (52 << 5)` | `0x2680` |
| SecondRpcBehaviour | Allocated | 54 | `0x2000 \| (54 << 5)` | `0x26c0` |
| InheritedRpcDerived | Allocated | 51 | `0x2000 \| (51 << 5)` | `0x2660` |
| `__RPCNetworkInstantiate` | Internal | — | `0` | `0x0000` |

The field is **per-view-ID, not per-class**: same class on different
allocated IDs produces different constants; different classes on the same
allocated ID produce the same constant.

**This field is the RPC routing key.** Unity uses the constant — not the
u64 timestamp header — to route incoming RPCs to the correct
NetworkView. An RPC with a wrong constant is either delivered to the
wrong NetworkView (if one exists at that ID) or dropped with an error.
Correct constant = delivered; wrong constant = lost.

A server implementation MUST set this field to the correct packed
NetworkViewID for the target view. See the delivery test in the research
doc `2026-06-27-rpc-constant-field-investigation.md` for experimental
proof: 3/10 RPCs delivered (the 3 with correct constant), 7/10 dropped.

### 3.7 Relay Format

When the server relays an RPC to other clients (e.g. for RPCMode.Others
or RPCMode.All), the relayed message differs from the original:

1. **Counter is re-assigned** — the server uses its own per-client
   RPC sequence counter, not the original sender's counter.
2. **Mode is preserved** — `Others` (1) stays `Others` (1).
3. **5 zero bits are appended** after the parameters.
4. **The `remaining` field increases by 5** to account for the extra bits.
5. All other fields (constant, tag, method hash) are preserved.

The relay padding increases the total bit length by exactly 5 bits.
For example, a subsequent-use `RPC_Int(42)` with mode=Others is 172 bits
without relay and 177 bits with relay.

An encoder supporting relay adds a `relay` flag:
```
if relay:
    remaining += 5
    total_bits += 5
    # after writing params:
    write_bits(0, 5)
```

### 3.8 RPC Batch Index (msg_id 0x07)

After receiving a first-use RPC for a method it hasn't seen before, the
receiver sends an **RPC Batch Index** message (msg_id `0x07`) back to the
sender. This message registers the receiver's own `method_index` for that
method, telling the sender what index to use in subsequent-use messages.

The message uses UNRELIABLE reliability (no retransmit).

#### 3.8.1 Wire Format

| Offset | Size | Field |
|--------|------|-------|
| 0 | 1 | msg_id = `0x07` |
| 1–4 | 4 | `method_id_bit_count / 2` (uint32 BE) |
| 5+ | var | BitStream payload (see below) |

The BitStream payload contains:

| Bit Offset | Width | Field |
|------------|-------|-------|
| 0 | 1 | flag (observed: always 0) |
| 1 | N | method_id (N = `method_id_bit_count`, same encoding as §3.3.2) |
| 1+N | 5 | method_index >> 2 (the sender's own index for the method, divided by 4) |
| 1+N+5 | pad | zero padding to byte boundary |

Total bit count: `1 + method_id_bit_count + 5`. The RakNet
bit_length is set to this value (not rounded up); byte padding is
cosmetic. The 5-bit field stores the method_index right-shifted by 2;
the receiver left-shifts by 2 to recover the full index used in
subsequent-use RPC encoding (§3.2). Note the 5-bit field can only
represent indices 0–124 in steps of 4 — it cannot express the ≥128
indices covered by §3.2's extended-header case, so batch-index
registration and the actual subsequent-use wire encoding diverge in
representable range at the high end; this hasn't been observed to
matter in practice (see §3.2's extended-header note).

#### 3.8.2 Observed Examples

From a cross-binary experiment with original (O) and patched (P) builds:

| Direction | Method | method_id (hex) | Registered idx | Build |
|-----------|--------|-----------------|----------------|-------|
| O→P | RPC_Int | 0c93b276d5b1d456 | 0x60 | Original |
| P→O | RPC_Int | 0c93b276d5b1d456 | 0x6c | Patched |
| O→P | RPC_Float | 0c93b276d5b1564a1a | 0x64 | Original |
| P→O | RPC_Float | 0c93b276d5b1564a1a | 0x70 | Patched |

The index difference (0x0c = 12) matches exactly 3 extra [RPC] methods
× 4 stride added by the patching.

#### 3.8.3 Protocol Sequence

For method M between peers A and B:

```
A → B:  FIRST-USE [M] (hash, RELIABLE_ORDERED)
B → A:  BATCH INDEX [M, idx=Y] (UNRELIABLE)    ← B's own index
A → B:  SUBSEQUENT-USE [M, idx=Y] (RELIABLE_ORDERED)
```

A uses B's registered index Y (not A's own index) for all subsequent
calls to M addressed to B. If A also calls M and B has a different index,
B separately registers its index with A.

#### 3.8.4 Implementer Notes

A non-Unity implementation that always sends first-use does not need to
send or process batch index messages. However, to support subsequent-use
(saving ~20 bytes per RPC), an implementation must:

1. **Receiving side:** After processing an incoming first-use, send a
   batch index message containing the receiver's own `method_index` for
   that method.
2. **Sending side:** Listen for incoming batch index messages. Store the
   registered index per peer per method. Use the registered index (not
   the local index) when encoding subsequent-use.
3. **Fallback:** If no batch index is received, continue sending
   first-use indefinitely.

### 3.9 WriteCompressed\<uint32\>

RakNet's compressed write for uint32, with DoEndianSwap=true (big-endian
on wire for x86).

The algorithm processes bytes from the least significant end. For each
zero byte, writes a flag bit `1` (skip). A flag bit `0` means the byte
is non-zero and all remaining bytes (from this position up) are written raw.

For the final (most significant) byte, there's a half-byte optimization:
- Flag `1`: only the bottom 4 bits are written (top nibble was zero)
- Flag `0`: all 8 bits are written

**Example:** encoding `0x00000038` (56 decimal, 7 bytes × 8 bits):
- Byte 3 (LSB) = 0x00 → flag=1 (skip)
- Byte 2 = 0x00 → flag=1 (skip)
- Byte 1 = 0x00 → flag=1 (skip)
- Byte 0 (MSB) = 0x38 → top nibble = 0x3 ≠ 0 → flag=0, write 8 bits
- Wire: `1 1 1 0 00111000` = 12 bits

### 3.10 Huffman String Encoding

Strings in RPCs use RakNet's StringCompressor with the
`englishCharacterFrequencies` table. The encoded bitstream uses a
Huffman tree built from these character frequencies.

The encoding process:
1. WriteCompressed\<uint32\> writes the total Huffman-encoded bit length
2. Each character is Huffman-encoded using the frequency tree
3. Output is padded to byte alignment

Decoding reverses: read the bit length, then decode characters from the
Huffman bitstream until the expected length is consumed.

---

## 4. State Sync Wire Format

State sync (OnSerializeNetworkView) uses msg_id `0x1b`. The default
mode uses UNRELIABLE_SEQUENCED reliability, while ReliableDeltaCompressed
mode uses RELIABLE_ORDERED — the same as RPCs.

**Disambiguating RPCs from state sync when both use RELIABLE_ORDERED:**
Byte 9 (the 10th byte) differs: RPCs always have `0x0b` (the marker byte),
while state sync has the flags byte (`0x80` for first message, `0x7f` for
subsequent). This check is necessary for correct dispatch.

### 4.1 Header (96 bits = 12 bytes)

| Bit Offset | Width | Field |
|------------|-------|-------|
| 0–7 | 8 | msg_id = `0x1b` (ID_TIMESTAMP) |
| 8–71 | 64 | u64 BE `senderRakNetGetTimeMS()` — server uptime in ms. Same field as the RPC header; RakNet's `ShiftIncomingTimestamp` reads bytes 1-8 as u64 for all 0x1b messages. |
| 72–79 | 8 | flags: `0x80` on first message, `0x7f` on subsequent (distinguishes state sync from RPCs, which use `0x0b`) |
| 80–95 | 16 | packed NetworkViewID (target view for this state sync stream) |

Data bit count = `bit_length` (from RakNet header) - 96.

### 4.2 BitStream Serialization Types

Values are written sequentially in the order `BitStream.Serialize()` is
called, with NO alignment padding between fields. Types are bit-packed.

| Type | Encoding | Size (bits) |
|------|----------|-------------|
| int | signed 32-bit big-endian | 32 |
| float (maxDelta) | IEEE 754 32-bit big-endian | 32 |
| Vector3 (maxDelta) | 3× float32 BE (x, y, z) | 96 |
| Quaternion (maxDelta) | 4× float32 BE (x, y, z, w) | 128 |
| bool | single bit (1=true, 0=false) | 1 |
| short | signed 16-bit big-endian | 16 |
| char | 8-bit ASCII (NOT UTF-16) | 8 |

The `maxDelta` parameter for float/Vector3/Quaternion controls when the
engine considers the value changed enough to send an update. It does NOT
affect the wire encoding — the full value is always sent.

Trailing bits in the last byte are zero-padded.

**Note:** `BitStream.Serialize` does NOT support `string` type.

### 4.3 Worked Example

Serializing `int(42) + float(3.14) + Vector3(1,2,3) + Quaternion(Euler(30,60,90)) + bool(true) + short(1234) + char('X')`:

```
Data bits: 32 + 32 + 96 + 128 + 1 + 16 + 8 = 313 bits
RakNet bit_length: 96 (header) + 313 = 409 bits
Payload bytes: ⌈409/8⌉ = 52 bytes

Header (12 bytes):
  1b 00 00 00 00 00 00  [ViewID=0]
  06 95                  [timestamp]
  7f                     [subsequent flag]
  00 04                  [constant]

Data (40 bytes):
  00 00 00 2a            int(42) = 0x0000002a
  40 48 f5 c3            float(3.14) = 0x4048f5c3
  3f 80 00 00            float(1.0)
  40 00 00 00            float(2.0)
  40 40 00 00            float(3.0)
  3e ff ff ff            quat.x ≈ 0.5
  3e 3b 67 ae            quat.y ≈ 0.183
  3e ff ff fe            quat.z ≈ 0.5
  3f 2e d9 eb            quat.w ≈ 0.683
  82                     bool(1) + first 7 bits of short(1234)
  69                     next 8 bits
  2c                     last 1 bit of short + char('X') = 0x58
  00                     7 zero-padding bits
```

---

## 5. NetworkViewID Encoding

NetworkViewIDs in the wire format use a 48-bit (6-byte) big-endian
encoding as `uint16 BE + uint32 BE`.

The first scene-baked NetworkView uses AllocatedID 0 on the wire:
`00 00 00 00 00 00`. ViewID 1 encodes as `00 00 00 00 00 01`.

Note: Unity's `NetworkView.viewID` is NOT the same as the wire-format
AllocatedID. The first scene-baked view has AllocatedID 0, regardless of
what Unity's API reports.

---

## 6. Network Groups

Network groups control message filtering per-NetworkView. Each
`NetworkView` has a `.group` property (integer, default 0).

**Key finding: Groups have NO wire protocol.** The group number is NOT
encoded in RPC or state sync message payloads. Instead, groups are a
purely local filtering mechanism on each endpoint.

### 6.1 Filtering APIs

| API | Scope | Effect |
|-----|-------|--------|
| `NetworkView.group = N` | Per-view | Assigns the view to group N |
| `Network.SetSendingEnabled(group, enabled)` | Local, per-group | Prevents outbound messages from views in that group |
| `Network.SetSendingEnabled(player, group, enabled)` | Per-player, per-group | Same, targeted at a specific player |
| `Network.SetReceivingEnabled(player, group, enabled)` | Per-player, per-group | Prevents processing inbound messages from views in that group |

### 6.2 Behavior

- `SetSendingEnabled(group, false)` causes the sender to silently drop
  messages. The RPC/state sync call returns normally but no packet is
  transmitted. Verified: blocked RPCs do not appear on the wire.
- `SetReceivingEnabled(group, false)` causes the receiver to silently
  discard messages from views in that group. The receiver determines the
  group by looking up the incoming message's `NetworkViewID` in its local
  view registry.
- Neither API generates any control messages on the wire.
- By default, all groups are enabled for both sending and receiving.

### 6.3 Server Implementation

For a replacement server, group support is purely server-side logic:

1. Maintain a `viewID → group` mapping for all known views.
2. Track per-client group enablement (both send and receive).
3. When sending to a client, check if the view's group is enabled for
   that client; skip the send if disabled.
4. When processing an incoming message, look up the NetworkViewID's group
   and check if receiving is enabled for that group from that client.

The Distance game uses three groups (GlobalGroup=0, GameModeGroup=1,
LobbyGroup=2) and toggles them during scene transitions.

---

## 7. ViewID Allocation

`Network.AllocateViewID()` is a client-side call that allocates a
NetworkViewID from a pre-assigned range. The server assigns each player
a ViewID range via the player assignment message (0x81).

### 7.1 Player Assignment Message (0x81)

| Offset | Size | Field | Description |
|--------|------|-------|-------------|
| 0 | 1 | msg_id | `0x81` |
| 1–4 | 4 | constant_1 | uint32 BE, always 1 (scene/level marker) |
| 5–8 | 4 | constant_0 | uint32 BE, always 0 |
| 9–12 | 4 | player_index | uint32 BE, 1-based, increments per client |
| 13–16 | 4 | viewid_stride | uint32 BE, ViewIDs per block (default 50) |
| 17–20 | 4 | constant_2 | uint32 BE, always 2 |
| 21–24 | 4 | block_start | uint32 BE, first ViewID block for this player |
| 25–28 | 4 | block_end | uint32 BE, last ViewID block for this player |

Multi-client observations (max_connections=4, 4 clients connected):

| Player | player_index | viewid_stride | block_start | block_end |
|--------|-------------|---------------|-------------|-----------|
| 1 | 1 | 50 | 1 | 2 |
| 2 | 2 | 50 | 3 | 4 |
| 3 | 3 | 50 | 5 | 6 |
| 4 | 4 | 50 | 7 | 8 |

Block assignment formula: `block_start = player_index * 2 - 1`,
`block_end = player_index * 2`.

### 7.2 Allocation Scheme

The client computes its ViewID allocation start as
`block_start * viewid_stride`. Each block contains `viewid_stride`
allocatable ViewIDs.

| Player | block_start | Allocation Start | Observed IDs |
|--------|------------|-----------------|-------------|
| 1 | 1 | 1×50 = 50 | 50, 51, 52 |
| 2 | 3 | 3×50 = 150 | 150, 151, ... |
| 3 | 5 | 5×50 = 250 | 250, 251, ... |
| 4 | 7 | 7×50 = 350 | 350, 351, ... |

The client calls `Network.AllocateViewID()` which returns the next
sequential ID from its allocated block. No per-allocation wire traffic —
the allocation is entirely local after receiving the block in the 0x81
message.

Each player gets `(block_end - block_start + 1) * viewid_stride`
allocatable ViewIDs (default: 2 × 50 = 100). When the range is
exhausted, `AllocateViewID()` returns `AllocatedID 0` (unassigned) and
Unity logs a warning — no exception, no crash.

`Network.AllocateViewID()` called before connection returns
`NetworkViewID.unassigned` (AllocatedID 0).

### 7.3 Scaling Behavior

The viewid_stride remains 50 regardless of max_connections. Unity never
adjusts stride, caps, or refuses higher max_connections (tested up to
2048 with 512 simultaneous clients). The block formula `player * 2 - 1`
is constant — player 512 gets alloc_start=51150 with no issues.

### 7.4 Server Implementation

The server:
1. Sends the 0x81 message with the player's block range.
2. Tracks which ViewIDs each player has allocated.
3. Frees all allocated ViewIDs on player disconnect (equivalent to
   `Network.RemoveRPCs()` / `DestroyPlayerObjects()`).
4. **Enforces ViewID ownership** on incoming RPCs: if an RPC's
   `targetView` (§3.6) decodes to an allocated ViewID outside the
   sender's block, the server drops the RPC silently. This prevents
   re-broadcast loops when clients relay events via `Broadcast()`.
5. **Recycles player indices** on disconnect: disconnected player
   indices go into a free list. New connections draw from the free
   list first, falling back to `nextPlayerIndex++` when empty. This
   keeps ViewID block assignments stable across reconnects — clients
   that allocate car ViewIDs on first connect and reuse them on
   reconnect would otherwise get a different block and fail the
   ownership check.

---

## 8. ReliableDeltaCompressed State Sync

When a NetworkView uses `NetworkStateSynchronization.ReliableDeltaCompressed`,
state sync messages use `RELIABLE_ORDERED` reliability (instead of
`UNRELIABLE_SEQUENCED`) and interleaved dirty flags to skip unchanged fields.

### 8.1 Header

Same 96-bit (12-byte) header as unreliable state sync:

| Offset (bits) | Size | Field | Description |
|---------------|------|-------|-------------|
| 0 | 8 | msg_id | `0x1b` (ID_TIMESTAMP) |
| 8 | 64 | timestamp | u64 BE `senderRakNetGetTimeMS()` |
| 72 | 8 | flags | `0x80` = first, `0x7f` = subsequent |
| 80 | 16 | view_id | packed NetworkViewID |

### 8.2 Data: Interleaved Dirty Flags

After the header, for **each serialized field** in order:

1. **1 dirty bit**: `1` if the field changed from the last acknowledged
   state, `0` if unchanged.
2. **If dirty**: the full new value at the field's native width (e.g.,
   32 bits for int/float). NOT XOR-encoded — the raw new value.

This means unchanged fields cost only 1 bit each. A message with 3
fields where none changed is just 3 bits of data (plus the 96-bit
header = 99 bits total).

### 8.3 Transport Differences from Unreliable

| Property | Unreliable | ReliableDeltaCompressed |
|----------|------------|------------------------|
| Reliability | UNRELIABLE_SEQUENCED | RELIABLE_ORDERED |
| Data encoding | Full values every tick | Dirty flags + changed values |
| State tracking | None | Server tracks last-sent per client |
| First message | flags=0x80, full data | flags=0x80, dirty flags + changed values |

### 8.4 Worked Example

Serializing 3 fields (int A=42, int B=0, float C=0.0) where only A
changed from a previous state of (0, 0, 0.0):

```
Header (12 bytes):
  1b 00 00 00 00 00 00  [msg_id + ViewID=0]
  xx xx                  [timestamp]
  7f                     [subsequent]
  00 04                  [constant]

Data (35 bits):
  1                      dirty_A = 1 (changed)
  00000000 00000000 00000000 00101010   A = 42
  0                      dirty_B = 0 (unchanged)
  0                      dirty_C = 0 (unchanged)
```

---

## 9. Message Type Summary

| msg_id | Reliability | Direction | Purpose |
|--------|-------------|-----------|---------|
| `0x00` | UNRELIABLE/RELIABLE | both | Internal ping |
| `0x03` | UNRELIABLE | both | Connected pong |
| `0x04` | RELIABLE | C→S | Connection request |
| `0x07` | UNRELIABLE | both | RPC batch index registration (§3.8) |
| `0x09` | (offline) | C→S | Open connection request |
| `0x0a` | (offline) | S→C | Open connection reply |
| `0x0e` | RELIABLE_ORDERED | S→C | Connection request accepted |
| `0x11` | RELIABLE_ORDERED | C→S | New incoming connection |
| `0x1b` | RELIABLE_ORDERED | both | RPC |
| `0x1b` | UNRELIABLE_SEQUENCED | S→C | State sync |
| `0x81` | RELIABLE_ORDERED | S→C | Unity player assignment |
| `0x83` | RELIABLE_ORDERED | C→S | Unity player ready |

---

## 10. Password Authentication

Password authentication is a **RakNet transport-level** feature, not
Unity-specific framing. The password is appended as plaintext ASCII bytes
to the connection request message (0x04).

### 10.1 Wire Encoding

| Scenario | 0x04 Size | Contents after GUID |
|----------|-----------|---------------------|
| No password | 25 bytes (200 bits) | (none) |
| Password "secret123" | 34 bytes (272 bits) | `73 65 63 72 65 74 31 32 33` (ASCII) |

The server checks the password by comparing the bytes after the GUID in
the connection request against `Network.incomingPassword` encoded as ASCII.
If the password doesn't match, RakNet rejects the connection before the
Unity handshake begins.

### 10.2 Server Implementation

1. When `incomingPassword` is set, extract bytes 25+ from incoming 0x04
   messages and compare against the expected password.
2. If mismatch, send `ID_CONNECTION_BANNED` (0x17) and close.
3. If match (or no password required), proceed with normal handshake.

---

## 11. Network.SetLevelPrefix

`Network.SetLevelPrefix(int)` does **NOT** modify the wire format. RPCs
sent with different level prefixes are wire-identical to baseline RPCs.

SetLevelPrefix is purely a **receiver-side filtering mechanism**: the
receiver discards incoming messages whose level prefix doesn't match
its current local prefix. No prefix value appears in any RPC or state
sync header field.

### 11.1 Server Implementation

For a replacement server, level prefix filtering is purely server-side:

1. Track each client's current level prefix.
2. Provide an API or control message for clients to declare their prefix
   (this is application-specific since Unity has no wire encoding for it).
3. Filter outgoing messages based on prefix matching.

---

## 12. Internal RPCs

Unity uses internal RPCs for operations like `Network.Instantiate`. These
use the same 0x1b message format as user RPCs with one key difference:

| Field | User RPCs | Internal RPCs |
|-------|-----------|---------------|
| user_rpc_constant (16 bits) | Per-view (see §3.6) | `0x0000` |

The method identification (GUID + hash) uses the same Huffman encoding
algorithm as user RPCs. Internal method names are prefixed with `__RPC`.

### 12.1 Known Internal RPCs

| Method Name | GUID (hex) | Hash (hex) |
|-------------|------------|------------|
| `__RPCNetworkInstantiate` | `2ad8d5b1324e` | `c9da62174c65fea2ddb15a3585` |

Note that `__RPCNetworkInstantiate` starts with `__R`, not `RPC_`, so
its GUID (`2ad8d5b1324e`) differs from user RPCs that share the `RPC_`
prefix (`0c93b276d5b1`).

---

## 13. Network.Instantiate Wire Format

`Network.Instantiate(prefab, position, rotation, group)` uses the
internal RPC `__RPCNetworkInstantiate` to transmit the instantiation
to all clients.

### 13.1 Message Structure

The message uses the standard first-use RPC format (§3.3) with
constant=`0x0000` (internal RPC). The method hash identifies
`__RPCNetworkInstantiate`.

### 13.2 Parameter Layout (421 bits observed)

| Bit Offset | Width | Field | Observed Value |
|------------|-------|-------|----------------|
| 0–148 | 149 | Pre-transform data | See §13.3 |
| 149–180 | 32 | position.x (float32 BE) | 1.0f |
| 181–212 | 32 | position.y (float32 BE) | 2.0f |
| 213–244 | 32 | position.z (float32 BE) | 3.0f |
| 245–276 | 32 | rotation.x (float32 BE) | 0.0f |
| 277–308 | 32 | rotation.y (float32 BE) | 0.0f |
| 309–340 | 32 | rotation.z (float32 BE) | 0.0f |
| 341–372 | 32 | rotation.w (float32 BE) | 1.0f |
| 373–420 | 48 | Post-transform data | See §13.4 |

Position and rotation are verified: Vector3(1,2,3) and Quaternion.identity
match exactly at the documented bit offsets.

### 13.3 Pre-Transform Data (149 bits)

| Bit Offset | Width | Field | Description |
|------------|-------|-------|-------------|
| 0–15 | 16 | Group/flags | See below |
| 16–148 | 133 | Prefab identifier | Opaque encoding, unique per prefab |

**Group/flags field (16 bits):**

| Bits | Width | Field | Observed |
|------|-------|-------|----------|
| 15–6 | 10 | Reserved | Always 0 |
| 5–3 | 3 | Network group | 0 or 5 |
| 2 | 1 | Flag | Always 1 |
| 1–0 | 2 | Level prefix | Always 0 |

Examples: group=0 → `0x0004` (= 0|0<<3|1<<2|0), group=5 → `0x002C` (= 0|5<<3|1<<2|0).

**Prefab identifier (133 bits):**
Confirmed by differential analysis — two instantiations of the same prefab
("NetworkPrefab") produce identical 133-bit regions, while a different
prefab ("NetworkPrefab2") produces a completely different bit pattern.
The encoding is NOT Huffman-encoded text or ASCII. It may be a hash of
the prefab's asset path or an internal Unity serialization format.

### 13.4 Post-Transform Data (48 bits)

| Bit Offset | Width | Field | Description |
|------------|-------|-------|-------------|
| 0–31 | 32 | Unknown (int32 BE) | Always 1 (may be view count or scope) |
| 32–47 | 16 | Instantiated ViewID | 16-bit NetworkViewID encoding (§14) |

The last 16 bits are the NetworkViewID of the newly instantiated object,
using the standard 16-bit packed encoding. Observed: AllocatedID:1
(`0x4040`), AllocatedID:2 (`0x4080`), AllocatedID:3 (`0x40c0`).

### 13.5 ViewID Allocation Handshake

Before `Network.Instantiate` can be used, a ViewID allocation handshake
occurs during connection:

1. **C→S:** `0x83` — client requests ViewID allocation
2. **S→C:** `0x81` — server assigns ViewID block (stride=50, block_start=1 for player 1)

The instantiated object receives a ViewID from the server's pool.

---

## 14. NetworkViewID as RPC Parameter

When `NetworkViewID` is used as an RPC parameter type, it is encoded as
**16 bits** (not the 48-bit encoding used in message headers).

### 14.1 Encoding

Bit 14 distinguishes scene-baked from runtime-allocated ViewIDs:

| Type | Formula | Bit 14 |
|------|---------|--------|
| SceneID:N | `N << 2` | 0 |
| AllocatedID:N | `0x4000 \| (N << 6)` | 1 |

The low bits (2 for SceneID, 6 for AllocatedID) are zero in all
observations. They may encode the level prefix, but this is unverified
since SetLevelPrefix has no wire effect.

**Decoding:**
```
if val & 0x4000:
    type = 'allocated'
    id = (val & 0x3FFF) >> 6
else:
    type = 'scene'
    id = val >> 2
```

### 14.2 Verified Encodings

| NetworkViewID | 16-bit Wire Value | Formula |
|---------------|-------------------|---------|
| SceneID:1 | `0x0004` | 1 << 2 = 4 |
| AllocatedID:1 | `0x4040` | 0x4000 + 1×64 |
| AllocatedID:2 | `0x4080` | 0x4000 + 2×64 |
| AllocatedID:3 | `0x40C0` | 0x4000 + 3×64 |
| AllocatedID:50 | `0x4C80` | 0x4000 + 50×64 |

### 14.3 RPC Method

The `RPC_NetworkViewID` method has:
- Hash: `310ba632fd579053a8ce`
- Method index: `0x74` = (37 - 1 - 7) × 4

---

## 15. NetworkPlayer as RPC Parameter

`NetworkPlayer` is encoded as **int32 BE** — the player's index value.

| Player | Wire Value |
|--------|------------|
| Server (index 0) | `0x00000000` |
| Client 1 (index 1) | `0x00000001` |

The `RPC_NetworkPlayer` method has:
- Hash: `310ba632fe7649ab19`
- Method index: `0xE0` = (36 - 1 - 7) × 4

---

## 16. Disconnect Cleanup (RemoveRPCs / DestroyPlayerObjects)

### 16.1 Wire Protocol

`Network.RemoveRPCs(player)` and `Network.DestroyPlayerObjects(player)` are
**purely server-side operations**. They produce **no wire messages**.

The only disconnect-related wire message is `0x15` (`ID_DISCONNECTION_NOTIFICATION`),
sent by the disconnecting peer. After receiving this, the server performs
cleanup internally:

1. Remove all buffered RPCs associated with the disconnecting player
2. Destroy all NetworkView objects owned by the disconnecting player
3. Free the player's ViewID allocation range

### 16.2 Verification

Experiment: Unity server with `DisconnectCleanupExperiment`. Client connects,
allocates ViewIDs, sends buffered RPC, then disconnects. Server calls
`Network.RemoveRPCs(player)` and `Network.DestroyPlayerObjects(player)` in the
`OnPlayerDisconnected` callback.

Capture shows: client sends disconnect (last frame), server ACKs it. No
additional frames from server after the cleanup calls. Both APIs complete
synchronously with no wire traffic.

### 16.3 Implementation Notes

A Python server implementation should:
- Clean up per-client state (ViewID allocations, delta state, group memberships)
- Remove any buffered RPCs from the disconnecting player
- The peer object (and its split packet assembler) is garbage-collected
  when removed from the peer map

---

## Appendix A: Huffman Frequency Table

The Huffman tree uses RakNet's `englishCharacterFrequencies` table.
See `protocol/huffman.py` for the full table and tree construction.

## Appendix B: Capture Methodology

All captures were made using:
- Unity 2018.1.6f1 Linux headless player
- Server and client running in the same Linux network namespace
- Traffic captured on loopback with `tshark -i lo`
- `Network.InitializeSecurity()` never called (plaintext payloads)
- Controlled experiments with known RPC values for differential analysis
