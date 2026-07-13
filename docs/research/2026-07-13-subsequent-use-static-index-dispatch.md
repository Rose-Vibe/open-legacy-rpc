# Subsequent-use RPC dispatch keys off a static per-method index, not the peer-reported 0x07 value

Findings write-up for `docs/plans/method-tag-collision-repro.md` (scenarios
S1-S8, run against the real headless Unity 2018.1.6f1 Linux player in the
`unitynet` netns). Corrects a claim in
`docs/research/2026-06-27-method-index-investigation.md` and adds a new
Known Issue to `docs/research/spec-status.md`.

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
- **Subsequent-use RPC dispatch does misdispatch (or silently drop),
  reliably, for every method tested except `RPC_Void`/`RPC_Int`** — but the
  mechanism has nothing to do with `method_tag` or collisions. The real
  Unity client's subsequent-use dispatch table is keyed by a **static
  per-method index** computed from compile-time MethodDef ordering (already
  documented in `2026-06-27-method-index-investigation.md`'s
  `position = base_offset + count(...)` formula, `index = position × 4`,
  shifted +12 for this build's 3 extra non-Loader `[RPC]` classes). The
  **RPC Batch Index (`0x07`) message's reported value is a red herring for
  a non-Unity sender** — the real Unity client's own self-reported "use
  this index for me" value does not match its own real dispatch slot for
  most methods in this build, for reasons this plan does not need to
  resolve (see "Not investigated further" below).

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

### S2/S3: using the peer-reported index reliably produces wrong-method dispatch or silence

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
  silence — no dispatch, no error. `RPC_Float`'s single-`float` payload
  doesn't decode as `RPC_IntFloatString`'s `(int, float, string)` shape, so
  Unity can't construct a call at all.
- Victim-check send (`RPC_Bytes` at index 124 = `RPC_NetworkPlayer`'s
  slot): dispatched as `RPC_NetworkPlayer(4)` — a byte-array payload
  happens to decode as a plausible (garbage) `int`, so the call succeeds
  with a garbage value instead of failing to decode.

This silence-vs-garbage-dispatch split (also seen in S8 below) is fully
explained by whether the sent parameter bytes happen to fit the actual
target method's parameter shape — not by anything specific to tag
collisions.

### S4: 3-way tag-8 collision, same pattern

`RPC_Int` → `RPC_Vector3` → `RPC_IntFloatString`, each first-used once
then sent again (`captures/TagCollision-scenario4-20260713-004011-*`):

- All three first-uses dispatched correctly, no misdispatch.
- Second round: `RPC_Int`'s and `RPC_Vector3`'s 0x07-reported index was
  the same value (88) for both — real slot at 88 apparently doesn't
  decode as a valid call for either payload shape, so both were silent.
  `RPC_IntFloatString`'s reported index (92 = `RPC_Void`'s real slot, 0
  params) decoded its `(int, float, string)` payload as a zero-arg call,
  producing a clean `RPC_Void` dispatch with the real payload bits simply
  discarded.

### S8: single-method isolation confirms this doesn't need a second claimant

Scenario 8 (added this session, not part of the original S1-S7 matrix):
`RPC_Float` first-use, wait for its `0x07`, then an immediate
subsequent-use of `RPC_Float` alone — no other method's first-use
intervenes. Result: silence, matching S2/S3's silence cases. This rules
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

## Production-code implication (out of scope for this plan, tracked separately)

`protocol/unity_server.py`'s `_send_rpc_to` currently uses `_peer_indices`
(the client's self-reported `0x07` value) for subsequent-use encoding.
Per the evidence above, that value is unreliable for every method tested
except where it happens to coincidentally match (none did, in this
build). This is a real production-code correctness gap — not simulated —
but designing and implementing the fix (most likely: compute and use the
static per-method index directly, the same approach already validated in
`scripts/index-sweep-server.py`) is explicitly out of scope for this plan
(see its "Explicitly out of scope" section) and is deferred to a follow-on
plan through the full CLAUDE.md pipeline.

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
