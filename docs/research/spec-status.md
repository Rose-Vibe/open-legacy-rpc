# Spec Status & Known Unknowns

Current status of every section in the wire format reference spec,
plus known unknowns and issues discovered during implementation.

Last updated: 2026-06-26

---

## Section Status

### §1 Transport: RakNet 3.731 — COMPLETE

| Subsection | Status | Notes |
|------------|--------|-------|
| 1.1 UDP Datagram Structure | Complete | All fields decoded |
| 1.2 ACK/NAK Range List | Complete | Encode/decode implemented |
| 1.3 Encapsulated Message Header | Complete | All 5 reliability levels handled |
| 1.4 Split Packet Reassembly | Complete | Implemented but not stress-tested with large payloads |
| 1.5 IP Address Encoding | Complete | Bitwise-inverted IPv4 + uint16 BE port |

### §2 Connection Handshake — COMPLETE

| Subsection | Status | Notes |
|------------|--------|-------|
| 2.1 Offline Phase (0x09/0x0A) | Complete | MTU-padded, GUID + magic + address |
| 2.2 Connected Phase (0x04/0x0E/0x11) | Complete | Password appended to 0x04 as plaintext |
| 2.3 Unity Layer (0x83/0x81) | Mostly complete | 0x81 has 4 unknown fields (5-8, 9-12, 17-20, 21-28) |
| 2.4 Keepalive (0x00/0x03) | Complete | Ping/pong timestamps |

All 0x81 fields decoded (M10a): constant_1=1, constant_0=0, player_index,
viewid_stride=50, constant_2=2, block_start=player*2-1, block_end=player*2.

### §3 RPC Wire Format — COMPLETE (one cosmetic unknown)

| Subsection | Status | Notes |
|------------|--------|-------|
| 3.1 Common Header | Complete | msg_id + ViewID + counter + 0x0b marker + first_use flag |
| 3.2 Subsequent-Use Format | Complete | 7-bit method index, fully decoded |
| 3.2.1 Method Index Derivation | Complete | Formula: `(RID - 1 - iface_count) × 4` |
| 3.3 First-Use Format | Complete | Huffman method hash, length indicator |
| 3.3.1 Internal Metadata | **Mostly complete** | `method_tag` (4 bits) derivation unknown |
| 3.3.2 Method Identifier Derivation | Complete | Huffman encoding algorithm fully reproduced |
| 3.4 RPCMode Values | Complete | 6 modes, Player has +1 target bit |
| 3.5 Parameter Encoding | Complete | All 8 param types implemented |
| 3.6 WriteCompressed | Complete | Big-endian uint32 compression |
| 3.7 Huffman String Encoding | Complete | RakNet StringCompressor reproduced |

**Known unknowns:**
- `method_tag` (4 bits in first-use metadata): values 0/4/8/C observed, derivation unknown. Unity accepts 0, so non-blocking.

### §4 State Sync Wire Format — COMPLETE

| Subsection | Status | Notes |
|------------|--------|-------|
| 4.1 Header | Complete | 96-bit header, RPC/sync disambiguation via byte 9 |
| 4.2 BitStream Types | Complete | 7 types: int, float, Vector3, Quaternion, bool, short, char |
| 4.3 Worked Example | Complete | Verified against capture |

**Known unknowns:**
- Constant `0x0004` at bits 80-95: purpose unknown, always the same value. Non-blocking.

### §5 NetworkViewID Encoding — COMPLETE

48-bit wire format fully decoded. Scene-baked vs allocated distinction understood.

### §6 Network Groups — COMPLETE

Groups have NO wire protocol — purely local filtering. Server-side implementation complete.

### §7 ViewID Allocation — COMPLETE

Stride=50 scheme, 0x81 assignment message, local allocation after base received.

### §8 ReliableDeltaCompressed State Sync — COMPLETE

Dirty-flag interleaving, RELIABLE_ORDERED reliability, encode/decode implemented.

### §9 Message Type Summary — COMPLETE

All 12 message types documented.

### §10 Password Authentication — COMPLETE

Plaintext ASCII appended to 0x04. Server-side comparison implemented.

### §11 Network.SetLevelPrefix — COMPLETE

No wire format — purely receiver-side filtering.

### §12 Internal RPCs — COMPLETE

Constant 0x0000 vs 0x0002 distinction. `__RPCNetworkInstantiate` hash known.

### §13 Network.Instantiate — MOSTLY COMPLETE

| Subsection | Status | Notes |
|------------|--------|-------|
| 13.1 Message Structure | Complete | Standard first-use RPC |
| 13.2 Parameter Layout | Complete | 421 bits total |
| 13.3 Pre-Transform Data | **Mostly complete** | Group decoded, prefab ID is opaque 133 bits |
| 13.4 Post-Transform Data | **Mostly complete** | ViewID decoded, int32=1 purpose unknown |
| 13.5 ViewID Allocation | Complete | Linked to §7 |

**Known unknowns:**
- Prefab identifier (133 bits): opaque encoding, can't generate from prefab name. Can pass-through from captures.
- Post-transform int32: always 1, may be view count per prefab.

### §14 NetworkViewID as RPC Parameter — COMPLETE

16-bit packed encoding: SceneID = `N << 2`, AllocatedID = `0x4000 | (N << 6)`. 5 verified data points.

### §15 NetworkPlayer as RPC Parameter — COMPLETE

int32 BE of player index. Verified for indices 0 and 1.

### §16 Disconnect Cleanup — COMPLETE

RemoveRPCs and DestroyPlayerObjects produce no wire messages. Purely
server-side operations. Verified by pcap analysis (M10f).

---

## Known Unknowns

Fields that are decoded positionally but whose semantics or derivation
are not fully understood. None of these block Distance integration.

| Location | Field | Width | Observed Values | Impact |
|----------|-------|-------|-----------------|--------|
| §3.3.1 | method_tag | 4 bits | 0, 4, 8, C | Cosmetic — Unity accepts 0 |
| §4.1 | state sync constant | 16 bits | 0x0004 | Unknown purpose, always same |
| §13.3 | prefab identifier | 133 bits | Opaque per-prefab | Cannot encode from name |
| §13.4 | post-transform int32 | 32 bits | Always 1 | May be view count |
| §14.1 | ViewID low bits | 2-6 bits | Always 0 | May encode level prefix |
| §3.4 | RPCMode.Player target bit | 1 bit | Always 0 | Transport addressing works without it |

### Previously unknown, now resolved

| Location | Field | Resolution |
|----------|-------|------------|
| §2.3 (0x81) | fields 2–7 | All decoded (M10a): constants 1,0 + player_index + stride + constants 2 + block_start/end |
| §1.4 | split packet reassembly | Tested up to 10KB payloads (M10c) |
| §15 | RemoveRPCs / DestroyPlayerObjects | Server-side only, no wire messages (M10f) |

---

## Known Issues

Problems discovered during implementation that are worked around but not fully resolved.

### 1. First-use RPC metadata (method_tag)

We send `method_tag = 0` for all first-use RPCs. Unity accepts this, but
the correct derivation is unknown. **Workaround:** always use subsequent-use
encoding (pre-register method indices), which skips this field entirely.

### 2. Scene-baked ViewID numbering is fragile

The server's primary NetworkView uses ViewID 0 on the wire, but this
depends on the scene setup. Rebuilding the Unity project (e.g., adding
prefabs) can change the numbering. **Workaround:** use wildcard view_id
handlers or discover the view_id dynamically from incoming messages.

### 3. Instantiate prefab identifier is opaque

The 133-bit prefab identifier in `Network.Instantiate` cannot be derived
from the prefab name — it must be captured from a live Unity instance.
**Workaround:** Distance doesn't use `Network.Instantiate`, so this is
non-blocking. For other games, pass-through from captures.

---

## Distance-Server Gap Analysis

Features the distance-server project requires, mapped against our implementation status.

| Feature | Distance Uses? | Our Status | Gap? |
|---------|---------------|------------|------|
| RPC with `byte[]` param | Yes (primary data channel) | Implemented, tested | No |
| RPC with `int` params | Yes (time sync: 2× int) | Implemented, tested | No |
| RPC with no params | Yes (time sync request) | Implemented, tested | No |
| RPCMode.Others | Yes (broadcast) | Implemented, tested | No |
| RPCMode.Player | Yes (targeted send) | Implemented, tested (M10b) | No |
| ReliableDeltaCompressed sync | Yes (1 view/car) | Implemented, tested | No |
| Unreliable state sync | Yes (2 views/car) | Implemented, tested | No |
| Multiple NetworkViews | Yes (3 per car) | Implemented, tested (M10d) | No |
| Multi-client (12-24 players) | Yes | Implemented, tested (M10a, up to 512) | No |
| Password auth | Yes (server-side) | Implemented, tested (M10e) | No |
| Network.RemoveRPCs | Yes (on disconnect) | Server-side only, implemented (M10f) | No |
| Network.DestroyPlayerObjects | Yes (on disconnect) | Server-side only, implemented (M10f) | No |
| Network groups | Not in reimplemented bridge | Implemented (server-side) | No |
| Network.SetLevelPrefix | No | Documented (no wire format) | No |
| Network.Instantiate | No | Decode-only | No |
| Buffered RPCs | No | Not implemented | No |
| Master Server | Yes (registration) | **Out of scope** (separate protocol) | N/A |
| NetworkViewID as param | Yes (3 IDs per car) | Implemented, tested | No |
| NetworkPlayer as param | Yes (as RPC target) | Implemented, tested | No |

### Critical gaps for Distance: **ALL RESOLVED (M10)**

All six gaps identified pre-M10 have been closed:
1. RPCMode.Player interop — tested (M10b)
2. Multi-client — tested up to 512 simultaneous clients (M10a)
3. Multiple NetworkViews — tested with 3 views, mixed sync modes (M10d)
4. RemoveRPCs / DestroyPlayerObjects — server-side only, no wire protocol (M10f)
5. Password auth interop — bidirectional Python↔Unity tested (M10e)
6. Large byte[] payloads — tested up to 10KB with split packets (M10c)

**Remaining gap:** Master Server registration (out of scope — separate protocol).
