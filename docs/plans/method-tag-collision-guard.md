# method_tag Collision Guard

## Context

`docs/research/unity-legacy-networking-wire-format.md` §3.3.1 documents
`method_tag` (4 bits in the first-use RPC metadata block) as the low
nibble of the method's real Unity `method_index`
(`method_tag = method_index & 0x0F`). `docs/research/spec-status.md`
currently calls it "Cosmetic — Unity accepts 0", based on the observation
that Unity's own decoder doesn't reject `method_tag = 0`.

The distance-server sibling project reported (via status-inbox, evidence in
their `docs/plans/rpc-dispatch-matrix-full-method-coverage.md`) that this is
wrong: `method_tag` is **not safely ignorable** when *we* are sending a
first-use RPC to a real Unity client. Their dispatch matrix showed
`RPC_BROADCAST_ALL` and `RPC_TARGETED` sharing `methodTag = 8`, causing 9/12
`RPC_BROADCAST_ALL` sends to silently misdispatch to
`ReceiveTargetedEventServerToClient` on the real client. `RPC_SERIALIZE`
(tag 4) showed a matching 0/12, hypothesized to collide with an unlogged
`ReceiveServerNetworkTimeSync` handler also on tag 4.

## Root Cause (confirmed by code inspection, this repo)

`ts/src/unity/rpc.ts` / `protocol/unity_protocol.py` maintain two
independent maps:

- `METHOD_INDEX_MAP` — the method's real 7-bit Unity index. Populated by
  `registerMethodIndices()`, `learnMethodIndex()`, or the built-in loader
  assembly table. `hasMethodIndex(name)` is true only once a method has an
  entry here.
- `METHOD_TAG_MAP` — the 4-bit tag used when encoding a *first-use* RPC.
  Populated as a side effect of `registerMethodIndices()`/`learnMethodIndex()`
  (`idx & 0x0F`), **or independently via `registerMethodTag(s)`**, which
  touches only `METHOD_TAG_MAP` and never `METHOD_INDEX_MAP`.

`registerMethodTag(s)` was added in Fix 5 of
`docs/research/2026-06-27-protocol-fixes-from-distance-integration.md` as an
escape hatch for callers who know a method's real tag but not its full
index. This is not a legitimate use case: per the wire doc, both values are
`position × 4` — the tag is just the low nibble of the same computation. If
a caller can compute a correct tag, they already have enough information to
compute (or extract, via `scripts/extract-method-indices.sh`) the full
index. In practice, distance-server used `registerMethodTag('RPC_BROADCAST_ALL',
8)` as a guess — copying `RPC_TARGETED`'s known-good tag — without a
matching index registration.

This has two compounding effects:

1. **The tag was simply wrong** (a guess, not derived), producing a
   collision with whatever other method already legitimately owns tag 8 on
   the real client.
2. **`hasMethodIndex('RPC_BROADCAST_ALL')` is permanently false**, because
   `registerMethodTag` never populates `METHOD_INDEX_MAP`. Per
   `server.ts::sendRpcTo` / `client.ts::sendRpc`, this means *every* send of
   that method uses `encodeRpcFirstUse` — it can never transition to
   subsequent-use encoding, so the colliding tag is retransmitted on every
   single send instead of just once.

Neither of these is a wire-format bug — the framing this repo emits matches
the documented layout. It's a **library API footgun**: `registerMethodTag(s)`
lets a caller create a permanently-first-use, arbitrarily-tagged method with
no warning that it will collide with the real Unity dispatch table.

## Fix

Registration-time collision detection was considered and cut: since
`method_index = position × 4`, tags only ever take 4 values (0, 4, 8, C),
so any registry with more than 4 methods *must* have tags collide as a
matter of course — `registerLoaderAssembly()` alone registers 13 built-in
methods across those 4 values. A warning wired into
`registerMethodIndices`/`learnMethodIndex`/`registerLoaderAssembly` would
fire on every legitimate startup, training callers to ignore it. The actual
bug wasn't "two methods share a tag" (normal and expected) — it was "a tag
was set without ever registering the real index it's derived from." Fix 1
below closes that off directly; fix 2 catches the runtime symptom. Neither
needs a collision warning to be effective.

### 1. `registerMethodTag(s)` removed — index registration is the only entry point

Change the signature so a caller must supply the real method_index, not
just the derived tag — this closes off the "tag without index" footgun
entirely:

- TS: `registerMethodIndex(methodName: string, index: number): void` /
  `registerMethodIndices(...)` (existing) become the only entry points that
  touch `METHOD_TAG_MAP`. `registerMethodTag`/`registerMethodTags` are
  removed; `METHOD_TAG_MAP` is derived exclusively from `idx & 0x0F`.
- Python: same — remove `register_method_tag`/`register_method_tags`,
  update `tests/test_unity_protocol.py` and `tests/test_cross_conformance.py`
  call sites to use `register_method_indices`/`register_method_index`
  instead.

This is a breaking API change but removes a function whose only observed
real-world use produced a protocol bug. There is no legitimate call
pattern that has a tag but not the index it's derived from.

Test call sites that need updating:
- `tests/test_unity_protocol.py` line 627 (`register_method_tag('RPC_Int', 8)`)
  and lines 655-657 (`test_register_method_tags_bulk`).
- `tests/test_cross_conformance.py` line 12 (import) and line 167
  (`register_method_tag(name, tag)`), backing golden vector `fu_int_42_tag8`.

These currently call `register_method_tag`/`register_method_tags` against
built-in methods like `RPC_Int`, mutating only `METHOD_TAG_MAP`. Rewritten
to call `register_method_index`/`register_method_indices` instead, they will
also mutate `METHOD_INDEX_MAP` and `INDEX_TO_METHOD` — which, for a
built-in like `RPC_Int`, clobbers its real loader-assembly index and the
decode reverse-lookup map for the rest of the test process. Any test doing
this must save and restore all three maps (`METHOD_TAG_MAP`,
`METHOD_INDEX_MAP`, `INDEX_TO_METHOD`) around the mutation, not just
`METHOD_TAG_MAP` as today, or it will leak state into unrelated tests
running later in the same process.

### 2. Warn on repeated first-use encoding per (peer, method)

In `server.ts::sendRpcTo` and `client.ts::sendRpc` (and their Python
equivalents), track which `(peer, methodName)` pairs have already been sent
via `encodeRpcFirstUse`. If `encodeRpcFirstUse` is invoked again for a pair
already seen, warn **once** per pair (not on every repeat — a stuck-on-first-use
method may be sent at high frequency, and repeated warnings for the same
pair add nothing once the first has fired):

```
[UnityServer] Re-sending first-use RPC for "RPC_BROADCAST_ALL" to the same
peer — method_index is not yet registered/learned for this method, so this
send repeats the (possibly colliding) method_tag instead of switching to
subsequent-use encoding. If this persists, the method is permanently stuck
on first-use encoding.
```

This catches the runtime symptom (stuck-on-first-use) directly, independent
of whether the tag happens to collide, and would have caught distance-server's
bug on the very first repeat send.

Note this is *not* a false-positive risk from the normal first-use →
batch-index → subsequent-use handshake latency: that window is a single
first send followed by (once the peer's 0x07 arrives) subsequent-use
encoding for all following sends. The warning only fires on the *second*
first-use send for the same pair, which only happens when the index never
gets registered/learned at all — the actual bug condition, not the normal
handshake window.

The per-peer tracking set must be evicted alongside existing per-session
state (`rpcReceivedFirstUse`, `peerIndices`, `deltaState`) in the
`onDisconnect` handler in `server.ts`, matching the session-eviction
discipline added in `6e8d6a3` — it must not accumulate across
reconnects/session churn.

## Out of Scope

- Determining the *exact* mechanism of Unity's real first-use dispatch
  cache (per-connection tag slot vs. something else) — distance-server's
  own docs mark this "not confirmed" and it doesn't change what fix is
  actionable here.
- Any change to wire encoding/decoding of `method_tag` itself — the 4-bit
  field's position, width, and derivation formula (`method_tag =
  method_index & 0x0F`) are unchanged and already correctly documented.
- Registration-time tag-collision warnings (cut — see Fix section above;
  tag collisions are an expected, unavoidable property of the 4-bit tag
  space, not a signal worth surfacing on their own).
- `spec-status.md`'s "Cosmetic" framing will be corrected as part of this
  work (doc-only change, not a protocol fix) but the acceptance criteria
  below don't depend on further live Unity captures.

## Exit Criteria

- [ ] TS: `registerMethodTag`/`registerMethodTags` removed from
      `ts/src/unity/rpc.ts` and `ts/src/index.ts` exports. `METHOD_TAG_MAP`
      is written only as a derived side effect of `registerMethodIndices`,
      `learnMethodIndex`, and `registerLoaderAssembly`.
- [ ] TS: `sendRpcTo` (`server.ts`) and `sendRpc` (`client.ts`) warn once
      per (peer, method) on repeated first-use encoding; the tracking set
      is evicted in `onDisconnect` alongside `rpcReceivedFirstUse` /
      `peerIndices` / `deltaState`.
- [ ] Python: mirrored — removal of `register_method_tag`/
      `register_method_tags` from `protocol/unity_protocol.py`, and the
      equivalent repeated-first-use warning wherever the Python send path
      lives (`unity_server.py`/`unity_client.py`), with matching per-session
      eviction.
- [ ] Tests (TS + Python): repeated-first-use warning fires on the second
      first-use send to the same peer for a method with no registered
      index, and does not fire on the first send or on any subsequent-use
      send; existing tests updated to stop calling the removed functions,
      with `tests/test_unity_protocol.py` and `tests/test_cross_conformance.py`
      saving/restoring all three maps (`METHOD_TAG_MAP`, `METHOD_INDEX_MAP`,
      `INDEX_TO_METHOD`) around any mutation of built-in method state.
- [ ] `docs/research/spec-status.md` updated at all locations describing
      `method_tag` as having "unknown derivation" or being "Cosmetic"
      (currently lines ~42, ~50, ~131, and Known Issue #1 ~line 152):
      `method_tag` reframed from "Cosmetic" to "load-bearing on the real
      Unity client; collisions cause silent misdispatch" per
      distance-server's dispatch-matrix evidence.
- [ ] `docs/research/unity-legacy-networking-wire-format.md` §3.3.1's
      "Unity accepts method_tag = 0... zero is a safe default" note amended
      to flag that zero is only "safe" from a decode-acceptance standpoint,
      not from a dispatch-correctness standpoint.
- [ ] All existing test suites (TS + Python) pass.
