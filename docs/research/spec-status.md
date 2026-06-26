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

**Known unknowns:**
- 0x81 player assignment: fields 2-3 and 5-7 have unknown purpose (observed as 0, 1, 2, 1, 2). Only field 1 (player_index) and field 4 (viewid_base) are confirmed.

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

---

## Known Unknowns

Fields that are decoded positionally but whose semantics or derivation are not fully understood.

| Location | Field | Width | Observed Values | Impact |
|----------|-------|-------|-----------------|--------|
| §2.3 (0x81) | fields 2,3,5,6,7 | 5×32 bits | 0, 1, 2, 1, 2 | Unknown — may matter for multi-client |
| §3.3.1 | method_tag | 4 bits | 0, 4, 8, C | Cosmetic — Unity accepts 0 |
| §4.1 | state sync constant | 16 bits | 0x0004 | Unknown purpose, always same |
| §13.3 | prefab identifier | 133 bits | Opaque per-prefab | Cannot encode from name |
| §13.4 | post-transform int32 | 32 bits | Always 1 | May be view count |
| §14.1 | ViewID low bits | 2-6 bits | Always 0 | May encode level prefix |

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

### 3. Split packet reassembly untested at scale

The reassembly code handles the protocol correctly but has never been
tested with payloads large enough to actually split (>~1200 bytes).
Large byte[] RPC params or many-field state sync could trigger this.

### 4. Multi-client interop untested

Only single-client connections have been verified. The 0x81 player
assignment message fields (2,3,5,6,7) may differ for multi-client
scenarios. ViewID range management and concurrent dispatch are untested.

### 5. Network.RemoveRPCs / DestroyPlayerObjects not implemented

Distance-server calls both on player disconnect. Our server implementation
cleans up allocated ViewIDs but doesn't send any wire messages for these
operations. The wire protocol for these (if any) is uninvestigated.

### 6. RPCMode.Player target bit semantics

The 1-bit target field after the RPCMode nibble (when mode=Player) is
always 0 in observations. It may encode the target player index or be
a flag. Sending RPC to a specific player works via transport-level
addressing, but the bit's purpose is unconfirmed.

---

## Distance-Server Gap Analysis

Features the distance-server project requires, mapped against our implementation status.

| Feature | Distance Uses? | Our Status | Gap? |
|---------|---------------|------------|------|
| RPC with `byte[]` param | Yes (primary data channel) | Implemented, tested | No |
| RPC with `int` params | Yes (time sync: 2× int) | Implemented, tested | No |
| RPC with no params | Yes (time sync request) | Implemented, tested | No |
| RPCMode.Others | Yes (broadcast) | Implemented, tested | No |
| RPCMode.Player | Yes (targeted send) | Implemented, **untested in interop** | **Yes** |
| ReliableDeltaCompressed sync | Yes (1 view/car) | Implemented, tested | No |
| Unreliable state sync | Yes (2 views/car) | Implemented, tested | No |
| Multiple NetworkViews | Yes (3 per car) | Implemented, **untested** | **Yes** |
| Multi-client (12-24 players) | Yes | Implemented, **untested** | **Yes** |
| Password auth | Yes (server-side) | Implemented, **untested in interop** | **Yes** |
| Network.RemoveRPCs | Yes (on disconnect) | **Not implemented** | **Yes** |
| Network.DestroyPlayerObjects | Yes (on disconnect) | **Not implemented** | **Yes** |
| Network groups | Not in reimplemented bridge | Implemented (server-side) | No |
| Network.SetLevelPrefix | No | Documented (no wire format) | No |
| Network.Instantiate | No | Decode-only | No |
| Buffered RPCs | No | Not implemented | No |
| Master Server | Yes (registration) | **Out of scope** (separate protocol) | N/A |
| NetworkViewID as param | Yes (3 IDs per car) | Implemented, tested | No |
| NetworkPlayer as param | Yes (as RPC target) | Implemented, tested | No |

### Critical gaps for Distance:

1. **RPCMode.Player interop** — Distance uses targeted RPCs heavily. Untested with real Unity.
2. **Multi-client** — Distance supports 12-24 players. Our server has never handled >1.
3. **Multiple NetworkViews per object** — Distance uses 3 views per car (different sync modes). Untested.
4. **Network.RemoveRPCs / DestroyPlayerObjects** — Called on every disconnect. Wire protocol unknown.
5. **Password auth interop** — Distance sets `incomingPassword`. Untested with Unity client.
6. **Large byte[] payloads** — Distance's primary data channel. Split packet path untested.
