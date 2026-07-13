# Fix: method_tag Is Not Derivable From method_index

## Context

`docs/research/2026-07-12-method-tag-real-derivation.md` empirically
disproves the formula `method_tag = method_index & 0x0F`, which
`docs/plans/method-tag-collision-guard.md` (shipped in `e3dab23`) treated
as settled fact. Ground truth from real Unity-to-Unity captures shows the
formula produces the wrong tag for 12 of the 13 Loader test RPC methods.
A live test against a real Unity 2018.1.6f1 client confirmed causally that
sending the wrong tag causes silent misdispatch or rejection, and sending
the real captured tag fixes it.

This plan fixes the derivation at its source (rather than working around
symptoms) and corrects every doc/API/test that currently asserts the wrong
formula as fact.

## Root Cause Recap

- `method_tag` cannot be derived from `method_index`, method name,
  signature, or RID — no closed-form formula fits the 13 known data
  points (see research doc's ground truth table).
- It must be captured empirically from a real Unity-to-Unity pcap, per
  compiled assembly.
- The `method-tag-collision-guard.md` plan removed `register_method_tag(s)`
  on the reasoning "if a caller can compute a correct tag, they already
  have the index" — this reasoning assumed the formula was correct. It
  isn't, so that API needs to come back, this time as the *only* correct
  way to supply a tag that isn't in our hardcoded ground-truth table.

## Fix Components

### 1. `protocol/unity_protocol.py`: hardcode real tags for the Loader assembly

Replace the formula loop at lines 232-234:

```python
METHOD_TAG_MAP = {}
for _name, _idx in METHOD_INDEX_MAP.items():
    METHOD_TAG_MAP[_name] = _idx & 0x0F
```

with a literal table sourced from the ground-truth capture data (research
doc table), applied inside `_register_loader_assembly()` (or immediately
after) instead of a computed default:

```python
_LOADER_REAL_TAGS = {
    'RPC_Void': 0,
    'RPC_Int': 8,
    'RPC_Float': 12,
    'RPC_String': 0,
    'RPC_Vector3': 8,
    'RPC_Quaternion': 8,
    'RPC_Bytes': 12,
    'RPC_IntFloatString': 8,
    'RPC_NetworkPlayer': 4,
    'RPC_NetworkViewID': 8,
    'RPC_Alpha': 4,
    'RPC_Beta': 4,
    'RPC_Gamma': 4,
}
```

`compute_method_tag(method_index)` (line ~237) computes the same wrong
formula and has no remaining legitimate caller once this lands — remove it
rather than leave a function whose name implies correctness it doesn't
have. Grep both languages for callers before removing to confirm nothing
else depends on it (confirmed zero callers as of this plan's writing).

**Definition-order hazard:** `METHOD_TAG_MAP = {}` is currently *defined*
at line 232, after `_register_loader_assembly()` is called at line 230. If
the real-tag table is applied "inside" `_register_loader_assembly()`
(rather than as a step immediately after it returns), `METHOD_TAG_MAP`
must be hoisted above that call first, or the function body will raise
`NameError` on first use. Whichever ordering is chosen, keep
`METHOD_INDEX_MAP`/`INDEX_TO_METHOD` population and `METHOD_TAG_MAP`
population in the same function or immediately adjacent, so the Loader
assembly's three tables are always populated together.

### 2. Stop deriving tag as a side effect of index registration

`register_method_indices()` (Python, `unity_protocol.py` ~line 147) and
`registerMethodIndices()` (TS, `rpc.ts` line 139) currently do:

```python
METHOD_TAG_MAP[name] = idx & 0x0F
```

Remove this line from both. Registering a method's index must not
silently guess its tag. Same for `learnMethodIndex()` (TS, line 123) —
learning an index from a batch-index message tells us nothing about the
real tag either, since the tag is not a function of the index; stop
writing to `METHOD_TAG_MAP` there too.

After this change, `encode_rpc_first_use`'s existing fallback
(`METHOD_TAG_MAP.get(method_name, 0)`) means any method without an
explicitly-registered real tag defaults to sending tag 0. This is exactly
as much of a guess as `idx & 0x0F` was — no more, no less principled — but
it stops presenting a wrong-but-confident-looking derivation as if it were
grounded in the method's real index. Add a one-time-per-method-name log
warning in `encode_rpc_first_use` (mirrored in TS `encodeRpcFirstUse`) when
falling back to the default, so callers sending first-use RPCs to a real
Unity client for methods with no captured tag get a visible signal that
they're gambling on an empty slot rather than silence. Track "already
warned" names in a module-level set (mirrors the pattern already used for
the repeated-first-use warning in `unity_server.py`/`unity_client.py`).
Export a clear/reset function for this set (e.g.
`_reset_tag_fallback_warnings()` in Python, an internal-but-test-reachable
equivalent in TS) so tests that assert the warning fires are not
order-dependent on whatever other test happened to trip the same
method-name warning first in the same process. Any test asserting the
warning must call the reset function in its own setup, not rely on running
first.

### 3. Reinstate `register_method_tag(s)` / `registerMethodTag(s)`

Bring back the API removed by `method-tag-collision-guard.md`, unchanged in
shape (`register_method_tag(name, tag)` / `register_method_tags({...})` in
Python touching only `METHOD_TAG_MAP`; TS mirror in `rpc.ts` + exported
from `index.ts`). This time it is the *documented, correct* way to supply
a tag captured from a real pcap for a game-specific method that isn't in
the hardcoded Loader table — not a footgun, because there is no longer a
"derive it from the index instead" alternative to steer callers toward.

Update the docstring to explain *why* this exists (tag is independent of
index, must come from a real capture) instead of the old docstring's
implicit assumption that index implies tag.

### 4. `scripts/extract-method-indices.cs`: stop emitting a fabricated tag

This tool statically walks the MethodDef table via Mono.Cecil and
currently emits `int tag = index & 0x0F;` alongside the (correct) index.
Since tag cannot be derived from static IL metadata, remove that field
from the tool's output entirely (don't replace it with a placeholder that
looks like real data). Add a comment at the removal site explaining that
`method_tag` must come from a real Unity-to-Unity capture of that specific
compiled assembly, decoded per
`docs/notes/unity-raknet-capture-decode-playbook.md`, and registered via
`register_method_tag(s)` — not computed from this tool's output.

### 5. Documentation corrections

- `docs/research/unity-legacy-networking-wire-format.md` §3.3.1 (lines
  365-390): rewrite the `method_tag` row and the paragraph below the table.
  Remove the `method_index & 0x0F` formula claim. State plainly that the
  tag is empirically opaque, must be captured per-assembly from a real
  pcap, and link the ground-truth table in the new research doc as the
  known values for the Loader test assembly. Also fix line 348's table
  entry in §3.3 with the same correction.
- `docs/research/spec-status.md`: update lines ~42, ~50-55, ~131, ~149,
  and Known Issue #1 (~157-179). Change "derivation confirmed" /
  "load-bearing, not cosmetic" framing (which was directionally right
  about load-bearing-ness but wrong about derivation) to: derivation is
  **not** a formula, must be captured empirically; Loader assembly's 13
  real values are known and hardcoded; other assemblies need their own
  captures. Update the Known Issue #1 "Workaround" paragraph — it
  currently says "always register real method indices... rather than
  relying on the first-use path" as if that fixes the tag; it doesn't,
  since tag isn't derived from index. Replace with: register real
  captured tags via `register_method_tag(s)` for any game-specific method
  that will be sent first-use to a real Unity client.
- `docs/plans/method-tag-collision-guard.md`: add an "Erratum
  (2026-07-12)" section at the top (don't rewrite the historical body —
  it accurately records what was believed and done at the time) stating:
  the premise `method_tag = method_index & 0x0F` is empirically disproven
  (link research doc); `register_method_tag(s)` has been reinstated by
  `docs/plans/method-tag-real-derivation-fix.md` for this reason; Fix 2
  (repeated-first-use-per-peer warning) remains valid and unchanged by
  this correction — that mechanism doesn't depend on the tag formula being
  right, only on whether an index was ever learned.
- `docs/research/2026-06-27-rpc-constant-field-investigation.md` line 135
  asserts "The 4-bit method_tag in first-use RPC messages equals
  `method_index & 0x0F`" as fact. Add a one-line erratum pointer to the
  new research doc, matching the historical-doc convention used above for
  `method-tag-collision-guard.md` (don't rewrite the surrounding
  investigation, which is otherwise unrelated to method_tag).

### 6. Correct the repro scripts' wrong grouping data

`scripts/tag-collision-server.py` and `scripts/tag-collision-fixed-server.py`
(Experiment A / B drivers for the paused `docs/plans/method-tag-collision-repro.md`
work) assert a specific tag grouping in their docstrings and build their
scenarios around it:

```
tag0: RPC_Void, RPC_Vector3, RPC_NetworkPlayer, RPC_Gamma
tag4: RPC_Int, RPC_Quaternion, RPC_NetworkViewID
tag8: RPC_Float, RPC_Bytes, RPC_Alpha
tag12: RPC_String, RPC_IntFloatString, RPC_Beta
```

This is wrong per the ground-truth table above. Update both files'
docstrings and scenario tables to the real groups:

```
tag0:  RPC_Void, RPC_String
tag4:  RPC_NetworkPlayer, RPC_Alpha, RPC_Beta, RPC_Gamma
tag8:  RPC_Int, RPC_Vector3, RPC_Quaternion, RPC_IntFloatString, RPC_NetworkViewID
tag12: RPC_Float, RPC_Bytes
```

Beyond the grouping tables, both files also contain prose rationale
sentences built on the wrong groups, which are equally false and must be
corrected in the same pass, not just the tables:
`tag-collision-fixed-server.py` claims "RPC_Float and RPC_Alpha already
coincidentally share tag=8" (false under ground truth — RPC_Float is
tag12, RPC_Alpha is tag4); `tag-collision-server.py` claims "RPC_Gamma
(tag 0)... never contaminates a test pair" (false — RPC_Gamma is tag4).
Rewrite these sentences to describe the real groupings above, not just
the tables they sit next to.

This plan only corrects the *data and rationale prose* in these files so
they stop asserting falsehoods — it does not redesign or re-run the
scenarios. Actually redesigning/executing Experiment A/B against the
corrected groups is tracked separately (existing tasks #2/#3, paused
pending this fix) and resumes after this plan's pipeline completes.

### 7. TypeScript mirror

Every Python change above (1, 2, 3) has a corresponding change in
`ts/src/unity/rpc.ts` and `ts/src/index.ts` (for the reinstated
`registerMethodTag`/`registerMethodTags` exports). Keep both
implementations byte-for-byte consistent per the project's cross-conformance
testing convention.

## Tests

### Python (`tests/test_unity_protocol.py`)

- `test_method_tag_registration` (line 625) currently asserts
  `register_method_indices({'RPC_Int': 8})` derives `method_tag=8` — this
  tests the behavior being removed. Rewrite to call
  `register_method_tag('RPC_Int', 8)` directly and assert the same wire
  output; add a companion assertion that `register_method_indices` no
  longer touches `METHOD_TAG_MAP` (register an index for a method with no
  prior tag entry, confirm `METHOD_TAG_MAP.get(name)` is still `None`/absent).
- `test_method_tag_defaults_to_zero` (line 650) stays conceptually valid
  (untagged methods still default to 0) but should additionally assert the
  one-time warning fires (component 2). It currently does
  `METHOD_TAG_MAP.pop('RPC_Int', None)` with no restore, unlike its
  neighboring tests — add save/restore of the popped entry (and call the
  component-2 warning-reset function in setup) so it doesn't leak state
  into tests that run after it.
- `test_register_method_indices_bulk_derives_tags` (line 663) tests
  exactly the behavior being removed — rewrite as
  `test_register_method_indices_does_not_derive_tags`, asserting
  `METHOD_TAG_MAP` is unaffected by a bulk index registration.
- Add `test_loader_assembly_tags_match_ground_truth`: asserts
  `METHOD_TAG_MAP` for all 13 built-in Loader methods matches the research
  doc's table exactly (regression test against silently reintroducing the
  formula).

### Cross-conformance (`tests/test_cross_conformance.py`)

- `GOLDEN['fu_int_42']`, `GOLDEN['fu_int_42_others']`,
  `GOLDEN_CONSTANT['fu_int_42_const2640']`, `GOLDEN_RELAY['fu_int_42_relay']`
  all encode `RPC_Int` first-use with the *default* (no explicit
  registration) tag. Once the Loader table changes RPC_Int's default tag
  from 4 (wrong) to 8 (real), these hex vectors' tag nibble changes.
  Regenerate them from the TS implementation (the documented source of
  truth for these golden vectors) after the TS fix lands, not by hand —
  confirm via `ts/scripts/interop-test.ts` or an equivalent one-off encode
  + hex dump, then update the Python-side hex constants to match.
  `GOLDEN['fu_void']` is unaffected (`RPC_Void`'s real tag is 0, same as
  the old wrong default).
- `test_first_use_with_method_tag_matches_ts` (`GOLDEN_TAG['fu_int_42_tag8']`,
  line 163) currently calls `register_method_indices({name: tag})` to
  hijack the derivation into producing tag 8 — this only worked because
  the tag was piggybacking on the index formula. Rewrite to call
  `register_method_tag(...)` directly, but change the registered tag from
  8 to a **non-default** value (e.g. 12) instead of keeping 8: once this
  plan lands, 8 becomes RPC_Int's hardcoded default tag, so a test that
  registers 8 explicitly would pass even if `register_method_tag` were a
  no-op — it would no longer exercise the override path at all. Rename the
  golden vector (e.g. `fu_int_42_tag12`) and regenerate its expected hex
  from the TS implementation to match the new registered value.

### TypeScript

No existing TS tests assert specific tag values (checked
`ts/test/unity-protocol.test.ts`, `ts/test/rpc-schema.test.ts` — neither
references `methodTag`/`Tag`). Add coverage mirroring the new Python tests:
`registerMethodTag`/`registerMethodTags` set only `METHOD_TAG_MAP`;
`registerMethodIndices`/`learnMethodIndex` no longer touch it; the 13
built-in Loader tags match the ground-truth table.

### Decode path

`decode_rpc`/`decodeRpc` don't read or validate the tag nibble at all
(confirmed by reading both implementations) — no decode-side test changes
needed; this plan only affects encoding and registration.

## Non-Goals

- Determining the actual Unity/Mono mechanism that assigns a method to a
  tag slot (hypothesized as some kind of 4-slot table, unconfirmed). Not
  required to unblock a correct practical fix, which relies on captured
  values, not a derived formula.
- Re-running or redesigning the tag-collision repro experiments
  (`docs/plans/method-tag-collision-repro.md` tasks #2/#3) — only their
  drivers' factually-wrong data tables are corrected here (component 6).
- Any change to the wire format itself (bit widths, offsets) — this is a
  registration/derivation-logic fix only, not a framing change.

## Exit Criteria

- [ ] `protocol/unity_protocol.py`: `METHOD_TAG_MAP` for the Loader
      assembly matches the ground-truth table exactly; `compute_method_tag`
      removed (after confirming no remaining callers);
      `register_method_indices` no longer writes `METHOD_TAG_MAP`.
- [ ] `register_method_tag`/`register_method_tags` reinstated in
      `protocol/unity_protocol.py`, exported the same way they were before
      removal.
- [ ] `encode_rpc_first_use` warns once per method name when falling back
      to the default tag (0) for a method with no registered tag.
- [ ] `ts/src/unity/rpc.ts` / `ts/src/index.ts`: all of the above mirrored
      (`registerMethodTag`/`registerMethodTags` reinstated and exported,
      `registerMethodIndices`/`learnMethodIndex` no longer touch
      `METHOD_TAG_MAP`, Loader table matches ground truth, one-time warning
      in `encodeRpcFirstUse`).
- [ ] `scripts/extract-method-indices.cs` no longer emits a `tag` field;
      a comment explains why and points to the correct registration path.
- [ ] `docs/research/unity-legacy-networking-wire-format.md` §3.3/§3.3.1
      corrected per component 5.
- [ ] `docs/research/spec-status.md` corrected per component 5 (all
      listed line references).
- [ ] `docs/plans/method-tag-collision-guard.md` has an Erratum section
      per component 5; Fix 2 (repeated-first-use warning) explicitly
      called out as still valid.
- [ ] `scripts/tag-collision-server.py` / `scripts/tag-collision-fixed-server.py`
      grouping tables and docstrings corrected per component 6.
- [ ] All Python test changes in the Tests section applied; full suite
      (`pytest`) passes.
- [ ] All TS test changes applied; full suite (`vitest` via the repo's
      normal TS test command) passes.
- [ ] Cross-conformance golden vectors regenerated from TS and verified
      byte-identical between Python and TS for the affected `fu_int_42*`
      entries; `fu_void` and non-RPC_Int vectors unchanged.
