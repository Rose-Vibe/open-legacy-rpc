# Subsequent-use RPC dispatch keys off a static per-method index, not the peer-reported 0x07 value

Findings write-up for `docs/plans/method-tag-collision-repro.md` (scenarios
S1-S8, run against the real headless Unity 2018.1.6f1 Linux player in the
`unitynet` netns). Corrects a claim in
`docs/research/2026-06-27-method-index-investigation.md` and adds a new
Known Issue to `docs/research/spec-status.md`.

**Erratum (2026-07-13, second pass):** every "silence" outcome originally
claimed below (S3's recovery send, S4's second `RPC_Int`/`RPC_Vector3`
sends, all of S8) was a misread of the client log. Each one actually
produced an explicit error line — the log just never names the *sent*
method, only the method occupying the slot that was hit, so grepping for
the sent method's name finds nothing and reads as silence. Read outcomes
positionally against the server's send log, not by name. Corrected
per-scenario below; no true silence case exists in this dataset. S4 also
turned up a new, real datum: slot 88 resolves to `DerivedRpc` (a method
that exists on a different NetworkView, not attached to `Loader`), which
is folded into the static-index table note. (Thanks to
`tag-collision-fable-design` for catching this by re-reading the raw
capture logs against the doc's claims.)

**Erratum (2026-07-13, third pass):** the "0x07 is a red herring" conclusion
below and the "Client's 0x07-reported index" column in the Evidence section
are wrong — traced to a bit-layout bug in `decode_batch_index` (fixed; see
`docs/research/2026-07-13-batch-index-decoder-was-broken.md`). Re-decoding
this same capture (`IndexSweep-20260712-235647`) with the fixed decoder
gives 92/96/100/104/108/112/116/120/124/128/132/136/140 for the 13 methods
in table order — **exactly matching the "Real dispatch index" column for
all 13**, not zero of 13. The old column's values (20, 88, 120, 24, 88,
92, 124, 60, 64, 32, 32, 32...) were the decoder bug's output on the same
raw frames, not the client's real announcement.

The corrected, precise statement (do not overstate this to "13/13 no
exceptions" — see caveat): **0x07 reports the announcer's real static
dispatch index for all 13 methods tested.** That index is
*verified-dispatchable* for the 11 slots ≤ 132 (confirmed by
`index-sweep-server.py` forcing those exact values and getting clean
dispatch, per the static index table above). For `RPC_Beta`/`RPC_Gamma`
(136/140), the announcement is still correct — it matches the Cecil-order
static table — but subsequent-use at those slots got "node not in map" in
this same sweep. That announce-vs-dispatch contradiction is real and
**remains open**, not resolved by this correction; see the Known Issue
section below, unchanged.

The specific numeric "0x07-reported index" values quoted throughout the
S1-S8 scenario write-ups below (e.g. 124, 120, 32, 48) are also decoder-bug
artifacts, not real client announcements — but the *experiments themselves*
and their *observed dispatch outcomes* are unaffected and still accurate:
our server really did send subsequent-use RPCs at those (wrong, buggy-
decoded) numeric slots, and the client really did respond as described
(clean dispatch to whatever real method occupied that slot, or an explicit
error). Read every occurrence of "0x07-reported index" or "peer-reported
index" below as "the numeric value our then-buggy decoder produced" (which
happened to coincidentally collide with other real slots), not as "the
client's true self-announced index" — those two were conflated before this
fix, and are not the same thing.

A direction-resolved re-read of a separate real Unity↔Unity capture
(`CrossBinary-20260628-004945.pcap`, see the decoder-was-broken doc above)
additionally confirms the *outbound* production-code recipe: real Unity
sends subsequent-use using the value the *receiver* announced (adoption),
which is exactly what `_peer_indices`/`peerIndices` already implement for
outbound sends. See the corrected "Production-code implication" section
below.

**Erratum (2026-07-13, fourth pass):** this doc's `RPC_Beta`/`RPC_Gamma`
"node not in map" gap (Known Issue, table below) did **not** reproduce in
a later, much larger non-uniform-delta test that used the full first-use
→ 0x07 announce → adopt sequence instead of this sweep's method of
forcing a raw Cecil-computed index directly for the subsequent-use send
— see `docs/research/2026-07-13-large-delta-cross-assembly-test.md`.
This narrows the gap to "specific to this sweep's forced-index
methodology," not resolved outright, and not chased further per
`CLAUDE.md`.

## Summary

- **First-use RPC dispatch does not misdispatch under a real `method_tag`
  collision.** S1, S2, S3, S5, S6, S8 each sent a first-use RPC for a
  method sharing its real captured `method_tag` with another method already
  first-used (or about to be) on the same connection. Every single
  first-use dispatched to the correct handler with the correct value, with
  no exceptions across 8 first-use sends spanning all four tag buckets
  (0, 4, 8, 12). This directly contradicts the working hypothesis this plan
  was built to test (that distance-server's Bug 2 — a single, unavoidable,
  correctly-tagged first-use misdispatching purely because another method
  already claimed the tag — would reproduce here).
- **Subsequent-use RPC dispatch reliably misdispatches for every method
  tested (13/13, no exceptions)** — but the mechanism has nothing to do
  with `method_tag` or collisions. The real Unity client's subsequent-use
  dispatch table is keyed by a **static per-method index** computed from
  compile-time MethodDef ordering (already documented in
  `2026-06-27-method-index-investigation.md`'s
  `position = base_offset + count(...)` formula, `index = position × 4`,
  shifted +12 for this build's 3 extra non-Loader `[RPC]` classes). The
  **RPC Batch Index (`0x07`) message's reported value is a red herring for
  a non-Unity sender** — the real Unity client's own self-reported "use
  this index for me" value does not match its own real dispatch slot for
  any of the 13 methods tested, for reasons this plan does not need to
  resolve (see "Not investigated further" below). Every subsequent-use
  send in this dataset produced a deterministic, loggable outcome — clean
  dispatch at the right slot, garbage-typed dispatch to the slot's real
  occupant, an explicit parameter-mismatch error, a "not attached to
  script" error, or (for `RPC_Beta`/`RPC_Gamma` specifically) "node not in
  map" — never true silence.

## The static index table (this build)

Confirmed via `scripts/index-sweep-server.py` forcing each computed index
directly (bypassing `_peer_indices`) against the real client — every
subsequent-use send below dispatched cleanly:

| Method | Index | Method | Index |
|---|---|---|---|
| RPC_Void | 92 | RPC_Bytes | 116 |
| RPC_Int | 96 | RPC_IntFloatString | 120 |
| RPC_Float | 100 | RPC_NetworkPlayer | 124 |
| RPC_String | 104 | RPC_NetworkViewID | 128 |
| RPC_Vector3 | 108 | RPC_Alpha | 132 |
| RPC_Quaternion | 112 | RPC_Beta | 136 (first-use only, see Known Issue below) |
| | | RPC_Gamma | 140 (first-use only, see Known Issue below) |

Slot 88 (one below `RPC_Void`'s 92) resolves to `DerivedRpc`, a real
method that exists in this assembly but on a different NetworkView, not
attached to `Loader` — see S4 below. That makes the occupied-slot run
contiguous from 88 through 132, which argues `RPC_Beta`/`RPC_Gamma`
*should* land at 136/140 by the same contiguous pattern — in tension with
their subsequent-use failing with "node not in map" (see Known Issue
below and S8-era "Not investigated further" note). This table's 92-132
rows are the only ones confirmed by a dispatched subsequent-use; 136/140
remain unconfirmed.

## Evidence

### The client's 0x07-reported index does not match its own real slot

`captures/IndexSweep-20260712-235647-server.log` sent first-use for all 13
methods, unmodified, and logged what the client's own `0x07` reply
claimed vs. the computed index that `index-sweep-server.py` then forced
for the subsequent-use send:

| Method | Client's 0x07-reported index | Real dispatch index | Match? |
|---|---|---|---|
| RPC_Void | 20 | 92 | No |
| RPC_Int | 88 | 96 | No |
| RPC_Float | 120 | 100 | No |
| RPC_String | 24 | 104 | No |
| RPC_Vector3 | 88 | 108 | No |
| RPC_Quaternion | 92 | 112 | No |
| RPC_Bytes | 124 | 116 | No |
| RPC_IntFloatString | 92 | 120 | No |
| RPC_NetworkPlayer | 60 | 124 | No |
| RPC_NetworkViewID | 64 | 128 | No |
| RPC_Alpha | 32 | 132 | No |
| RPC_Beta | 32 | 136 | No |
| RPC_Gamma | 32 | 140 | No |

Zero of 13 match. The reported values are also not random noise — they
repeat deterministically across separate captures and across methods
(`RPC_Int` and `RPC_Vector3` both report 88 in every run; `RPC_Alpha`,
`RPC_Beta`, `RPC_Gamma` all report 32). Root-causing exactly why the
client's own batch-index reply diverges from its own dispatch table when
the *sender* is a non-Unity implementation is out of scope for this plan
(see "Not investigated further").

### S2/S3: using the peer-reported index reliably produces wrong-method dispatch or an explicit mismatch error

S2 (`RPC_Float` claims tag 12 → `RPC_Bytes` single first-use → `RPC_Bytes`
recovery send using its own 0x07-reported index 124 → `RPC_Float`
victim-check using its own 0x07-reported index 120):

- Both first-uses dispatched correctly (`RPC_Float`, then `RPC_Bytes`).
- Recovery send (index 124): real client dispatched `RPC_NetworkPlayer(4)`
  — 124 is `RPC_NetworkPlayer`'s real static slot, not `RPC_Bytes`'s (116).
- Victim-check send (index 120): real client attempted
  `RPC_IntFloatString` and logged a parameter-count mismatch — 120 is
  `RPC_IntFloatString`'s real static slot, not `RPC_Float`'s (100).

S3 (mirrored order: `RPC_Bytes` claims tag 12 → `RPC_Float` single
first-use → `RPC_Float` recovery (index 120) → `RPC_Bytes` victim-check
(index 124)), `captures/TagCollision-scenario3-20260713-003916-*`:

- Both first-uses dispatched correctly (`RPC_Bytes`, then `RPC_Float`) —
  order does not matter, confirming first-use is unaffected by tag
  sharing in either direction.
- Recovery send (`RPC_Float` at index 120 = `RPC_IntFloatString`'s slot):
  explicit error, same as S2's victim-check —
  `Failed to invoke arriving RPC method because the parameters didn't
  match the function declaration. 'RPC_IntFloatString' of 'Loader'.`
  `RPC_Float`'s single-`float` payload doesn't decode as
  `RPC_IntFloatString`'s `(int, float, string)` shape, so Unity logs the
  mismatch rather than constructing a call. (Originally misread as
  silence — see erratum at top of doc.)
- Victim-check send (`RPC_Bytes` at index 124 = `RPC_NetworkPlayer`'s
  slot): dispatched as `RPC_NetworkPlayer(4)` — a byte-array payload
  happens to decode as a plausible (garbage) `int`, so the call succeeds
  with a garbage value instead of failing to decode.

This dispatch-vs-mismatch-error split is fully explained by whether the
sent parameter bytes happen to fit the actual target method's parameter
shape — not by anything specific to tag collisions.

### S4: 3-way tag-8 collision, same pattern

`RPC_Int` → `RPC_Vector3` → `RPC_IntFloatString`, each first-used once
then sent again (`captures/TagCollision-scenario4-20260713-004011-*`):

- All three first-uses dispatched correctly, no misdispatch.
- Second round: `RPC_Int`'s and `RPC_Vector3`'s 0x07-reported index was
  the same value (88) for both, and both produced the same explicit
  error, twice: `RPC call failed because the function 'DerivedRpc' does
  not exist in any script attached to 'Loader'.` Slot 88 resolves to a
  real method name (`DerivedRpc`, from the inherited-RPC test class) that
  simply isn't attached to the `Loader` view being targeted — a distinct,
  fifth outcome type from the taxonomy above, and the first real-capture
  confirmation of what occupies slot 88. (Originally misread as silence —
  see erratum at top of doc.) `RPC_IntFloatString`'s reported index
  (92 = `RPC_Void`'s real slot, 0 params) decoded its `(int, float,
  string)` payload as a zero-arg call, producing a clean `RPC_Void`
  dispatch with the real payload bits simply discarded.

### S8: single-method isolation confirms this doesn't need a second claimant

Scenario 8 (added this session, not part of the original S1-S7 matrix):
`RPC_Float` first-use, wait for its `0x07`, then an immediate
subsequent-use of `RPC_Float` alone — no other method's first-use
intervenes. Result: the same explicit `Failed to invoke arriving RPC
method... 'RPC_IntFloatString' of 'Loader'.` error as S2's victim-check
and S3's recovery send (originally misread as silence — see erratum at
top of doc; there was no discrepancy to explain after all). This rules
out "requires a second method's first-use to corrupt state" as a
necessary condition — the peer-reported index is simply never usable for
subsequent-use encoding from a non-Unity sender in this build, tag
collision or not.

### Independent third confirmation: WrongIndex-20260628-004459 (pre-dates this plan)

`captures/WrongIndex-20260628-004459-*` (from `scripts/wrong-index-server.py`,
run before this plan existed, originally analyzed in
`2026-06-27-method-index-investigation.md`'s "Python wrong-index
experiment"): Phase 6 sent a subsequent-use `RPC_String` with no
preceding first-use, at a **deliberately chosen but real** index (`0x78` =
120). The client dispatched it as `RPC_IntFloatString(16, 13616.77, "")`
— exactly matching the static table (120 = `RPC_IntFloatString`) and
exactly the same garbage-dispatch behavior seen in S2-S4, timestamp-correlated
against the server log's Phase 6 send. Phases 2/3/5 used arbitrary
non-slot values (`0x30`=48, `0x08`=8) and got explicit `Internal RPC
error` rejections instead — those aren't real dispatch-table entries, so
there's nothing for them to (mis)decode as.

**Erratum:** `2026-06-27-method-index-investigation.md`'s "Evidence:
Python wrong-index experiment" section states "Unity rejected the
mismatch," citing this same capture. That's incomplete — it's true for
arbitrary non-slot indices (48, 8), but false for indices that happen to
land on a real method's slot (120), which produce a silent misdispatch
with garbage-but-well-typed parameters, not a rejection. See Known Issue
below and `spec-status.md`.

## What this means for distance-server's Bug 2

Distance-server's actual reported failure (`RPC_BROADCAST_ALL` →
`RPC_TARGETED`, both tag 8, first-use) does **not** reproduce under any
scenario run here — every first-use across S1-S8, all four tag buckets,
dispatched correctly regardless of what else shared its tag or had already
been used on the connection. Distance's own report used the same wire
mechanism (a real Unity client, real API), so the discrepancy is not a
methodology gap on our side; either Distance's build exhibits behavior
this build doesn't (different assembly layout, different Unity
patch/platform), or Distance's dispatch-matrix testing was itself
observing a subsequent-use-style effect (a stale/reused index from earlier
traffic) mislabeled as a first-use collision. This repo cannot resolve
which without Distance's own capture or a build with matching assembly
layout — flagged for the reply to distance-server's inbox.

The shipped `316a1ae` fix (real captured `method_tag` values, replacing
the disproven `index & 0x0F` formula) remains correct and necessary
regardless: it ensures the wire-level tag we emit matches what a real
Unity sender would emit. It just isn't gating the misdispatch mechanism
this plan set out to find, because that mechanism doesn't appear to exist
in this build.

## Production-code implication (corrected 2026-07-13, third pass)

**Superseded — the paragraph originally here concluded `_peer_indices` was
unreliable and should be replaced with a directly-computed static index.
That conclusion depended on the same decoder bug and is wrong.** With the
fixed decoder, `_peer_indices` (the client's self-reported `0x07` value,
`protocol/unity_server.py`'s `_send_rpc_to`) is correct: it reports the
receiver's own real static dispatch index, and real Unity's own outbound
sends use exactly that value (adoption, confirmed direction-resolved
against `CrossBinary-20260628-004945.pcap` — see
`docs/research/2026-07-13-batch-index-decoder-was-broken.md`). No fix is
needed on the outbound-send side.

The real, separate gap (found independently this session, Python-only):
`decode_rpc`/`_handle_rpc`'s *inbound* decode path resolves a
subsequent-use `method_name` from a single process-wide global
(`INDEX_TO_METHOD`) instead of each instance's own previously-
self-announced index, which causes cross-connection misdispatch when two
client or server instances in one process independently announce
different indices for the same method. Tracked and fixed via
`docs/plans/global-index-table-cross-connection-leak.md` — not the fix
originally proposed in this section.

## Not investigated further (explicitly out of scope for this plan)

- *Why* the client's own `0x07` reply diverges from its own real dispatch
  slot when the first-use sender is non-Unity. Candidate explanations
  (untested): the reply's index computation depends on `class_guid`
  matching a value only a real Unity sender would compute correctly; the
  reply is computed via a different internal code path than the one that
  populates the per-connection dispatch table; some registration step
  that only runs for genuine Unity-to-Unity traffic never fires for us.
  Resolving this is re-deriving Unity's internal formula, which this
  plan's "Explicitly out of scope" section already excludes.
- `RPC_Beta`/`RPC_Gamma`'s own subsequent-use failure (`Unable to
  retreive RPC node from map`, distinct from the misdispatch/silence
  pattern above) — noted in `2026-07-13-method-index-ceiling-fix.md`,
  tracked as a continuation of task #7, not resolved here.
