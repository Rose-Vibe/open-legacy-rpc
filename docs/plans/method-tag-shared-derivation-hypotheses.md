# method_tag: Shared-Derivation Rule (Confirmed) and Propagation Plan

Date: 2026-07-13
Status: RULE CONFIRMED — plan now covers hardening + propagating the fix.
Originally scoped as a hypothesis-testing plan; superseded mid-review after
the Fable reviewer (`method-tag-fable-peer`) found and validated a
zero-free-parameter derivation. Independently re-verified below (not taken
on trust) before committing to this rewrite.

## Background

`CLAUDE.md`'s "Why the Protocol Must Assume Divergent Assemblies" section
argues that Unity's design intent requires `method_tag` to be derivable by
both peers *without* either side knowing the other's whole-assembly
compiled layout. This document originally laid out six untested
hypotheses (H1-H6) plus an automated controlled-variable experiment matrix
to search for that derivation. Before the matrix was built, the Fable plan
reviewer found the actual rule while checking the existing confound
analysis. It has since been independently reproduced from scratch (see
Verification below) rather than accepted on the reviewer's say-so.

## The Rule

`method_tag`'s upper 2 bits are not an independent field — they are
spillover from the same StringCompressor Huffman-encoding stream that
`compute_method_id` (`protocol/unity_protocol.py:38`) already builds for
the class-GUID/method-hash identifier. Concretely:

```
s   = '00' + Huffman(method_name) + code(0) + code(0) + ...   # code(0) = pad-source constant, 16 bits: '0101011110001101'
cap = 8 * ceil(len(Huffman(method_name)) / 8)
tag = int(s[cap : cap + 2], 2) << 2
```

This is computable from the method name alone — no signature, no
declared position, no compiled RID, nothing whole-assembly-relative. It
is exactly the kind of shared-computable derivation CLAUDE.md's
divergent-assemblies argument predicted must exist, given `method_tag`
has no `0x07`-style negotiation channel to fall back on.

The low 2 bits of the tag nibble have been 0 in every observation so far;
their semantics are unconfirmed (possibly always-zero, possibly meaningful
in a case not yet observed — see Phase 0 below).

## Verification

Two independent checks, both done directly against raw bytes/code, not
inferred from the reviewer's summary:

1. **Ground truth (13/13).** Reimplemented the formula from scratch
   against the 13-method table in
   `docs/research/2026-07-12-method-tag-real-derivation.md` (all methods
   on `Loader`, `UnityProject/Assets/Scripts/Loader.cs:184-272`). Exact
   match on every row, including the behaviorally-load-bearing
   `RPC_Float → 12` case. No fitted parameters. Chance probability of a
   13/13 match against a 4-valued field is ~1.5e-8.
2. **Out-of-sample, from a different capture (2/2).** Predicted
   `BaseRpc → 4` and `DerivedRpc → 12` (names never used in fitting the
   rule, declared in `InheritedRpcBase`/`InheritedRpcDerived`, a
   different class hierarchy than `Loader`), then manually decoded the
   raw first-use frames from `captures/InheritedRpcExperiment-20260627-102459.pcap`
   using `protocol.bitstream.BitStream` against the exact bit layout in
   `encode_rpc_first_use` (`protocol/unity_protocol.py:434-495`). The
   decoded identifier bytes matched `compute_method_id('BaseRpc')` /
   `compute_method_id('DerivedRpc')` exactly (confirming packet identity,
   not just an assumed label), and the decoded tags were 4 and 12
   respectively — both exact matches.

Not yet independently re-verified: the reviewer's cross-build
(`LargeDelta-20260713-*.pcap`) claim that two divergent-index builds emit
identical tags for the same 13 names. A spot-check of
`LargeDelta-20260713-031337.pcap` reproduced the same 13 (identifier,
tag) pairs as the original ground-truth table (consistent with the claim)
but `LargeDelta-20260713-030839.pcap` yielded no decodable first-use
frames via `decode_pcap.py` in this pass — worth a clean re-check in
Phase 0 below, but not blocking: the rule is already confirmed
name-only/build-independent by construction (it only reads
`get_codes()`, a static Huffman table, and the method name string), so
this is a confirmation of that fact, not a load-bearing test of it.

3. **Wide sweep, all 86 captures (155 matching frames, 3rd independent
   check).** Scanned every `captures/*.pcap` for first-use frames whose
   identifier matches one of the 16 known RPC names and compared the
   observed tag against the predicted one. First pass over-reported:
   16 names scored, 10 clean, but 6 (`RPC_Int`, `RPC_Float`,
   `RPC_String`, `RPC_Quaternion`, `RPC_Alpha`, `RPC_Beta`) appeared to
   show genuine variance, including in
   `RpcNameVaryExperiment-20260626-031616.pcap` — a plain
   `experiments/*.cs` capture with **no** Python-side driver, which
   would have been a real counterexample. Root-caused: the sweep
   script's mismatch report listed every pcap containing *any*
   observation of an identifier, not specifically the pcaps with a
   *wrong* one — pure reporting bug, not a decode bug. Rerunning with
   per-pcap (pcap, observed, predicted) attribution shows
   `RpcNameVaryExperiment-20260626-031616.pcap` itself is clean
   (RPC_Alpha 4/4 OK, RPC_Beta 4/4 OK) — it only ended up in the
   mismatch list because it also contains a matching *correct*
   observation, alongside wrong ones logged elsewhere. All 155
   matching frames were then re-attributed individually: every single
   wrong-tag observation (36 total, across the 6 names) traces to
   `TagCollisionFailure-scenario*` or `WrongIndex-*` captures. Both are
   confirmed non-Unity-computed by inspecting their driver scripts —
   `run-wrong-index.sh` explicitly launches `scripts/wrong-index-server.py`
   as "Python server (NOT Unity — we're crafting custom packets)", and
   `TagCollisionFailure-*` comes from `scripts/tag-collision-server.py`
   (same Python-driver pattern as `run-tag-collision.sh`). Zero wrong-tag
   observations occur in any pure real-Unity-to-Unity capture. This was
   the user's own suggestion ("test against a wider set of names before
   committing") and it correctly surfaced a real issue — just in the
   verification tooling, not in the rule itself.

## Falsified / superseded hypotheses (kept for the historical record)

The original H1-H6 fan-out and the automated controlled-variable matrix
(Phase 1b, in the prior version of this doc) are moot — the rule above
supersedes all of them. Per the reviewer's correction to the original
confound analysis: H1 was already falsified by the existing single-class
data, not "untested as claimed" — rows with declaration position ≡ 0 mod
4 (`RPC_Void`, `RPC_Vector3`, `RPC_NetworkPlayer`, `RPC_Gamma`) carry tags
`{0, 8, 4, 4}`, not a constant, so no `tag = f((position + c) mod 4)`
mapping for any `f`/`c` survives the existing data — the multi-class
experiment to "break the confound" was never actually necessary. H3
(alphabetical) and H6 (per-class offset) die the same way. H2 (name-hash
mod 4) was noise (6/13, and an independent ~35-candidate hash screen
topped out at 6/13 too). See the reviewer's message
(2026-07-13, `method-tag-fable-peer`) for the full per-hypothesis
partition-consistency argument.

## Remaining Plan (as approved by Fable review, 2026-07-13)

### Phase 0 — Cheap hardening (no new Unity capture) — DONE

1. ~~Re-check `LargeDelta-20260713-030839.pcap`'s decode gap~~ — checked
   both logs: the run aborted immediately
   (`MissingMethodException: System.Array.Empty` in the experiment DLL,
   a Mono-runtime incompatibility unrelated to method_tag). Zero
   first-use frames is expected for an aborted run; no decoder fix
   needed. `031337.pcap` is the clean run and already confirms the
   cross-build claim.
2. ~~Score the rule against every other capture~~ — done as the wide
   sweep (see Verification #3 above): 155 first-use frames across all
   86 captures, zero genuine-Unity mismatches.
3. ~~Characterize the always-0 low 2 bits~~ — checked independently:
   continuing the Huffman/pad stream 2 more bits after the tag's high 2
   bits predicts *varying, nonzero* values (e.g. `10`, `01`, `11`
   depending on name) that never appear on the wire (always `00`) — so
   confirmed NOT stream continuation. Per Fable, park this as an open
   question rather than investigate further now; Phase 1's confirmation
   run should log the full nibble per frame so it's characterized
   opportunistically.
4. ~~Fix `scripts/verify-protocol-fields.py` crashes~~ — DONE. Root
   cause of both `check_target_view:115` and `check_method_tag:249`:
   `decode_rpc` (`protocol/unity_protocol.py`) only set
   `result['method_hash']`/`result['method_name']` when `hash_bytes > 0`
   — any first-use identifier that fits entirely in the 6-byte
   `class_guid` (empty hash, e.g. `BaseRpc`) silently dropped the key,
   causing `KeyError: 'method_name'` downstream. Fixed by always setting
   both, and replacing `lookup_method_by_hash` (hash-only, ambiguous
   when hash is empty) with a new `lookup_method_by_identifier(guid_hex,
   hash_hex)` that matches on the full identifier — applied to both
   `decode_rpc` and `decode_batch_index` (0x07), which had the same
   latent ambiguity. Added a guard to `check_target_view` for
   `method_name == 'unknown'` (the other two checks already had one).
   Also found and fixed a third, unrelated pre-existing crash while
   sweeping: `verify_roundtrip` read `decoded['view_id']`, a key
   `decode_rpc` never populates (view_id is an accepted-but-unused
   parameter of both RPC encoders; the wire format has no per-RPC
   view_id field) — this crashed the roundtrip section on every capture
   with a known-signature RPC. Fixed by dropping the dead read and
   using the encoders' default. Verified: `pytest tests/` still
   73/73 pass; swept all 86 `captures/*.pcap` through
   `verify-protocol-fields.py` — zero crashes (one `PermissionError` on
   a root-owned pcap turned out to be a leftover file-permission
   artifact from an earlier capture run, fixed with `chmod`, unrelated
   to any of the above).

### Phase 1a — Smoke test (gates Phase 1, do before any generator/capture code) — ~~DONE~~

5. ~~Confirm a runtime-`AddComponent`'d `[RPC]`-bearing class (defined in
   `experiments/*.cs`, not compiled into `Assembly-CSharp.dll`) is
   actually reachable via Unity's reflection-based RPC dispatch.~~
   Confirmed 2026-07-13 via `experiments/RuntimeRpcSmokeExperiment.cs`:
   a class (`RuntimeRpcBehaviour`) defined purely in `experiments/*.cs`
   (compiled into `Experiments.dll` via `mcs`, never part of
   `Assembly-CSharp.dll`), `AddComponent`'d onto the scene-baked
   `PrimaryNetworkView`'s GameObject at runtime and assigned as
   `.observed`, IS discovered by Unity's reflection-based `[RPC]`
   dispatch — server log shows
   `[RPC] RuntimeRpcBehaviour.RPC_SmokeTest(42) from 1`, and the wire
   capture (`RuntimeRpcSmokeExperiment-20260713-100821.pcap`) shows a
   normal `msg_id 0x1b` `first_use` RPC frame with a real
   `classGuid`/`methodHash` identifier.
   Fable's predicted failure mode WAS real, though, and cost two
   iterations before landing on this result: Unity validates locally,
   on the *sender*, that the RPC method name exists on
   `NetworkView.observed` before it will put anything on the wire at
   all. The first attempt only swapped `.observed` on the server side
   (matching `AllocatedViewRpcExperiment`'s asymmetric pattern) and the
   client silently refused to send
   (`"RPC call failed because the function 'RPC_SmokeTest' does not
   exist in the any script attached to 'Loader'"` — zero RPC bytes on
   the wire, confirmed via pcap). Fixed by swapping `.observed` to a
   `RuntimeRpcBehaviour` instance on **both** peers, unconditionally,
   in `Setup()` rather than role-gated in `OnServerReady()`. (A second,
   unrelated bug fixed along the way: the client's `Tick()` fired
   before `OnConnectedToServer`, since `Loader.started` is set
   synchronously right after the async `Network.Connect()` call — fixed
   by gating the send on a `connected` flag set in `OnClientConnected`
   instead of firing on the first `Tick()`.)
   **Consequence for Phase 1**: the predictive-confirmation experiment
   must swap `.observed` on both client and server for every runtime-
   `AddComponent`'d RPC-bearing class it uses, not just the receiver.

### Phase 1 — Predictive confirmation run (slimmed per Fable review) — ~~DONE~~

**Result: 11/11 exact matches.** Ran
`experiments/RpcTagPredictiveExperiment.cs` (single class
`PredictiveTagBehaviour`, 11 `[RPC] void Name(int, NetworkMessageInfo)`
methods declared in shuffled, non-alphabetical/non-tag-grouped order,
`AddComponent`'d and `.observed`-swapped on both peers per the Phase 1a
finding) against
`captures/RpcTagPredictiveExperiment-20260713-101651.pcap`. All 11
predicted tags were computed *before* the capture (embedded as a comment
table in the experiment file) via brute-force search over the formula
for names hitting each required boundary/spill-value combination — not
hand-picked after seeing results. Every observed tag (manually decoded
from `BitStream` at `bs.pos = 160 + hash_extra_bits`, reading 4 bits,
independent of `decode_rpc`, which does not currently surface this field
at all) matched its prediction exactly, including:
- All four TRUNC tags (`RPC_B`→0, `RPC_IC`→4, `RPC_D`→8, `RPC_M`→12)
- The EXACT case (`RPC_A`→4)
- The SHORT/≤6-byte-identifier case (`BaseRpc`→4)
- Three PAD tags at five different `r` offsets, with two tags each
  confirmed at *two independent* `r` values (`RPC_K` r=4 and `RPC_J` r=6
  both →4; `RPC_Q` r=5 and `RPC_I` r=3 both →8; `RPC_C` r=7→12) — a
  cross-check the rule wasn't required to pass but did.
- PAD+tag0 was excluded from the run entirely: working out the
  padding-codeword math (fixed 16-bit code `0101011110001101`) shows
  every PAD case reads its 2 tag bits from one of only 5 fixed windows
  of that constant, and none of those 5 windows is `00` — i.e. PAD+tag0
  is structurally unreachable, not merely unsampled. This is itself a
  falsifiable prediction: a future capture showing PAD+tag0 would
  falsify the padding-codeword model specifically (not just the overall
  rule).
- The low 2 bits of the tag nibble were 0 in all 11 frames (consistent
  with every prior observation; still not proven to be structurally
  required, just never seen otherwise).

Fixture: `docs/research/fixtures/method-tag-phase1-confirmation.csv`
(doubles as the Phase 3 conformance fixture, item 15 below).

6. One class, ~10-12 names, all predictions computed *before* the
   capture. Name selection driven by the rule's boundary/spill-value
   space, not alphabetical adjacency (H3 is dead — position ≡0 mod 4
   already carries tags `{4,4,8,0}`): for each of the four 2-bit spill
   values, one TRUNCATE name and one PAD name, plus one EXACT-fit name
   (like `NetworkPlayer`) and one ≤6-byte-identifier/SHORT name (like
   `BaseRpc`). Signatures all `(int)` — signature diversity buys
   nothing here (rule is name-only, and F2 already falsified
   signature-determines-tag separately). Single class — H6
   (per-class offset) is already dead and the rule has no class input.
   At most one permuted-order pair as a sanity row (the cross-build
   evidence already closes the ordering question). Log the full tag
   nibble per frame (not just the top 2 bits) to opportunistically
   characterize the low 2 bits per item 3 above.
7. A single hand-written experiment file for this — the
   template/generator/driver-loop pipeline from the original Phase 1b
   idea is over-engineering for a 12-name confirmation run. Defer that
   machinery; only build it if Phase 1 produces a genuine mismatch and
   exploration has to reopen.
8. Build the flat CSV fixture as part of this run:
   `name, ident_hex, predicted_tag, observed_tag, boundary_case
   (TRUNC/PAD/EXACT/SHORT), match`. This doubles as the Phase 3
   conformance fixture (item 15 below).

### Phase 2 — Behavioral accept/reject test (mirrors the original decisive RPC_Float test) — ~~DONE~~

9. Hand-craft a first-use send for a name Unity has never seen using
   the rule's predicted tag (expect accept) and, separately, a
   deliberately wrong tag (expect reject) — no harness needed, just a
   raw crafted packet in the style of `wrong-index-server.py`.

**Result, with an important methodological correction along the way.**

First attempt (`experiments/RpcTagPhase2Experiment.cs` +
`scripts/rpc-tag-phase2-server.py`): two brand-new names
(`RPC_Phase2Accept`, `RPC_Phase2Reject`) added via runtime
`AddComponent` onto `ctx.SecondRpcNetworkView` (scene ID 2, routing
constant `0x0004` — chosen so Loader's own `PrimaryNetworkView` stayed
untouched and its `RPC_Gamma` remained available as a ready-ping, per
`scripts/tag-collision-server.py`'s pattern). Sent `RPC_Phase2Accept(777)`
with the rule's predicted (correct) tag 8, then `RPC_Phase2Reject(999)`
with a deliberately wrong tag — first 0, then (after 0 turned out to be
an empty/arbitrary choice) 8 (colliding with the slot `RPC_Phase2Accept`
had just claimed). **Both attempts dispatched cleanly regardless of the
wrong tag** — `[RPC] RPC_Phase2Reject(999) from 0` appeared both times,
never an `Internal RPC error`. This looked at first like a direct
contradiction of the original `RPC_Float` finding.

Before concluding `method_tag` is cosmetic, ran two control tests using
*only* Loader's own statically-compiled `[RPC]` methods (no experiments-DLL
type on the receiving side at all — `experiments/WrongIndexExperiment.cs`
unmodified as the client, which already sends `RPC_Int(-1)` as a ready
ping and does nothing else):

- **Reject control** (`scripts/rpc-tag-phase2-control.py` /
  `run-rpc-tag-phase2-control.sh`): sent `RPC_Float(1.23)` with tag
  forced to 8 (real tag is 12). Result: `Internal RPC error. Invalid RPC
  index, function not registered.` — the original finding reproduces
  exactly, today, unmodified.
- **Accept control** (`scripts/rpc-tag-phase2-accept-control.py` /
  `run-rpc-tag-phase2-accept-control.sh`): sent `RPC_Beta(555)` with its
  real, correct tag (4, no override). Result: `[RPC] RPC_Beta(555) from
  0` — clean dispatch, no error.

So for statically-compiled `[RPC]` methods, the accept/reject behavior is
exactly as expected and exactly reproduces the original decisive test:
correct tag → accept, wrong tag → reject. **The divergence is real, but
it's about the receiver's type, not about the rule.** Every RPC method
`[RPC]`-declared in Unity's normal deployment shape — a MonoBehaviour
subclass compiled into the project and present in the scene at domain
load — behaves like `RPC_Float`/`RPC_Beta`. Only a class discovered
purely via a runtime `AddComponent` (invisible to whatever reflection
scan Unity runs at domain load, since it doesn't exist yet at that point)
skips tag validation on receipt.

**Working model, consistent with all four results above (not just the
Loader ones):** Unity does not implement `method_tag` as a shared
slot-occupancy table across methods (that would make `RPC_Alpha` /
`RPC_Beta` / `RPC_Gamma` / `RPC_NetworkPlayer` — which all real-tag to 4
simultaneously in ordinary gameplay — mutually exclusive, which they
plainly aren't). Instead, at domain load Unity's own reflection scan
computes an expected tag per `[RPC]` identifier it can see statically,
and on receiving a first-use RPC it cross-checks the wire tag against
*that specific identifier's own* precomputed expectation — reject on
mismatch, regardless of any other method's tag. A class that doesn't
exist yet at domain-load time has no entry in that table, so there is
nothing to cross-check against, and Unity accepts whatever tag arrives
for it. (The original doc's "occupied slot" phrasing was a reasonable
read of the `RPC_Int`/`RPC_Void` "worked by luck" cases, but "matches its
own expected value" explains both those cases and today's four results
without needing an exclusivity assumption the known tag-collision
gameplay pattern already falsifies.)

**Consequence for Phase 1's already-recorded 11/11 result:** unaffected.
Phase 1 tested what tag *Unity itself chooses to embed as sender* for a
new name — a question about `Unity`'s own first-use encoding path, which
is one shared code path regardless of receiver-side validation
differences. Phase 2 is the complementary receiver-side validation
question, and it now has its own clean, if more nuanced, answer.

**Consequence for Phase 3 (below):** the plan's item 16 reinterpretation
("rejection means identifier-match failure, not slot collision") holds
up, and should additionally note the domain-load-vs-runtime-AddComponent
distinction discovered here, since any future harness work relying on
runtime `AddComponent` (as Phase 1/1a's own approach does) must not be
read as validating receiver-side tag-checking behavior — only sender-side
tag emission.

### Phase 3 — Propagate the fix

10. Add `compute_method_tag(method_name)` to `protocol/unity_protocol.py`
    (reuse `get_codes()`/Huffman machinery already in
    `compute_method_id` — don't duplicate it).
11. Replace `encode_rpc_first_use`'s `METHOD_TAG_MAP.get(...)` fallback
    (`protocol/unity_protocol.py:466-479`). Per Fable: keep a slim
    override, demote its role — `compute_method_tag` is the default
    path; `register_method_tag` stays as an explicit per-name override
    that takes precedence and **logs a warning whenever the override
    diverges from the computed value** (this doubles as the detection
    channel if the rule ever fails in the wild). Remove everything
    predicated on the old "opaque, capture per build" model:
    `_tag_fallback_warned` and any "missing tag" code paths — a tag can
    no longer be missing. Revisit after Phase 2: if the override is
    never actually used, delete it in a follow-up cleanup commit rather
    than keeping it as a permanent just-in-case shim.
12. `scripts/extract-method-indices.cs`: per Fable, don't port the rule
    to C# — just **stop emitting a tag field entirely**. Tags are
    computed at runtime from the name in Python/TS now; a third
    implementation in the Cecil tool is pure drift surface with no
    consumer.
13. Check `ts/src/unity/rpc.ts` for an equivalent per-build
    `METHOD_TAG_MAP`/fallback and apply the same fix if present.
14. `tools/decode_pcap.py`: surface `method_tag` on first-use frames
    AND compute the expected tag when the name is resolvable, emitting
    a match/mismatch flag — turns every future capture into a passive
    regression test of the rule for free.
15. Pin the conformance fixture (13 Loader names + `BaseRpc` +
    `DerivedRpc`, plus `ReceiveSerializeEvent` once independently
    verified, plus the Phase 1 ~12-name set) as a shared test fixture
    for both the Python and TS implementations, so the two encoders
    can't silently drift apart.
16. Update `docs/research/2026-07-12-method-tag-real-derivation.md`'s
    conclusion, the wire-format spec's §3.3.1 and spec-status Known
    Issue #1, and `docs/plans/method-tag-collision-guard.md`'s errata —
    **reinterpretation, not just correction**: under the rule, "tag
    collision" isn't a slot-table collision — the tag is part of
    identifier validation, so rejection means identifier-match failure,
    and same-tag collisions between distinct names are inherent and
    harmless. `docs/plans/method-tag-collision-repro.md`,
    `tag-collision-server.py` / `tag-collision-fixed-server.py`, and
    `TagCollisionExperiment`'s conclusions need re-reading under this
    model — some of their scenarios may be testing a mechanism that
    doesn't exist.
17. Update `CLAUDE.md`: the "Method-Index / Subsequent-Use Testing"
    section's `method_tag` framing, AND (per Fable) the "Consequence
    for `method_tag` specifically" paragraph and the "do not re-derive"
    carve-out language in "Why the Protocol Must Assume Divergent
    Assemblies" — record the resolution and where it's documented, so
    a future session doesn't re-open the search from the stale framing.

## Fable Review

Approved 2026-07-13, no blocking concerns — proceed to Step 3 (implement
Phases 0.4, 1a, 1, 2) and Step 4 (Opus implementation review) before
Phase 3 code propagation.
