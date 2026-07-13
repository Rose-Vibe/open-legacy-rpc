# method_index >= 128 ceiling: subsequent-use RPC header is 4 bits wider, not truncated

Follow-up to `docs/research/2026-06-27-method-index-investigation.md` and
the S2 anomaly in `docs/plans/method-tag-collision-repro.md`. Resolves
task "Resolve 7-bit method_index ceiling question."

## Summary

The subsequent-use RPC wire format (`unity_protocol.py`'s
`encode_rpc_subsequent`/`decode_rpc`) previously encoded `method_index`
as a fixed 7-bit field followed by 16 always-zero "reserved" bits. This
works for `method_index < 128`. For `method_index >= 128`, the real
format is **4 bits wider**: an extension flag at bit 89 (relative to the
frame start) is set, the reserved span grows from 16 to 20 bits, and
every field downstream (`remaining_bit_count`, `user_rpc_constant`,
`RPCMode`, parameters) shifts out by 4 bits. `remaining_bit_count`'s
formula changes from `total_bits - 121` to `total_bits - 125`
accordingly.

This was previously misdiagnosed as a simple dropped/misplaced bit (a
7-bit field silently truncating index >> 7). That first fix was
implemented, passed its own round-trip test, and then was proven wrong by
re-running the real-Unity-client sweep: identical failures before and
after. The header-width difference was only found by comparing two real
captured frames field-by-field at fixed bit offsets.

## Evidence

### The static index table (background)

For the current experiment build (`TagCollisionExperiment` /
`IndexSweep`), Unity's real per-method dispatch index follows
`shifted_index = 80 + (RID-28)*4 + 12`, confirmed for 9/9 low-index
methods in the prior session's sweep. Four methods in the Loader test
assembly land at or above 128: `NetworkViewID`=128, `Alpha`=132,
`Beta`=136, `Gamma`=140.

### The real-capture anomaly

`captures/MethodIndexU2U-20260627-145136-*` is a genuine real-Unity-
client-to-real-Unity-server capture (no Python driver in the loop),
sending `RPC_Int`/`RPC_Float`/`RPC_String`/`RPC_Alpha` twice each,
client→server. `RPC_Alpha`'s second (subsequent-use) send used wire index
4 with what looked like a "reserved" field of `0x4000` — nonzero, where
every other captured subsequent-use frame had `reserved = 0x0000`. The
real server dispatched it cleanly: `[RPC] RPC_Alpha(43) from 1`, no
error. Our own sweep, sending computed index 132 (low7=4, matching) via
the then-current fixed 7-bit encoding, got an explicit
`Internal RPC error. Not enough data to read.` — a direct contradiction.

### First (wrong) fix: relocate one bit

Read as `0100000000000000`, the nonzero reserved field's leading `1`
looked like it was at bit 88 (the field's first bit) — implying
`method_index`'s bit 7 (value 128) had been silently dropped by the
encoder's `write_bits(method_index, 7)` call. The fix relocated that bit
to sit immediately after the 7-bit low field, keeping total frame width
unchanged (1 flag + 7 low bits + 1 relocated bit + 15 padding = same 24
bits as before). It passed a self-consistent round-trip test. Re-running
`scripts/run-index-sweep.sh` against the real Unity client afterward
produced **identical failures** to the pre-fix run — same four methods,
same two error types, unchanged. The encoder's wire bytes were verified
(via direct pcap decode of the re-run) to now carry `full=128/132/136/140`
correctly — so the change was taking effect, it just wasn't the change
the real Unity decoder cares about.

### Second (correct) fix: the header is 4 bits wider

Careful re-reading of the same real capture showed the nonzero bit was
actually the **second** bit of the reserved span (bit 89), not the
first (bit 88):

```
int_su   (low index, correct at every fixed offset):
  bit 88: 0   bit 89: 0

alpha_su (high index, real capture, dispatched cleanly by real Unity):
  bit 88: 0   bit 89: 1
```

Comparing `int_su` (index 96, correctly decoding under the original
fixed-offset model: `reserved=0x0000`, `remaining_bit_count=51` matching
`172-121`, `target_view=0x0002`, `mode=0=Server`) against `alpha_su`
(index 132) at those *same* fixed offsets produced nonsense
(`remaining_bit_count` reads as 3, not the expected `176-121=55`).
Shifting every field downstream of bit 89 out by 4 bits — i.e.
hypothesizing a 20-bit reserved span (bits 88–107) instead of 16 —
resolved this cleanly:

- `remaining_bit_count` (bits 108–123): 51 — internally consistent (see
  note below on why this numerically matches `int_su`'s value despite a
  longer frame)
- `target_view` (bits 124–139): `0x0002` — the known routing constant
- `RPCMode` (bits 140–143): `0` = Server — exactly matching the real C#
  source's explicit `RPCMode.Server` call (and correcting an earlier
  `decode_pcap.py` misreading of this frame as `RPCMode.All` under the
  old fixed-offset model)
- final parameter (bits 144–175, 32 bits): decodes to exactly `43` —
  matching the real sent value `RPC_Alpha(43)`

Three independently-checkable fields (routing constant, RPC mode, and
the actual parameter value) all land correctly under the 4-bit-wider
hypothesis and none of them do under the fixed-width model. This is
strong evidence, not a coincidence.

Note: `alpha_su`'s `remaining_bit_count` (51) numerically equals
`int_su`'s (51) despite `alpha_su`'s frame being 4 bits longer overall —
this checks out because `remaining_bit_count` is computed relative to a
formula that itself accounts for the header width (`total_bits - 125` vs
`total_bits - 121`), and both frames carry the same single-`int`
parameter payload, so the *remaining* bits after the (now-correctly-
located) `remaining_bit_count` field are identical between the two.

## The fix

`protocol/unity_protocol.py`:

- `encode_rpc_subsequent`: when `method_index >= 128`, write bit 88 as
  `0`, bit 89 as `1` (extension flag), then 18 more zero bits (20-bit
  reserved span total, vs 16 for `method_index < 128`). `total_bits` and
  the `remaining_bit_count` formula both add 4 in this case.
- `decode_rpc`: read the low 7 bits at bits 81–87, peek bit 89 for the
  extension flag, and offset every subsequent fixed-position read
  (`target_view`, `RPCMode`) by 4 bits when the flag is set. The decoded
  `method_index` is now also stored on the result dict (previously only
  `method_name` was), so downstream consumers don't need to re-derive it
  from raw bytes.

`tools/decode_pcap.py`: both the main RPC decode path and the
`_partial_rpc` best-effort fallback updated to read the extension flag
at bit 89 (not 88), and `_rpc_remaining_hex`'s `mode_start` offset now
accounts for the same 4-bit shift. The main decode path now reuses
`decode_rpc`'s `method_index` instead of independently re-deriving it
from raw payload bytes, removing a duplicate (and previously
subtly-wrong) computation.

## Verification

**Round-trip**, encoding and decoding `method_index` values 96, 128, 132,
136, 140, and 255 directly against `BitStream` positions (bypassing
`decode_rpc`'s method-name/signature lookup, which has a known,
unrelated cosmetic bug — see below): all values round-trip correctly,
`remaining_bit_count` matches the expected formula in both the narrow and
extended cases, and the encoded `Alpha`(132) frame is exactly 22 bytes /
176 bits — matching the real captured frame's length exactly.

**Real-Unity-client sweep** (`scripts/run-index-sweep.sh`, all 13 Loader
RPC methods + 1 negative control, forcing each method's real static
index via the established `server._peer_indices` injection technique):
before this fix, 4 methods failed with 2 distinct error types (2×
`Not enough data to read`, 2× `Unable to retreive RPC node from map`).
After this fix: `NetworkViewID`(128) and all of `Alpha`(132)'s first and
second sends dispatch cleanly; `Beta`(136) and `Gamma`(140)'s first-use
sends dispatch cleanly. **Zero** `Not enough data to read` errors remain
anywhere in the sweep. Two errors remain — `Beta`/`Gamma`'s
*second* (subsequent-use) sends still fail, but with the *different*
error `Unable to retreive RPC node from map`, which is a dispatch-table
registration lookup failure, not a bit-width symptom. This is very
likely the same class of issue as the still-open "root-cause first-use
RPC dispatch failure for non-Void/Int methods" investigation, not part
of this ceiling question.

## Known limitation (not blocking)

Only `method_index = 132` (`RPC_Alpha`) has independent confirmation from
a genuine real-Unity-to-real-Unity capture. `128`/`136`/`140` are
confirmed only via our own encoder producing bytes the real client
accepts in the sweep — a strong signal, but not a second independent
capture. Whether the header widens further for indices beyond ~140 (e.g.
>= 256) is unknown and untested. This is very unlikely to matter in
practice: distance-server's entire shipped game has only 7 total
`[RPC]`-attributed methods (see
`docs/research/2026-07-11-unity-vs-distance-rpc-model.md`), far under
128. Revisit only if a target game's real dispatch table approaches that
size.

## Unrelated cosmetic bug noticed in passing

`INDEX_TO_METHOD` (in `unity_protocol.py`) reflects the *unshifted*
(original, RID-only) index assignments, not the shifted table the
current experiment build actually uses. Looking up a shifted index
(e.g. our computed 96 for `RPC_Int`) against this table can return the
wrong method name (unshifted-96 might be a different method with a
different parameter signature), which then makes `decode_rpc`'s
subsequent param decoding throw or silently misparse. This is a
pre-existing, display/labeling-only artifact — it does not affect wire
encoding correctness, and is unrelated to the header-width fix above. Not
fixed here; noted for whoever next touches `decode_pcap.py`'s method-name
labeling for shifted builds.
