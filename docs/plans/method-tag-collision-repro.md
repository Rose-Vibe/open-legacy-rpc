# Plan: Repro the method_tag collision failure mode, and characterize whether the shipped fix prevents it

Date: 2026-07-12 (revised 2026-07-12, second pass)

## Background

`docs/plans/method-tag-collision-guard.md` (implemented, commits
`e3dab23`/`c19be59`) removed `registerMethodTag`/`registerMethodTags` and
added a warn-once guard for repeated first-use sends. That work was driven
entirely by distance-server's own black-box evidence
(`/home/server-mint/distance-server/docs/plans/rpc-dispatch-matrix-full-method-coverage.md`)
and static code inspection of this repo — **not** by an independent repro
against a real Unity client in this repo.

Separately, `docs/plans/method-tag-real-derivation-fix.md` (implemented,
commit `316a1ae`) replaced the disproven `method_tag = index & 0x0F`
formula with a hardcoded, empirically-captured per-method-name lookup
table (`docs/research/2026-07-12-method-tag-real-derivation.md`), exposed
via `register_method_tag(s)`.

### Why this plan exists, and why it was revised a second time

distance-server sent this repo an async message (via the cross-session
inbox) with new evidence from testing against a **real, unmodified Unity
client running the actual Distance game** — not our own decoder, which
can only mirror the encoder's assumptions and cannot reveal real client
dispatch behavior:

- Their "Bug 2" bisection confirmed `method_tag` genuinely gates
  dispatch: `tag=4` → silent non-dispatch, `tag=8` → correct dispatch,
  everything else byte-identical.
- Their "Finding A" follow-up found a **real, in-the-wild tag collision**:
  `RPC_TARGETED` and `RPC_BROADCAST_ALL` both carry `tag=8` in Distance's
  own compiled build. In isolation (fresh connection, no other tag-8
  traffic yet), `RPC_BROADCAST_ALL`'s first-use dispatched correctly. In
  realistic connection history — where `RPC_TARGETED` had already been
  first-used earlier via an unrelated `AddClient` call (also tag 8) —
  `RPC_BROADCAST_ALL`'s first-use was misdispatched to `RPC_TARGETED`'s
  handler in 9/12 sends.
- Their own corrective follow-up clarified the framing precisely: the
  wire-level tag *value* per method name is static (confirmed stable
  across sessions); what's order-dependent is the *dispatch outcome* when
  two different methods share a tag — apparently a connection-scoped
  "first claim wins" cache/alias mechanism on the receiver.

They asked this repo to build an isolated, Distance-independent repro of
this mechanism using our existing real-Unity-client experiment harness,
covering: order/symmetry, whether `tag=0` is a specially-exempt sentinel,
whether a clobbered method's own later subsequent-use dispatch also
breaks, RPCMode-dependence, 3+-way collisions, and whether relying on
real registered per-connection indices sidesteps the problem.

**This directly matters for the just-shipped `316a1ae` fix.** That fix
guarantees the *tag value* emitted per method name matches what a real
Unity sender would emit, and (via the pre-existing collision guard)
guarantees no method repeats first-use once its real index is known. But
neither guarantee prevents two *different* methods from sharing a tag —
4 bits is 4 bits, and Loader's own tag-8 bucket alone has 5 real methods.
If a method's very first, single, correctly-sent first-use misdispatches
purely because another method already claimed its tag on that
connection, the shipped fix does not prevent Distance's Bug 2 at all; it
only removes an aggravating condition (repetition). This plan exists to
find out, empirically, whether that's the case.

### First plan revision (already implemented, in `scripts/tag-collision-server.py` / `tag-collision-fixed-server.py`, uncommitted)

The first pass reused the existing "hand-craft the wire bytes, bypass our
own library's public API" technique from `scripts/wrong-index-server.py`,
grouping Loader's 13 built-in `[RPC]` methods into tag buckets computed
via `idx = (rid - 8) * 4` — the *disproven* index-derived formula. Both
scripts still exist on disk with erratum comments (added same day)
acknowledging their scenario pairs no longer collide under the real,
captured tag values. They were never run. This second revision
supersedes their scenario tables entirely; see "Method" below.

### Second plan revision (this pass): real buckets, Fable design consult

Loader's 13 built-in `[RPC]` methods, grouped by their **real captured**
`method_tag` (`docs/research/2026-07-12-method-tag-real-derivation.md`,
`_LOADER_REAL_TAGS` in `protocol/unity_protocol.py`):

| tag | methods |
|-----|---------|
| 0   | RPC_Void, RPC_String |
| 4   | RPC_NetworkPlayer, RPC_Alpha, RPC_Beta, RPC_Gamma |
| 8   | RPC_Int, RPC_Vector3, RPC_Quaternion, RPC_IntFloatString, RPC_NetworkViewID |
| 12  | RPC_Float, RPC_Bytes |

This is a materially different grouping than the first revision's table
(e.g. `RPC_Float`/`RPC_Alpha` do **not** actually collide; `RPC_Float`/
`RPC_Bytes` do). This revision was designed in consultation with a
Fable-model agent (`tag-collision-fable-design`, kept addressable for
ongoing consult through implementation), which made two corrections to
the initial framing worth recording here:

1. **`RPC_Void` is not tag-0-bucket-unusable.** The zero-arg
   `NetworkView.RPC` crash (`Array.Empty<object>()` missing from this
   mscorlib) only bites a *Unity client initiating* the call. Our Python
   server encodes and sends `RPC_Void` itself, and the derivation doc
   already recorded it dispatching correctly when sent that way. So
   `RPC_Void` → `RPC_String` is a legitimate, non-fabricated tag-0
   collision pair — no need to bend the "no fabricated collisions"
   principle for this bucket.
2. **Hand-crafting is not the risk it first appears to be, but it tests
   the wrong condition for the primary question.** `send_hand_crafted`
   calls the exact same `encode_rpc_first_use()` the real API calls —
   the bytes are identical, only bookkeeping differs, and the derivation
   doc already confirmed our first-use encoding is byte-for-byte correct
   against a real capture (tag nibble aside, now fixed). The actual
   problem with hand-crafting-via-repetition is that *forced repeated
   first-use* is a wire condition a real Unity sender never produces —
   real senders transition to subsequent-use after one round trip. Since
   distance-server's actual bug requires **no repetition** (it happened
   on `RPC_BROADCAST_ALL`'s very first first-use), the primary scenario
   below uses `send_rpc()` exclusively, never hand-crafted repetition.

Consequently: **the two-script split (hand-crafted "Experiment A" /
real-API "Experiment B") is dropped.** Everything below is one
data-driven driver script using only the real public API
(`UnityServer.send_rpc()`); Experiment B's checks (one first-use per
method, warn-once never fires) become cross-cutting assertions applied
to every scenario, not a separate run.

## Method

Reuse the existing experiment harness (`experiments/*.cs` +
`scripts/run-*.sh` + netns/tshark, per `feedback_experiment_approach`).
Keep `make_server`/`poll_server`/the ready-ping connection gate/the
`TARGET_VIEW = 0x0002` scene-view fix from the first-revision scripts —
those mechanics are sound. Delete `send_hand_crafted` and both scenario
tables; replace with a single data-driven scenario table of
`(method, params, mode)` steps, driven entirely through `send_rpc()`.

`experiments/TagCollisionExperiment.cs` (already written: connect, send
`RPC_Gamma` as a ready ping, wait, log `EXPERIMENT_DONE`) needs no
changes — all scenario logic stays server-side in Python, per the
existing convention.

**Fresh connection per scenario**, each its own Unity client process
launch, so no scenario's dispatch state leaks into the next.
`Network.InitializeSecurity()` is never called (standing constraint).

**Nondeterminism:** distance-server's own result was 9/12, not 12/12 —
a single clean run does not refute a real collision, and a single
misdispatch does not confirm one beyond doubt either. The driver takes
`--repeat N` (default 1); rerun the primary scenario (S2) and its mirror
(S3) at N=3 if the first pass is anything other than uniformly clean or
uniformly misdispatched.

### Cross-cutting instrumentation (applies to every scenario)

- `UnityServer._handle_batch_index` (`protocol/unity_server.py:346`) is
  currently silent. Add a log line (method name + assigned index) in the
  driver's own server instance or via a thin wrapper — whether, and
  what, the client registers via the `0x07` batch-index response *after
  a misdispatched first-use* is the single most mechanism-revealing
  observable available: it tells us whether the client resolved the
  method's true identity internally even while dispatching it to the
  wrong handler.
- Wire assertion: first-use bit set at most once per method per
  connection, except the documented no-`0x07`-arrived recovery case
  (distinguished by the existing "Re-sending first-use RPC" warning log
  line).
- Capture the client's full Unity log, including any "Internal RPC
  error" lines — silence vs. an explicit rejection is a load-bearing
  distinction (the original plan's Known Issue #1 text already
  conflated these; see Exit Criteria).

### Scenario matrix

- **S1 — baseline / harness gate.** `RPC_String` (tag 0) then `RPC_Float`
  (tag 12), one first-use each, real API — shares no tag with each other
  or with `RPC_Gamma`. Exit: both log the correct handler and value;
  wire shows exactly one first-use per method. If this fails, it's a
  harness bug — stop and fix before running anything else.

- **S2 — PRIMARY (the single-unavoidable-first-use question), tag 12,
  order A.** `RPC_Float(9.99)` first-use → poll for its `0x07`, checking
  `server._peer_indices[addr]` directly and logging the result as an
  explicit precondition line (not just a fixed wait) — if `RPC_Float`'s
  index hasn't registered by the deadline, log the run as **degraded**
  and note it in the findings write-up rather than proceeding silently;
  the tag was still claimed by `RPC_Float`'s first-use either way, so
  the `RPC_Bytes` observation below remains valid, but the "would
  spacing first-uses around the 0x07 round trip have helped" mitigation
  question is only answerable if this precondition is on record → then
  **`RPC_Bytes([0xDE, 0xAD, 0xBE, 0xEF])` single first-use — this is the
  observation the whole plan exists to make** → `RPC_Bytes` again
  (recovery send: subsequent-use if its own `0x07` arrived, or a logged
  repeat-first-use warning if not) → `RPC_Float` again (checks whether
  the first claimant's own subsequent-use dispatch still works after
  being "clobbered" by a later first-use claim on its tag). Exit: an
  explicit recorded outcome for the `RPC_Bytes` first-use, categorized as
  one of {dispatched as `RPC_Bytes`, dispatched as `RPC_Float` with
  garbage/reinterpreted value, silence, explicit client error}, plus
  whether `RPC_Bytes`'s `0x07` ever arrived, plus the outcome of both
  follow-up sends. `0xDEADBEEF` reinterpreted as a float is a garish
  `-6.6e18`; `9.99f`'s raw bytes read as a byte array are unmistakably
  not `0xDEADBEEF` — a misdispatch in either direction is legible in the
  client log, not ambiguous.

- **S3 — order B (symmetry check against S2).** `RPC_Bytes` first-use →
  `RPC_Float` first-use → `RPC_Float` again → `RPC_Bytes` again. Same
  exit criteria as S2, mirrored. S2 vs. S3 together answer whether
  first-claim-wins is symmetric (whichever method sends first always
  wins) or has some other bias. Note up front: S2 and S3's misdispatch
  directions are expected to look different, not symmetric-in-form. If
  `RPC_Bytes` misdispatches to `RPC_Float` (S2), the first 32 payload
  bits decode as a float — legible garbage. If `RPC_Float` misdispatches
  to `RPC_Bytes` (S3), `9.99f`'s raw bytes (`0x411FD70A`) are read as the
  byte-array *length prefix* — roughly 1.09e9, far past this repo's own
  `MAX_BYTES_PARAM_SIZE` (1 MiB) — so the likely observable outcome is a
  decode failure or silence, not a legible `RPC_Bytes(N bytes)` line.
  That is an expected, documented possible outcome for this direction,
  not a sign S3 was inconclusive by design flaw.

- **S4 — 3-way collision, tag 8.** `RPC_Int(999)` → `RPC_Vector3(1,2,3)`
  → `RPC_IntFloatString(7, 2.5, "x")`, each sent once, then each sent
  once more. This distinguishes between two possible cache mechanisms:
  if both later methods misdispatch to `RPC_Int`, the tag slot is
  claimed once and never overwritten; if `RPC_IntFloatString`
  misdispatches to `RPC_Vector3` instead, the slot is overwritten by
  each new first-use claim. Note up front: mismatched param widths mean
  some misdispatches may read as silence or a decode error rather than
  legible garbage — that is an expected, documented possible outcome for
  this scenario, not a failure of the design.

- **S5 — tag-0 sentinel check.** `RPC_Void` → `RPC_String`, both real
  API (per the Fable-agent correction above, `RPC_Void` is legitimately
  sendable server→client). Exit: if `RPC_String` misdispatches to
  `RPC_Void`, tag 0 is an ordinary slot like any other; if S2/S3 show
  misdispatch but S5 stays clean, tag 0 is a plausible sentinel; if
  nothing anywhere misdispatches, the question is moot but this
  scenario was still cheap to run.

- **S6 — RPCMode variant.** Exact repeat of S2 with `mode=RPCMode.Others`
  instead of the default. Verified before adding this scenario:
  `send_rpc()` accepts `mode`; `RPCMode.Others` adds no extra wire
  fields (only `RPCMode.Player` does — see below). **`RPCMode.Player` is
  explicitly excluded**: both `encode_rpc_subsequent` and
  `encode_rpc_first_use` write a hardcoded 1-bit target field
  (`protocol/unity_protocol.py:397-398` and `:462-463` respectively,
  always `write_bit(0)`) that looks like a placeholder rather than a real
  implementation of per-player targeting — a `RPCMode.Player` scenario
  would test our encoder's untested guess, not real Unity behavior, and
  is out of scope here. (Distance's "`RPC_TARGETED`" name refers to the
  method's own purpose, not necessarily `RPCMode.Player` on the wire —
  All vs. Others already covers the mode-dependence question honestly.)

- **S7 — outbound-contamination probe (secondary).** Server sends only
  `RPC_Alpha(111)` once, real API, tag 4. The client has already
  first-used `RPC_Gamma` (also tag 4) *outbound* as its ready ping
  before this send happens. Both methods take a single `int`, so
  decoding succeeds either way — the only question is which handler
  name appears in the client log. `RPC_Alpha`-as-`RPC_Alpha` → outbound
  sends don't seed the receive-side slot table (validates every other
  scenario's assumption that `RPC_Gamma` doesn't contaminate them);
  `RPC_Alpha`-as-`RPC_Gamma` → send and receive share one slot table, a
  significant finding in its own right.

Distance-server's "does relying on real registered per-connection
indices sidestep the problem" question is answered implicitly by the
recovery sends already built into S2/S3/S4: those are exactly
subsequent-use dispatch via the client-assigned index, no tag on the
wire at all.

## Exit Criteria

- One driver script (replacing both `scripts/tag-collision-server.py`
  and `scripts/tag-collision-fixed-server.py`) runs all 7 scenarios
  end-to-end against the real headless Unity Linux player in the
  `unitynet` netns, with `--scenario N --repeat N` options.
  `scripts/run-tag-collision.sh` updated to match (pcap capture, log
  tailing for `EXPERIMENT_DONE`, summary printed per scenario).
- All 7 scenarios run at least once; S2/S3 rerun at `--repeat 3` if
  their first pass isn't uniformly clean or uniformly misdispatched.
  Logs and pcaps saved under `captures/`.
- A findings write-up added to `docs/research/` (date-prefixed) stating
  plainly what was observed in every scenario, including "inconclusive"
  where the log doesn't resolve it — and explicitly correcting
  `docs/research/spec-status.md` / `unity-legacy-networking-wire-format.md`'s
  existing Known Issue #1 text, which currently describes the
  `WrongIndex-*` capture evidence as Unity "rejecting" a mismatched
  subsequent-use index; the actual log
  (`RPC_IntFloatString(16, 13616.77, "")`) shows a misdispatch with
  garbage params, not a rejection.
- If S2 reproduces a single-unavoidable-first-use misdispatch, the
  write-up must say plainly that the shipped `316a1ae` fix removes an
  aggravating condition (repetition) but does not prevent Distance's
  Bug 2 mechanism, and enumerate what (if anything) the recovery-send
  data in S2-S4 suggests as a real mitigation (e.g. scheduling colliding
  methods' first-uses so each `0x07` round trip completes before the
  next colliding first-use is sent — S2's own structure already tests
  whether that ordering would have helped).
- Reply to distance-server's inbox thread with the findings once the
  write-up is done.

## Explicitly out of scope

- Re-deriving Unity's real internal `method_tag`/`method_index` formula
  beyond what's already documented — this plan characterizes dispatch
  *behavior*, not the tag's numeric origin.
- `RPCMode.Player` (see S6 rationale).
- Any change to `Network.InitializeSecurity()` usage (must stay
  disabled).
- Building a new Unity project/build per scenario — everything reuses
  the existing Loader build + `Experiments.dll` pattern.
- Designing or implementing an actual fix for whatever S2-S4 reveal —
  that is a follow-on piece of work through the full CLAUDE.md pipeline,
  scoped once this plan's findings are in.
