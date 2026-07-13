# method_tag Is Not `method_index & 0x0F`: Empirical Ground Truth

Date: 2026-07-12

## What This Document Covers

`docs/plans/method-tag-collision-guard.md` (shipped in `e3dab23`) documents
and relies on the formula `method_tag = method_index & 0x0F` as an
already-confirmed fact. This investigation set out to root-cause a
different, seemingly unrelated symptom — first-use RPC dispatch silently
failing for every Loader test method except `RPC_Void` and `RPC_Int` when
sent by our Python implementation to a real Unity 2018.1.6f1 client — and
found that the guard's premise is wrong. `method_tag` is not derivable from
`method_index` at all. This document records the evidence.

## Symptom

A hand-crafted first-use RPC for `RPC_Float(1.0)`, sent as the *only* RPC on
a fresh connection (so no other message could interfere), was rejected by a
real Unity client:

```
Internal RPC error. Invalid RPC index, function not registered.
```

`RPC_Void` and `RPC_Int`, sent the same way, dispatched correctly. Every
other Loader RPC method failed identically to `RPC_Float`.

## Ruled Out

- **Huffman hash-length correlation** — `RPC_Void` (succeeds) and
  `RPC_Float` (fails) both have `hash_extra_bits=24`; identical, so hash
  length isn't the discriminator.
- **`remaining_count` field** — byte-for-byte comparison of a hand-crafted
  `RPC_Float` first-use message against a real Unity-to-Unity ground-truth
  capture showed every field matching except one nibble.
- **`method_tag` being safely ignorable** — decisively disproven: forcing
  the real captured tag (12, instead of our computed 8) into an otherwise
  identical hand-crafted `RPC_Float` first-use send made a real Unity
  client accept it (`[RPC] RPC_Float(1) from 0`, no error). See
  `/tmp/.../isolate-realtag.py` (reproduced below) for the exact test.
- **Alternate closed-form derivations of the tag** — tested `idx mod 4`,
  `(idx/4) mod 4`, `RID mod 16`, param-signature-based grouping, and a hash
  of the method-hash bytes. None fit all 13 data points below (e.g.
  `RPC_Alpha` and `RPC_Int` share signature `['int']` but have different
  real tags 4 vs 8; a mod-4 cyclical pattern that fit the first 7 points
  broke at `RPC_IntFloatString`).

## The Decisive Test

```python
old_tag = up.METHOD_TAG_MAP.get('RPC_Float')
up.METHOD_TAG_MAP['RPC_Float'] = 12   # real captured value, was 8
payload, bits = encode_rpc_first_use(
    'RPC_Float', [1.0], view_id=0, timestamp_ms=uptime_ms, mode=RPCMode.Server,
    target_view=TARGET_VIEW)
server._raknet.send_to(addr, payload, Reliability.RELIABLE_ORDERED, bit_length=bits)
```

Sent as the sole RPC in a fresh connection to a real Unity 2018.1.6f1
client (server role: netns `unitynet`, real Unity Player as client). Result:

```
[RPC] RPC_Float(1) from 0
```

No `Internal RPC error`. This is a controlled, single-variable change from
a previously-failing send (only the tag nibble changed) to a
succeeding one — proof that `method_tag` is load-bearing and that our
computed value was wrong, not merely "one possible correct value among
several."

## Ground Truth Table

Real `method_tag` values extracted from real Unity-to-Unity captures
(`captures/Rpc*Experiment-2026062*.pcap`, `captures/RpcVoidExperiment-recapture.pcap`),
by decoding the first-use RPC's 52-bit internal metadata block at bit
offset `160 + hash_extra_bits` (4 bits), compared against
`METHOD_INDEX_MAP`'s formula-derived value (`method_index & 0x0F`):

| Method | `method_index` | computed (`idx & 0x0F`) | **real tag** | match? |
|---|---|---|---|---|
| RPC_Void | 80 | 0 | **0** | yes (coincidence) |
| RPC_Int | 84 | 4 | **8** | no |
| RPC_Float | 88 | 8 | **12** | no |
| RPC_String | 92 | 12 | **0** | no |
| RPC_Vector3 | 96 | 0 | **8** | no |
| RPC_Quaternion | 100 | 4 | **8** | no |
| RPC_Bytes | 104 | 8 | **12** | no |
| RPC_IntFloatString | 108 | 12 | **8** | no |
| RPC_NetworkPlayer | 112 | 0 | **4** | no |
| RPC_NetworkViewID | 116 | 4 | **8** | no |
| RPC_Alpha | 120 | 8 | **4** | no |
| RPC_Beta | 124 | 12 | **4** | no |
| RPC_Gamma | 128 | 0 | **4** | no |

12 of 13 computed values are wrong. `RPC_Void`'s match is coincidental (both
happen to be 0) — not evidence the formula is right, since every other
method disproves it.

This also explains the original symptom precisely: `RPC_Void` (tag 0,
correct by coincidence) and `RPC_Int` (tag computed as 4, real 8 — wrong,
but tag 4 happened to be an empty/unused slot on a fresh connection, so the
wrong guess didn't collide with anything) both worked "by luck." Every
other method's wrong guess collided with a real, already-populated tag
slot and silently misdispatched or was rejected.

### `RPC_Void`'s capture required a build fix

The existing old capture of `RpcVoidExperiment` (`RpcVoidExperiment-20260626-031432.pcap`)
contains no RPC-type frames at all. Root cause: `RpcVoidExperiment.cs` called
`ctx.PrimaryNetworkView.RPC("RPC_Void", RPCMode.Server)` with zero
variadic arguments. Mono's `mcs` (6.8.0.105) compiles a zero-length
`params object[]` expansion to a call to `System.Array.Empty<object>()`
regardless of `-optimize-` or `-langversion`; that method doesn't exist in
the 2018.1.6f1 Mono runtime's `mscorlib.dll`, so the client crashed with
`MissingMethodException` before ever sending the RPC.
`TagCollisionExperiment.cs` already carries a comment noting this same trap
and works around it by never calling a zero-arg RPC. Fixed in
`experiments/RpcVoidExperiment.cs` by passing an explicit `new object[0]`
instead of relying on params-array expansion — an explicit array literal
compiles to a `newarr` instruction, not `Array.Empty<T>()`. Confirmed via a
standalone `mcs` compile + `monodis` inspection before applying the fix.

## What This Means

- `method_tag` cannot be derived from `method_index`, or from any other
  whole-assembly compiled property of the method (signature, RID) tested
  so far.
- The only 4 values ever observed across 13 methods are 0, 4, 8, 12 — always
  a multiple of 4 — suggesting some kind of small internal slot table, but
  the *assignment* of a specific method to a specific slot is opaque from
  outside Unity's runtime. This is a hypothesis, not confirmed.
- This directly contradicts `docs/plans/method-tag-collision-guard.md`'s
  premise, which treated the `method_index & 0x0F` formula as settled fact
  and removed the only API (`register_method_tag(s)`) that could set a tag
  independent of index. See `docs/plans/method-tag-real-derivation-fix.md`
  for the corrective plan.

**Update, 2026-07-12 (later the same day) / 2026-07-13:** the paragraph
above originally continued by concluding the tag "must be captured
empirically from a real Unity-to-Unity pcap for each compiled assembly" —
i.e. that it's an opaque per-build constant with nothing more to say about
it, the same way `method_index` is. **That conclusion was wrong**, and is
kept struck-through-in-spirit here rather than deleted, as the record of a
resting point that didn't hold up. `method_tag`'s upper 2 bits turned out
to be spillover from the *same* Huffman/StringCompressor bitstream
`compute_method_id` builds for the method hash: continue the bitstream
past the byte-aligned cap that truncates the hash (padding with repeats of
`codes[0]`, the same pad source `compute_method_id` itself uses) and the
next 2 bits, shifted into the tag's high bits, are the real tag — a
name-only derivation with no dependency on signature, RID, or compile
order. This reproduces all 13 ground-truth values above exactly, plus 2/2
out-of-sample (`BaseRpc`→4, `DerivedRpc`→12) and 11/11 blind predictions
against a fresh capture. See
`docs/plans/method-tag-shared-derivation-hypotheses.md` for the full
derivation and validation, and `compute_method_tag()`
(`protocol/unity_protocol.py`) / `computeMethodTag()`
(`ts/src/unity/method-hash.ts`) for the implementation now used by
`encode_rpc_first_use`/`encodeRpcFirstUse` as the default (with
`register_method_tag(s)`/`registerMethodTag(s)` kept as an explicit,
logged-on-divergence override for the rare case a specific compiled
assembly needs one — not as the primary mechanism). The
per-build-empirical-capture requirement remains genuinely true for
`method_index`; it was never true for `method_tag`, this document's
original conclusion notwithstanding.

## Related Files

- `protocol/unity_protocol.py` — `METHOD_TAG_MAP`, `_register_loader_assembly()`
- `ts/src/unity/rpc.ts` — TS mirror
- `scripts/extract-method-indices.cs` — static extraction tool, emits the
  same wrong formula for `tag`
- `docs/research/unity-legacy-networking-wire-format.md` §3.3.1
- `docs/research/spec-status.md` — §3.3.1 status row, Known Issue #1
- `docs/plans/method-tag-collision-guard.md` — premise corrected by this doc
- `docs/plans/method-tag-collision-repro.md`,
  `scripts/tag-collision-server.py`, `scripts/tag-collision-fixed-server.py`
  — collision scenarios built on the wrong grouping, need the real groups
  from the table above
