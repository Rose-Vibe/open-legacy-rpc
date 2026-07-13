# Spec Status & Known Unknowns

Current status of every section in the wire format reference spec,
plus known unknowns and issues discovered during implementation.

Last updated: 2026-06-27

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
| 2.3 Unity Layer (0x83/0x81) | Complete | All 0x81 fields decoded (M10a) |
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
| 3.3.1 Internal Metadata | Complete | `method_tag` (4 bits): empirically opaque, not derivable from `method_index` or any static property; load-bearing, not cosmetic (see Known Issues) |
| 3.3.2 Method Identifier Derivation | Complete | Huffman encoding algorithm fully reproduced |
| 3.4 RPCMode Values | Complete | 6 modes, Player has +1 target bit |
| 3.5 Parameter Encoding | Complete | All 8 param types implemented |
| 3.6 WriteCompressed | Complete | Big-endian uint32 compression |
| 3.7 Huffman String Encoding | Complete | RakNet StringCompressor reproduced |

**Known unknowns:**
- `method_tag` (4 bits in first-use metadata): **not** a formula —
  empirically disproven for `method_index & 0x0F` on 12 of 13 tested
  methods (see `docs/research/2026-07-12-method-tag-real-derivation.md`).
  Must be captured per-assembly from a real Unity-to-Unity pcap. The
  exact mechanism by which a real Unity client assigns/uses the tag for
  dispatch is not confirmed. distance-server's dispatch-matrix testing
  showed two RPC methods sharing a tag causing a real Unity client to
  silently misdispatch first-use RPCs between them, and our own testing
  showed a wrong tag can also cause outright rejection — this is **not**
  cosmetic. See Known Issue #1 below.

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
| §3.3.1 | method_tag | Derivation is **not** a formula — `method_index & 0x0F` empirically disproven for 12 of 13 tested methods (2026-07-12); must be captured per-assembly from a real pcap. Confirmed load-bearing on a real Unity client via distance-server's dispatch-matrix testing and our own single-variable capture test — see Known Issue #1 |
| §3.2 | subsequent-use RPC, `method_index >= 128` | Header is 4 bits wider (extension flag at bit 89), not a fixed-width field — confirmed against a real Unity client via `scripts/index-sweep-server.py` (2026-07-12/13); see Known Issue #4 for residual uncertainty above index 132 |
| §3.2.1 | RPC Batch Index (`0x07`) usability for a non-Unity sender | The receiver's self-reported index is **not** usable for subsequent-use encoding when the sender is a non-Unity implementation — confirmed for all 13 Loader RPC methods (2026-07-13); see Known Issue #5 |

---

## Known Issues

Problems discovered during implementation that are worked around but not fully resolved.

### 1. First-use RPC metadata (method_tag) — not derivable, collisions cause silent misdispatch or rejection

**Erratum (2026-07-12):** the paragraph originally here claimed
`method_tag = method_index & 0x0F` was a correct derivation and that the
only remaining risk was tag-space collisions between correctly-derived
tags. That premise is empirically disproven — the formula produces the
wrong tag for 12 of the 13 Loader test RPC methods (see
`docs/research/2026-07-12-method-tag-real-derivation.md`). `method_tag` is
not a function of `method_index`, method name, signature, or RID; it must
be captured empirically from a real Unity-to-Unity pcap per compiled
assembly.

The risk is not only collisions between correctly-derived tags (as
originally framed) — it's that there is no correct derivation at all.
Per distance-server's dispatch-matrix testing, a real Unity client can
silently misdispatch a first-use RPC to a different method that shares its
tag (observed: `RPC_BROADCAST_ALL` and `RPC_TARGETED` both tag 8, causing
`RPC_BROADCAST_ALL` sends to route to `ReceiveTargetedEventServerToClient`
instead). Our own single-variable capture test found that a wrong tag can
also cause outright rejection (`Internal RPC error. Invalid RPC index,
function not registered.`) rather than misdispatch. The exact caching/slot
mechanism on the Unity side is not confirmed in either case.

`registerMethodTag`/`registerMethodTags` — removed by
`docs/plans/method-tag-collision-guard.md` on the (now-disproven) reasoning
that a correct tag could always be derived from a registered index — have
been reinstated by `docs/plans/method-tag-real-derivation-fix.md`. They are
now the *only* correct way to supply a tag for a game-specific method not
already in the hardcoded Loader-assembly ground-truth table. The library
still warns when a method is sent first-use more than once to the same
peer, which remains valid and unaffected by this correction — that
mechanism doesn't depend on the tag formula being right, only on whether an
index was ever learned.
**Workaround:** register real captured tags via `registerMethodTag`/
`registerMethodTags` (Python: `register_method_tag`/`register_method_tags`)
for any game-specific method that will be sent first-use to a real Unity
client. Registering the method's index alone (via
`scripts/extract-method-indices.sh`) is necessary for subsequent-use
encoding but does **not** supply a correct tag — the two are independent.

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

### 4. subsequent-use RPC header width above method_index 132 is unconfirmed

§3.2's extended header (4 bits wider, extension flag at bit 89) is
confirmed correct for method_index 128–140 via a real-Unity-client sweep
(`scripts/index-sweep-server.py`, 2026-07-12/13: `NetworkViewID`=128,
`Alpha`=132, `Beta`=136, `Gamma`=140 all dispatch cleanly with zero `Not
enough data to read` errors). Only index 132 (`Alpha`) has independent
confirmation from a genuine real-Unity-to-real-Unity capture
(`MethodIndexU2U-20260627-145136`); 128/136/140 rely on our own encoder
producing wire bytes the real client accepts, not a second independent
capture. It is unknown whether the header widens further for larger
indices (e.g. >= 256) or whether the +4-bit widening is a fixed constant
for the whole 128–255 range. **Workaround:** not needed in practice —
distance-server's shipped game has only 7 total `[RPC]`-attributed
methods, far under 128 (see
`docs/research/2026-07-11-unity-vs-distance-rpc-model.md`). Revisit only
if a target game's real dispatch table exceeds ~128 entries.

### 5. RPC Batch Index (`0x07`) reply is not usable for subsequent-use encoding from a non-Unity sender

`docs/research/unity-legacy-networking-wire-format.md` §3.2.1 documents
the batch index protocol as "sender uses the receiver's registered
index" — confirmed true for real-Unity-to-real-Unity traffic, but **not**
confirmed, and now empirically disproven, for a non-Unity sender (this
repo's Python server) talking to a real Unity client. Tested for all 13
Loader `[RPC]` methods (`captures/IndexSweep-20260712-235647-*`): the real
client's own `0x07` reply matched its own real dispatch slot in 0 of 13
cases. Using the reported value for subsequent-use encoding reliably
produces a silent non-dispatch or a misdispatch to an unrelated method
(`docs/research/2026-07-13-subsequent-use-static-index-dispatch.md`, from
`docs/plans/method-tag-collision-repro.md` scenarios S2-S4 and S8).

Also corrects `2026-06-27-method-index-investigation.md`'s "Python
wrong-index experiment": a wrong index that happens to land on a real
method's slot is silently misdispatched with garbage-but-well-typed
parameters, not rejected — only indices with no corresponding real slot
produce an explicit `Internal RPC error`.

**Workaround:** `protocol/unity_server.py`'s `_send_rpc_to` currently uses
`_peer_indices` (the reported value) for subsequent-use encoding — this is
a known production-code correctness gap. `scripts/index-sweep-server.py`
demonstrates the fix (compute the static per-method index directly and
use that instead), but implementing it in the shipped server is deferred
to a follow-on plan through the full CLAUDE.md pipeline, not done here.
Until fixed, a caller can avoid the bug entirely by never relying on
subsequent-use for methods it didn't itself compute the index for — i.e.
always sending first-use (see §3.2.1's "non-Unity implementation that
always sends first-use" fallback), at the cost of ~20 extra bytes per RPC.

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
| Master Server | Yes (registration) | Implemented in Python + TS (M15), cross-language tested | No |
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

**Remaining gap:** None. Master Server implemented in M15 (Python + TS,
cross-language conformance tested). Full wire format spec at
`docs/research/master-server-wire-format.md`.
