# Large-delta cross-assembly RPC index test: results

Findings for `docs/plans/large-delta-cross-assembly-index-test.md`. Two
independently-built Unity assemblies — an unmodified original and a copy
patched with `scripts/patch-assembly-shift-indices.cs`'s non-uniform
filler recipe — exchanged first-use and subsequent-use RPCs for all 13
real `Loader` `[RPC]` methods, at genuinely non-uniform, large real
Cecil-index deltas (ranging +8 to +92 across the 13 methods, not a
uniform shift). Capture: `captures/LargeDelta-20260713-031337.pcap` /
`-server.log` / `-client.log`. Ground truth: `/tmp/large-delta-orig-
indices.json`, `/tmp/large-delta-patched-indices.json` (Cecil-extracted).

## Real per-method index deltas used

| Method | Original (client) | Patched (server) | Delta |
|---|---|---|---|
| RPC_Void | 104 | 112 | +8 |
| RPC_Int | 108 | 120 | +12 |
| RPC_Float | 112 | 136 | +24 |
| RPC_String | 116 | 140 | +24 |
| RPC_Vector3 | 120 | 152 | +32 |
| RPC_Quaternion | 124 | 172 | +48 |
| RPC_Bytes | 128 | 176 | +48 |
| RPC_IntFloatString | 132 | 192 | +60 |
| RPC_NetworkPlayer | 136 | 200 | +64 |
| RPC_NetworkViewID | 140 | 224 | +84 |
| RPC_Alpha | 144 | 228 | +84 |
| RPC_Beta | 148 | 240 | +92 |
| RPC_Gamma | 152 | 244 | +92 |

This is the largest and first genuinely non-uniform delta tested — prior
tests (`CrossBinary-20260628-004945.pcap`) used a uniform +12 shift from
3 extra `[RPC]` classes, which cannot distinguish "adoption" from
"lucky small-delta alignment" the way a non-uniform, order-of-magnitude
delta can.

## Result 1: all 26 RPC exchanges dispatched correctly

Both sides sent all 13 methods first-use then subsequent-use (26 sends
each). Both logs show 26/26 `[RPC]` lines with zero errors and
`EXPERIMENT_DONE` on both sides. No "node not in map", no parameter
mismatch, no silent drop, at any of the delta magnitudes above.

**This directly answers the plan's open question about the `RPC_Beta`/
`RPC_Gamma` "node not in map" gap** documented in
`docs/research/2026-07-13-subsequent-use-static-index-dispatch.md`: it
did **not** reproduce here, even though this test pushed `RPC_Beta`/
`RPC_Gamma` to much higher indices (148/240, 152/244) than the original
gap (136/140). That original test (`index-sweep-server.py`) forced a
raw Cecil-computed index directly for the subsequent-use send, bypassing
the real first-use → `0x07` announce → adopt-peer's-value sequence this
test used. The most likely explanation, consistent with Result 2 below
and with `CLAUDE.md`'s standing prohibition on re-deriving the static
index formula: the Cecil-computed index used in that earlier test wasn't
actually the value Unity itself would use for those two methods, so
forcing it directly landed on a bad slot for reasons unrelated to the
protocol's dispatch logic. This is **narrowed, not fully resolved** — the
gap is not a property of the adoption-based protocol procedure, but its
root cause in the earlier test is not chased further, per `CLAUDE.md`.

## Result 2: adoption model reconfirmed positionally at scale

Every subsequent-use RPC's wire `method_index` was checked positionally
(not by name-grep) against the value the *peer* had itself announced via
`0x07` for that method earlier in the same session. All 26 subsequent-use
sends (13 per direction) matched adoption, not own-static-index, across
the full +8 to +92 delta range. The adoption recipe —
"sender encodes using the value the *receiver* previously announced;
receiver decodes inbound using the index *it itself* previously
announced" — holds robustly under real, large, non-uniform per-method
deltas between two genuinely different assemblies.

## Result 3: `>=128` batch-index tail is a 5-bit non-contiguous quotient, not 2-bit

The prior fix (`docs/research/2026-07-13-batch-index-decoder-was-broken.md`)
only had 4 real `>=128` frames to fit against (128/132/136/140 — quotient
values 0-3), which a 2-bit field fits by coincidence. This test's wider
range of real announced indices (128 through 244) falsified that: several
frames needed a quotient > 3 and did not decode correctly under the old
2-bit formula.

The corrected 17-bit tail layout (bit positions 0-indexed from the start
of the tail, MSB-first):

| Position | Meaning |
|---|---|
| 0-4 | unconfirmed/padding, always 0 in real frames |
| 5 | quotient bit 4 (weight 16) |
| 6 | constant flag, always 1 (semantics unknown) |
| 7 | quotient bit 3 (weight 8) |
| 8 | quotient bit 2 (weight 4) |
| 9 | quotient bit 1 (weight 2) |
| 10 | quotient bit 0 (weight 1) |
| 11-16 | padding, always 0 |

`method_index = 128 + quotient * 4`, where `quotient = (method_index -
128) / 4`, range 0-31 (representable index range 128-252). Verified
against 12 real distinct captured frames (method_index 128 through 232,
`RPC_NetworkViewID`/`Alpha`/`Beta`/`Gamma`/`String`/`Vector3`/
`Quaternion`/`Bytes`/`IntFloatString`/`NetworkPlayer` at various slots)
plus round-trip encode→decode for all 12. Implemented and tested in both
`protocol/unity_protocol.py` (`encode_batch_index`/`decode_batch_index`)
and `ts/src/unity/rpc.ts` (`encodeBatchIndex`/`decodeBatchIndex`).

The sub-128 tail encoding (9 bits: 1 leading bit + 8-bit byte, low 7 bits
= index directly) is unchanged.

## Result 4 (new anomaly, documented not chased): a constant "-12" offset between the wire-announced index and the Cecil-extractor's output

While checking the plan's decisive readout (a) — "each side's `0x07` tail
value equals its own Cecil-extracted index" — this held for *relative*
consistency (adoption direction, Result 2) but **failed as a literal
numeric equality claim**: the *same* client build (original, unmodified
`Player.x86_64`) announced `RPC_Int=96`, `RPC_Float=100`, `RPC_String=104`
via `0x07`, in both this capture and the older
`CrossBinary-20260628-004945.pcap`, while `scripts/extract-method-
indices.cs` (Cecil-based) computes `108`, `112`, `116` for that same
build's assembly — a constant offset of exactly **-12** (3 method-slots
× 4), reproducible across both captures and both builds tested (original
and patched — same relative -12, despite the wildly different real
deltas between the two builds' own tables).

This is **not** a decoder bug: the fixed decoder correctly extracts
whatever real Unity puts on the wire (confirmed by the 26/26 dispatch
success and the golden-frame tests). The discrepancy is between that
correctly-decoded wire value and a *separate tool's* (the Cecil
extractor's) computed index for the same method in the same assembly.
Per `CLAUDE.md`'s standing convention ("the `base_offset` term has a
known counterexample and no general formula was found... treat
re-deriving the formula as an absolute last resort"), this is flagged as
a bounded, reproducible finding rather than chased to a root cause. It is
plausibly the same class of issue as that known `base_offset`
counterexample from `docs/research/2026-06-27-method-index-
investigation.md`, but that connection is not verified here.

**Practical implication:** none for the adoption-based dispatch recipe
itself (Result 2 shows adoption is self-consistent regardless of this
offset, since both sides always use each other's *announced* value, never
a Cecil-computed one). It matters only for tooling/tests that assume the
Cecil extractor's output equals the real wire-announced index for a given
build without cross-checking — that assumption should not be made without
verification against a real capture.

## Exit criteria status

- [x] Configurable non-uniform-delta patcher (`scripts/patch-assembly-
      shift-indices.cs`) — done, used to produce the +8..+92 deltas above.
- [x] At least one experiment at delta >= +80 non-uniform, both first-use
      (including collisions, inherited from the existing method-tag-
      collision test suite) and subsequent-use exchanged between two
      independently-extracted-index builds — done (up to +92).
- [x] Every outcome read positionally against the send log, not by
      name-grep.
- [x] Adoption re-confirmed at scale (Result 2).
- [x] `>=128` extended-tail encoding fitted across the wider range
      (Result 3) — now confirmed 128-252, was 128-140.
- [x] This findings doc.
- [x] `[[batch-index-protocol]]` memory and `docs/research/spec-status.md`
      update — see those files' own edits alongside this doc.
- [~] Task #15 framing — unaffected by this test; the adoption recipe was
      already correctly designed for outbound (`_peer_indices`/
      `peerIndices`); the inbound-decode leak fix
      (`docs/plans/global-index-table-cross-connection-leak.md`) remains
      the actual remaining work, tracked separately (task #28).

## Out of scope, not attempted

- Root-causing the -12 offset (Result 4) or the original Beta/Gamma
  IndexSweep gap (Result 1) beyond the narrowing above — both would
  require re-deriving or probing the static index formula, which
  `CLAUDE.md` treats as a last resort.
- The plan's optional item 4 ("lied index" experiment) — not run this
  session; would need a dedicated follow-up if still desired.
