# `decode_batch_index` had the wrong bit layout; 0x07 is a real, usable dispatch index

## Summary

Every prior conclusion that msg_id `0x07` ("RPC Batch Index") is inert,
method-name-keyed noise, or otherwise not a usable subsequent-use dispatch
index was built on a decoder bug, not a real protocol property. The bug is
fixed (`protocol/unity_protocol.py:decode_batch_index`/`encode_batch_index`,
mirrored in `ts/src/unity/rpc.ts`). Corrected:

- **0x07 carries the announcer's own real static dispatch index** for the
  method named in the frame, byte-exact against every known-ground-truth
  capture checked (see Verification below).
- **Real Unity uses an adoption recipe for subsequent-use dispatch**: the
  sender of a subsequent-use RPC always encodes it using the index the
  *receiver* previously announced via 0x07 for that method; the receiver
  always decodes inbound subsequent-use by looking up the index *it
  itself* previously announced — never a value it computed independently
  or adopted from someone else's announcement. This is direction-resolved
  from real Unity-to-Unity traffic (`CrossBinary-20260628-004945.pcap`),
  not inferred.

## The bug

Old `decode_batch_index` read a 5-bit field starting immediately after
`class_guid + method_hash`, with no offset, then left-shifted by 2
(`<<2`) to get the index. This is wrong on two counts: there is no
separate 5-bit-then-shift field, and the read starts one bit too early
(landing on the tail end of the length/hash region instead of the actual
index field).

The correct layout: `msg_id(8) + length_field(31, no separate flag bit)
+ class_guid(48) + method_hash(variable, hash_bytes = length*4/8 - 6) +
method_index(9 or 17 bits, depending on total frame length)`. Recovered
from the frame's trailing bits:

- If 9 bits remain after the hash: `method_index = payload[-1] & 0x7F`
  (values 0-127; the top bit of that byte plus the leading bit of the
  9-bit field are unused/noise, not part of the index).
- If 17 bits remain: `method_index = 128 + ((payload[-1] >> 6) & 0x3) * 4`
  (values 128, 132, 136, 140 — the only ones directly observed; the full
  width of this extended field for larger deltas is still open, see
  `docs/plans/large-delta-cross-assembly-index-test.md`).

## Verification

1. **`IndexSweep-...-235647.pcap`**, 9 sub-128 frames with independently
   known ground-truth indices (RPC_Void=92 ... RPC_NetworkPlayer=124,
   obtained by direct index-forcing / positional log reads, no decoder in
   the loop): fixed decoder matches all 9 exactly.
2. **Same capture, 4 extended (≥128) frames** (RPC_NetworkViewID=128
   through RPC_Gamma=140): fixed decoder matches all 4 exactly.
3. **`CrossBinary-20260628-004945.pcap`**, two real Unity builds with a
   known +12 static-index shift: fixed decoder gives 96/108 (RPC_Int),
   100/112 (RPC_Float), 104/116 (RPC_String) — each side announcing its
   own build's real index, exactly +12 apart, for all 3 methods.
4. **Cross-language conformance**: Python and TS encoders produce
   byte-identical output for the same (method, index) pairs, independently
   verified via a standalone `npx tsx` script (not circular self-checks).
5. **Provenance of the disputed prior claim**: reconstructing the *old*
   buggy formula exactly and running it against the 13 real frames in
   `docs/research/2026-07-13-subsequent-use-static-index-dispatch.md`
   reproduces that document's disputed "0x07-reported index" column
   13/13 — proving that column was the same bug observed at more data
   points, not independent falsifying evidence.

## The adoption model (direction-resolved)

Re-reading `CrossBinary-20260628-004945.pcap` by src/dst port
(server=7777, client=41182) with the fixed decoder:

| method | announcer (0x07 direction) | announced value | later SU sender | SU destination |
|---|---|---|---|---|
| RPC_Int | client→server | 96 | server | client (= the announcer) |
| RPC_Int | server→client | 108 | client | server (= the announcer) |
| RPC_Float | client→server | 100 | server | client |
| RPC_Float | server→client | 112 | client | server |
| RPC_String | client→server | 104 | server | client |
| RPC_String | server→client | 116 | client | server |
| RPC_Alpha (≥128) | client→server | 132 | server | client |

In every row the endpoint that announces an index later *receives*
subsequent-use traffic at that index, never sends at it. That rules out
"own-static-sender" (each side always uses its own compiled index
regardless of peer) and confirms **adoption**: the sender uses whatever
the receiver told it to use.

Practical consequence: the pre-existing `_peer_indices` (Python
`unity_server.py`) / `peerIndices` (`ts/src/unity/server.ts`) design —
learn the peer's announced index, use it for *outbound* sends to that
peer — was already the correct recipe and needed no redesign, only the
codec fix. The remaining gap is on the *inbound decode* side in Python
only: `decode_rpc` resolves a subsequent-use `method_name` from a single
process-wide global (`INDEX_TO_METHOD`) instead of each instance's own
previously-self-announced index, which under the confirmed adoption
model is exactly backwards — see
`docs/plans/global-index-table-cross-connection-leak.md`.

## What remains open (not resolved by this fix)

- **Beta/Gamma contradiction** (from
  `2026-07-13-subsequent-use-static-index-dispatch.md`): the client
  cleanly announces 136/140 via 0x07 and dispatches first-use cleanly,
  yet our subsequent-use frames at 136/140 got "node not in map" in that
  sweep. 0x07 reports the announcer's static-table index correctly for
  all 13 methods in that sweep; it is verified-*dispatchable* for the 11
  slots ≤132. Whether that's our ≥128 SU encoding subtly differing from
  real Unity's (only 132 is real-frame-confirmed) or a genuine
  divergence between the client's announce table and its dispatch node
  map at those slots is still unknown.
- **The full ≥128 extended-tail width** beyond the 4 confirmed values
  (128/132/136/140) — a wider range needs a larger, non-uniform-delta
  capture to fit (see `docs/plans/large-delta-cross-assembly-index-test.md`).
- **Whether real Unity's inbound decode genuinely prioritizes a learned
  0x07 announcement over its own static table**, as opposed to always
  using its own static table with 0x07 being truthful-but-unused chatter
  — CrossBinary can't distinguish these since both sides always announce
  their *true* index. A "lied index" experiment (announce a false index,
  see if the peer still dispatches via it) would settle this; proposed as
  an optional follow-up in the large-delta plan.

## Stale documents corrected as a result

- `docs/research/2026-07-13-crossbinary-manual-decode-was-wrong.md` —
  retracted (its own "re-decode" was the same bug).
- `CLAUDE.md`'s "0x07 does not carry a usable dispatch index — do not
  revive" paragraph — corrected.
- `docs/research/2026-07-13-subsequent-use-static-index-dispatch.md` —
  its 0x07 column and "red herring"/"production code gap" conclusions
  corrected; its "real dispatch index" table and Beta/Gamma open item are
  unaffected and not changed.
- `docs/research/spec-status.md` Known Issue #5 — updated.
- `docs/research/unity-legacy-networking-wire-format.md` §3.2.1/§3.8.1 —
  updated to the correct bit layout.
- `docs/plans/large-delta-cross-assembly-index-test.md` — Background
  corrected via Erratum, plan scope updated to test the adoption recipe
  at scale rather than "stress the decoupled model."
- `[[batch-index-protocol]]` memory — already rewritten to this model.
