# Plan: Large-delta cross-assembly test for subsequent-use index dispatch

Date: 2026-07-13

## Erratum (2026-07-13, second pass)

The Background below (and the `crossbinary-manual-decode-was-wrong.md`
finding it was built on) is **inverted**. `decode_batch_index` itself was
the broken component — wrong bit layout, not a wrong theory about 0x07.
Once fixed, 0x07 decodes to exactly the announcer's own real static
dispatch index (verified 9/9 end-aligned against `IndexSweep-...-235647`'s
known-ground-truth indices, and independently against `CrossBinary`'s
known +12 build delta — see corrected readout below). The "0x07 is
method-name-keyed, not build-keyed, and not a usable dispatch index" claim
was the parser bug observing itself: three "independent" re-checks were
three runs of the same broken parser, not three confirmations.

Beyond fixing the decoder, a direction-resolved re-read of
`CrossBinary-20260628-004945.pcap` (server=port 7777, client=port 41182)
settles the previously-open "adopt vs. own-static-sender" semantic
question:

| method | who announces (0x07) | value | who later sends SU using that value | direction |
|---|---|---|---|---|
| RPC_Int | client→server | 96 | server→**client** | client (the announcer) is the SU *destination* |
| RPC_Int | server→client | 108 | client→**server** | server (the announcer) is the SU *destination* |
| RPC_Float | client→server | 100 | server→client | same pattern |
| RPC_Float | server→client | 112 | client→server | same pattern |
| RPC_String | client→server | 104 | server→client | same pattern |
| RPC_String | server→client | 116 | client→server | same pattern |
| RPC_Alpha (≥128) | client→server | 132 | server→client | same pattern |

In every row, the endpoint that announces an index later *receives*
subsequent-use traffic at that index — it never *sends* at its own
announced value. That is **adoption**, not own-static-sender: the sender
of a subsequent-use RPC always encodes it using the value the *receiver*
previously announced for that method; the receiver always decodes inbound
subsequent-use by looking up the index *it itself* previously announced.
This is real-Unity-to-real-Unity behavior (both `CrossBinary` endpoints
are real Unity builds), not an artifact of either language implementation.

This also means the pre-existing `_peer_indices` (Python
`unity_server.py`) / `peerIndices` (`ts/src/unity/server.ts`) design —
learn the peer's announced index, use it for outbound sends to that peer
— was already the correct recipe for the *outbound* half. The remaining
gap, found independently this session, is on the *inbound decode* half:
Python's `decode_rpc` resolves a subsequent-use `method_name` from a
single shared global (`INDEX_TO_METHOD`) rather than each instance's own
previously-self-announced index first, which is exactly wrong under the
now-confirmed adoption semantics and causes cross-connection
misdispatch when two instances in one process announce different indices
for the same method (see `docs/plans/global-index-table-cross-connection-leak.md`).

**Corrected conclusion carried into this plan:** 0x07, correctly decoded,
*is* a real, usable dispatch index, and the operative recipe — adopt the
peer's announced index for outbound; decode inbound via one's own
previously-announced index, never a cross-instance-shared table — is
already right in design and needs a scoped Python fix, not a redesign.
This plan's job changes from "stress-test the decoupled model to see if
it survives" to "stress-test the fixed parser + adoption recipe at a
scale where the original small, uniform +12 delta could have hidden a
narrower bug (e.g. one that only shows up with non-uniform per-method
deltas, or well past the ≥128 boundary)."

## Background (superseded — kept for record, see Erratum above)

The user asked whether the pre-07-12 "both sides learn the subsequent-use
index via msg_id 0x07" model might actually have been correct all along,
with some other bug misattributed to it — since this investigation saw
dispatch problems in both first-use (method-tag collisions,
`docs/research/2026-07-12-method-tag-real-derivation.md`) and
subsequent-use (index dispatch,
`docs/research/2026-07-13-subsequent-use-static-index-dispatch.md`) at
various points, and the "decoupled" model that superseded the learning
model was itself established under confounded conditions (see
`[[batch-index-protocol]]` memory, "REVISED 2026-07-12").

A transcript-archaeology pass (general-purpose agent, see conversation)
catalogued every experiment and belief-revision in the investigation.
Its central finding: the strongest evidence *for* the learning model
(`CrossBinary-20260628-004945.pcap`, a two-build +12-static-index-shift
test) had never been re-verified against the current, code-accurate 0x07
decoder — the original 2026-06-28 analysis read it by hand.

Re-decoding it bit-correctly (`protocol/unity_protocol.py:decode_batch_index`,
current post-881f335 code) settled the question — **this reasoning was
itself wrong; see Erratum above; kept verbatim for the record only:**
`docs/research/2026-07-13-crossbinary-manual-decode-was-wrong.md`. 0x07
does not match either side's real subsequent-use index for any of 4
methods tested; the real subsequent-use indices correctly reproduce the
known +12 build delta, and 0x07 doesn't. The original "it matches!" read
was very likely a manual misread of the frame's non-byte-aligned trailing
bits. Re-checking two more real single-build U2U captures
(RpcMultiParamExperiment, both RpcModeOthersRelay sessions) with the same
decoder reinforces this: RPC_Int's and RPC_IntFloatString's 0x07 value is
consistently 88 across at least 4 different real builds/sessions, while
their real static index varies (96/108/84/120) — 0x07 tracks *something*
deterministic (looks method-name-hash-keyed, not build-keyed) but is not
a usable dispatch index by any read attempted so far.

**Conclusion carried into this plan (superseded, see Erratum above):** the
"decoupled" / static-per-build-index model is correct. Re-deriving or
reviving 0x07-based learning is a dead end; per `CLAUDE.md`'s existing
guidance, per-build empirical extraction (Cecil) or genuine runtime
learning via *some other*, still undiscovered mechanism remain the only
paths — and this plan does not chase the latter (0x07 is ruled out twice
now; there is no known candidate replacement message to chase).

### A relevant discovery about the real-world stakes

A separate Explore pass on `/home/server-mint/distance-server` found that
Distance's actual "dedicated server" is not a genuinely different
compiled assembly: the reference server's patcher renames
`Assembly-CSharp.dll` to `Distance.dll` unmodified (sha256-verified
byte-identical to the real client's assembly,
`distance-server/reference-server-diff/README.md`), and loads it
alongside a separate plugin-host assembly (`ServerBase`) that adds *zero*
`[RPC]`-attributed methods of its own (grep-confirmed, this session).
So Distance's real client and "server" share one static index table —
task #15's actual fix is to extract that one table via Cecil and use it
directly, not to solve a general two-differing-assemblies bridge at
runtime.

That lowers the urgency of cross-assembly testing for fixing Distance's
bug specifically, but does **not** remove the reason to do it: per
`CLAUDE.md`'s standing convention (added this session), this
investigation should keep testing with two genuinely different
assemblies precisely because a same-build or small-delta test can hide
bugs that only surface once two real per-build tables have diverged for
real reasons. The existing CrossBinary test's +12 delta (3 extra `[RPC]`
methods) is a token delta — smaller than a real differently-versioned
game client/server pairing would likely produce, and small enough that
several of the observed misdispatches landed on adjacent, easily-
recognizable methods (e.g. index+4 or index+8 away), which may have made
some past readings easier to get right by luck than a larger, messier
delta would allow. This plan's job is to stress-test the current model at
a scale where "getting lucky" is no longer available.

## What this plan builds

**Prerequisite (do first, cheap, may reshape scope below):** confirm the
fixed `decode_batch_index` against known-index frames before building
anything on top of it (already done this session for `IndexSweep-...-235647`
sub-128/extended fixtures and `CrossBinary`'s +12 delta — see Erratum
above) — a fresh large-delta capture run through a still-broken parser
would produce nothing.

1. **A configurable-delta assembly patcher.** Generalize
   `scripts/patch-assembly-shift-indices.cs` (currently hardcodes 3 extra
   `[RPC]` classes for a fixed +12 shift) to accept a parameter for how
   many synthetic `[RPC]` methods to inject, so the delta can be dialed
   up arbitrarily (target: at least +80, i.e. 20+ extra methods — an
   order of magnitude past the existing +12 test — plus a second run at
   an even larger delta, e.g. +200, if the first run is clean, to see if
   anything changes qualitatively as indices grow well past the observed
   ≥128-header boundary and into un-exercised territory). **Make the
   delta non-uniform**, not a bigger uniform shift: interleave injected
   `[RPC]` classes/methods before, between, and after the existing ones
   so different methods shift by different amounts. A uniform shift has
   the same which-build-is-which ambiguity as the original +12 test —
   values alone can't distinguish adoption from own-static without the
   direction-resolved src/dst read this plan's Erratum already did by
   hand for +12. Non-uniform deltas make every per-method observation
   individually diagnostic at scale, and match `CLAUDE.md`'s convention
   more literally (different sets/ordering, not just a shift).

2. **A combined first-use + subsequent-use test harness**, extending the
   existing `TagCollisionExperiment.cs` / `CrossBinaryIndexExperiment.cs`
   pattern rather than replacing it: two real Unity builds (baseline +
   large-delta-patched), each side sending a mix of first-use RPCs
   (including some with tag collisions at the new, larger table) and
   subsequent-use RPCs. For each side's subsequent-use sends, use the
   confirmed **adoption recipe**: send at the value the *peer* announced
   via 0x07 for that method (not a value computed from one's own
   Cecil-extracted table) — this is what real Unity itself does per the
   Erratum's direction-resolved table, and is what `_peer_indices` /
   `peerIndices` already implement. Cecil-extracted per-build tables
   (`scripts/extract-method-indices.cs`) remain the ground truth for
   *verifying* the decode-and-verify pass below, not for computing what
   to send — per `CLAUDE.md`'s "do not re-derive the formula" guidance,
   this still never touches the unsolved formula itself. This directly
   tests both problem areas the user flagged (first-use and
   subsequent-use) in the same genuinely-cross-assembly session, so any
   shared root cause would show up in both at once rather than needing
   two separate experiments correlated after the fact.

3. **A decode-and-verify pass** using the current `decode_pcap.py` /
   `decode_batch_index` on the resulting captures, checking:
   - Do all first-use RPCs dispatch correctly regardless of tag
     collisions at the larger table size (extending S1-S8's finding)?
   - For every method, does the **decisive readout** the Erratum
     establishes still hold at scale: (a) each side's 0x07 tail value
     equals its own Cecil-extracted index (parser + announcement model),
     and (b) each side's real subsequent-use wire index equals the
     *peer's* announced value, not its own (adoption, not own-static)?
     With non-uniform deltas these two checks are unambiguous per-method
     instead of relying on one hand-read direction table.
   - Does the Beta/Gamma-style "node not in map" gap reappear at the
     new, larger table's analogous higher slots, or was that specific to
     the original build's slot layout? (Note: Beta/Gamma's contradiction
     — client announces 136/140 cleanly via 0x07, yet dispatch at
     SU@136/140 hits "node not in map" — is a real, still-open item,
     *not* resolved by the parser fix; see corrected
     `docs/research/2026-07-13-subsequent-use-static-index-dispatch.md`.)
   - Fit the ≥128 extended-tail encoding across a much wider range of
     real index values than the 4 frames (128/132/136/140) available so
     far — check whether the "1 leading noise bit + top-bit-of-tail-byte
     noise" seen in the <128 case is actually a constant extension flag
     that also governs the ≥128 case (i.e. one variable-width field, not
     two separate encodings) by seeing whether one of those "noise" bits
     flips exactly at the <128/≥128 boundary across many more indices.

4. **Optional, cheap, decisive follow-up: the "lied index" experiment.**
   Once our own encoder announces a deliberate false index for a method
   to a real Unity client (e.g. "my index for RPC_Int = 48", a slot
   confirmed empty by `WrongIndex`), then sends subsequent-use at 48:
   if the client dispatches RPC_Int correctly, that proves the client's
   *decode* path genuinely prioritizes a learned announcement over any
   static/own-table fallback (stronger than what CrossBinary alone shows,
   since there both sides always announced their *true* index — this
   can't distinguish "receiver decodes via learned map" from "receiver
   decodes via its own real static table, which happens to equal what it
   announced"). If the client fails to dispatch or errors, adoption still
   holds for honest announcements but the receiver's decode path is using
   its own table, with 0x07 only ever informationally true. Either result
   is useful and this validates the new encoder against a real consumer,
   which the `unity_server.py`/`unity_client.py` fix
   (`docs/plans/global-index-table-cross-connection-leak.md`) needs
   validated against a real peer anyway.

## Exit criteria

- Doc-correction pass (see "Prerequisite" and Erratum above) landed
  first: `docs/research/2026-07-13-crossbinary-manual-decode-was-wrong.md`
  retracted, `CLAUDE.md`'s "do not revive 0x07" paragraph corrected,
  `docs/research/2026-07-13-subsequent-use-static-index-dispatch.md`'s
  0x07 column and "red herring"/"production code gap" conclusions
  corrected (its "real dispatch index" table and Beta/Gamma open item are
  NOT changed), `docs/research/spec-status.md` Known Issue #5 updated,
  `docs/research/unity-legacy-networking-wire-format.md` §3.2.1/§3.8.1
  updated. Merging this plan's experiment while those docs assert the
  inverted model guarantees future confusion.
- Configurable-delta, non-uniform patcher merged and documented (replaces
  or extends `patch-assembly-shift-indices.cs`).
- At least one experiment run at delta ≥ +80 (non-uniform) with both
  first-use (including collisions) and subsequent-use RPCs exchanged in
  the same session between two genuinely different, independently-
  extracted-index builds.
- Every outcome read positionally against the send log (per the
  established "never diagnose silence by name-grep" methodology lesson),
  with raw log lines quoted for anything non-obvious.
- Adopt-vs-translate re-confirmed at scale (not just re-asserted from the
  +12 case) via the decisive per-method readout in item 3 above.
- ≥128 extended-tail encoding fitted across the wider index range, or
  explicitly bounded if it can't be fully resolved.
- A findings doc (`docs/research/2026-07-13-large-delta-cross-assembly-
  test.md` or later date if this slips) stating plainly whether the
  adoption model and fixed parser hold at this scale, and documenting any
  new anomaly (positively or negatively) with the same rigor as this
  session's CrossBinary re-decode.
- `[[batch-index-protocol]]` memory and `docs/research/spec-status.md`
  updated to reflect the outcome (memory already rewritten this session
  per `tag-collision-fable-design`; confirm it stays current after this
  plan's results land).
- Task #15 updated to reflect the corrected framing (Distance-specific
  fix = use the one real extracted table directly; general cross-
  assembly dispatch = the adoption recipe, already implemented for
  outbound via `_peer_indices`/`peerIndices`, fixed for inbound via
  `docs/plans/global-index-table-cross-connection-leak.md`) or closed if
  this plan's results settle it.

## Explicitly out of scope

- Re-deriving the static index formula from scratch (`CLAUDE.md`
  guidance — per-build empirical extraction only).
- Rebuilding distance-server's actual bug reproduction — that belongs to
  the distance-server project; this plan is about this repo's own
  library-level correctness under large assembly divergence.
