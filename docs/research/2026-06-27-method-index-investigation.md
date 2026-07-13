# RPC Method Index: Investigation and Dynamic Learning

Date: 2026-06-27

## What This Document Covers

Unity's legacy networking (`NetworkView.RPC()`, last supported in Unity
2018.1) sends RPC calls over the wire using two encodings:

- **First-use:** includes the method name (as a Huffman hash), sent the
  first time a method is called on a connection
- **Subsequent-use:** replaces the name with a compact 7-bit
  `method_index`, used for all later calls to the same method

This document covers:
1. How first-use and subsequent-use relate in the protocol
2. The **RPC Batch Index** protocol (msg_id `0x07`) — discovered
   2026-06-28 — which registers method indices between peers
3. How a non-Unity implementation can decode both without knowing Unity's
   internal formula
4. What we learned about Unity's internal index derivation (partially
   reverse-engineered, not fully solved)
5. A bug found and fixed in the TS implementation

## The Protocol: First-Use / Subsequent-Use Pairs

When a Unity client connects to a server and calls `NetworkView.RPC("Foo")`:

1. **First call:** Unity sends a first-use message containing the Huffman
   hash of `"Foo"`. The receiver decodes the hash to learn the method name.

2. **Second call:** Unity sends a subsequent-use message containing a
   7-bit `method_index` (e.g., `0x5c`). The receiver must map this index
   back to `"Foo"`.

3. **All further calls:** subsequent-use with the same index.

The sender tracks per-connection which methods have had their first-use
sent. On a new connection, the cycle resets — first-use is sent again.

### How the receiver learns the mapping

~~Unity always sends first-use and subsequent-use in strict pairs on
`RELIABLE_ORDERED` delivery. The receiver can learn every mapping from
the traffic itself.~~ **Corrected (2026-06-28):** The actual protocol
uses a dedicated index registration message (msg_id `0x07`), not
implicit learning from first-use/subsequent-use pairs.

The correct protocol (discovered via cross-binary experiment):

1. Sender sends first-use for method M to Receiver (Huffman hash)
2. Receiver resolves the hash → method name `"Foo"`
3. Receiver sends an **RPC Batch Index** message (msg_id `0x07`,
   UNRELIABLE) back to Sender, containing: method_id + Receiver's
   own `method_index` for M
4. Sender receives the batch index, stores: "when sending subsequent-use
   for M to this Receiver, use index I"
5. Sender sends subsequent-use with index I
6. Receiver decodes I → `"Foo"` using its own local method table

Each peer registers its **own** index with the other side. The sender
uses the **receiver's** registered index, not its own. This is why
two builds with different assemblies (different indices) can
communicate — each side declares its own mapping.

The `learnMethodIndex()` mechanism in `ts/src/unity/rpc.ts` works as
an alternative — it learns indices from observed first-use/subsequent-use
pairs in traffic. This catches indices sent by Unity (which uses its own
index, registered with us via batch). Both mechanisms achieve the same
result.

### Evidence: cross-binary Unity communication (experiment 2)

Two Unity builds with **different** assemblies (one patched with 3
extra `[RPC]` methods, shifting all indices by +12) were connected
and exchanged RPCs. All RPCs were received correctly by both sides.

Wire capture confirmed:

| Method | Original build idx | Patched build idx | Difference |
|--------|-------------------|-------------------|------------|
| RPC_Int | 0x60 | 0x6c | +12 |
| RPC_Float | 0x64 | 0x70 | +12 |
| RPC_String | 0x68 | 0x74 | +12 |

The batch index protocol was observed between every first-use and
first subsequent-use:

```
S→C  FIRST-USE [RPC_Int]     (hash, RELIABLE_ORDERED)
C→S  BATCH INDEX idx=0x60    (client registers its own index, UNRELIABLE)
C→S  FIRST-USE [RPC_Int]     (hash, RELIABLE_ORDERED)
S→C  BATCH INDEX idx=0x6c    (server registers its own index, UNRELIABLE)
S→C  SUBSEQUENT idx=0x60     (server uses client's registered index ✓)
C→S  SUBSEQUENT idx=0x6c     (client uses server's registered index ✓)
```

### Evidence: Python wrong-index experiment (experiment 1)

A Python server sent first-use RPCs (accepted) and subsequent-use RPCs
with deliberately wrong indices. The pcap revealed Unity **did** send a
batch index (idx=0x60) after receiving our first-use, but our server
ignored it and used a fake index (0x30). Unity rejected that mismatch.

**Erratum (2026-07-13):** "Unity rejected the mismatch" only holds for
arbitrary non-slot index values (this experiment's 0x30/0x08), which
don't correspond to any real method and produce an explicit `Internal
RPC error`. The same capture's Phase 6 sent a wrong index that happened
to land on a *real* method's slot (0x78/120) and Unity did not reject it
— it silently misdispatched to that method (`RPC_IntFloatString`) with
garbage-but-well-typed parameters. See
`docs/research/2026-07-13-subsequent-use-static-index-dispatch.md` for
the full picture: the batch index this section describes as required and
correctly-used is, in fact, not reliably usable at all when the sender is
a non-Unity implementation — every method tested in that follow-up had a
self-reported batch index that didn't match its own real dispatch slot.
The cross-binary evidence below (experiment 2) still holds; it's a
different case (both sides are real Unity, so each side's self-reported
index is self-consistent with its own dispatch table in a way this
experiment's non-Unity sender's requested index was not).

This proves the batch index is *sent*, and that Unity's decoder can
reject packets — not that a non-Unity sender can rely on the reported
value for correct dispatch. See the erratum above.

### Sending without knowing the index

An implementation can always send first-use instead of subsequent-use.
The server's `sendRpcTo()` checks `hasMethodIndex(methodName)`: if false,
it sends first-use. Once an index is learned from incoming traffic
(via `learnMethodIndex()` or batch index processing), `hasMethodIndex()`
returns true, and subsequent calls automatically use the more compact
subsequent-use encoding.

This means a non-Unity server that has never received traffic for a
method will send first-use (slightly larger, ~20 extra bytes for the
Huffman hash), and Unity will accept it. No batch index exchange needed.

## Bug Found and Fixed

The Distance game server registered method **tags** (4-bit, for
first-use encoding) but not full method **indices** (7-bit, for
subsequent-use decoding). This meant:

- **Sending RPCs (server → client):** always first-use (no index →
  `hasMethodIndex()` false). Worked fine.
- **Receiving RPCs (client → server):** first-use decoded correctly
  (Huffman hash lookup), but subsequent-use decoded as `unknown_0xNN`
  because the index was not in the lookup table. The RPC handler was
  silently not called.

In practice, only the **first** call of each RPC method per connection
was received. All subsequent calls were dropped. This went unnoticed
because:
- The predominant flow is server → client (always first-use, works)
- Client → server RPCs like `SubmitTimeSync` are called once per
  connection
- The silent drop produced no errors or logs

### Fix

Added `learnMethodIndex()` and per-session first-use tracking:
- `ts/src/unity/rpc.ts`: `learnMethodIndex()` export, `methodIndex`
  field on `DecodedRpc`
- `ts/src/unity/server.ts`: per-session queue of pending first-use
  names, learning in `handleRpc()`
- `ts/src/unity/client.ts`: same, plus disconnect cleanup

## Unity's Internal Formula (Partially Reverse-Engineered)

The rest of this document covers what we learned about HOW Unity computes
the `method_index`. This is not needed for interop (the learning protocol
above handles it), but is useful for understanding Unity internals.

### Method: Differential Experiments

We used a single Unity 2018.1.6f1 headless Linux build with a
configurable experiment DLL. The DLL sends known RPCs and we capture
the traffic via `tshark`. By modifying the assembly (adding/removing
`[RPC]` attributes via Mono.Cecil, adding/removing types and methods),
we observed how the wire-format index changed.

### Assembly Layout

The test assembly (`Assembly-CSharp.dll`) contains:

| Type | MethodDef RIDs | Notes |
|---|---|---|
| SerializeHandler (delegate) | 1–4 | .ctor, Invoke, BeginInvoke, EndInvoke |
| ExperimentContext | 5–8 | .ctor, Log, EnableStateSynchronization, CreateNetworkView |
| IExperiment (interface) | 9–15 | 7 abstract methods |
| InheritedRpcBase : MonoBehaviour | 16–17 | .ctor, BaseRpc `[RPC]` |
| InheritedRpcDerived : InheritedRpcBase | 18–19 | .ctor, DerivedRpc `[RPC]` |
| Loader : MonoBehaviour | 20–47 | .ctor, lifecycle callbacks, 13 `[RPC]` methods (RPC_Void through RPC_Gamma), ParseArgs, LoadExperiment |
| SecondRpcBehaviour : MonoBehaviour | 48–49 | .ctor, ReceiveSerializeEvent `[RPC]` |

Three NetworkViews exist in the scene, each observing a different
MonoBehaviour component:
- **Primary NV**: observes Loader
- **SecondRpc NV**: observes SecondRpcBehaviour
- **InheritedRpc NV**: observes InheritedRpcDerived

### Observed Wire Values

Captured via pcap from Unity → Unity traffic, each RPC sent as first-use
then subsequent-use:

| RPC Method | NetworkView | Wire Index | Position (idx÷4) |
|---|---|---|---|
| RPC_Void | Primary | 0x5c (92) | 23 |
| RPC_Int | Primary | 0x60 (96) | 24 |
| ReceiveSerializeEvent | SecondRpc | 0x50 (80) | 20 |
| BaseRpc | InheritedRpc | 0x58 (88) | 22 |
| DerivedRpc | InheritedRpc | 0x04 (4) | anomalous |

### What we confirmed

**1. The index is always `position × 4`.**

Consecutive RPC methods on the same NV differ by exactly 4 in wire
value. RPC_Void = 0x5c, RPC_Int = 0x60 (delta = 4).

**2. The index is per-NetworkView.**

Each NetworkView has its own method table. ReceiveSerializeEvent on the
SecondRpc NV has index 0x50 (position 20), while RPC_Void on the Primary
NV has index 0x5c (position 23) — even though their MethodDef RIDs are
further apart.

**3. Interface methods are excluded.**

IExperiment (7 methods, RIDs 9–15) does not affect the index.

**4. Non-MonoBehaviour types are excluded.**

Adding a method to ExperimentContext (a plain class) did not change any
RPC indices. (Build B experiment from prior session.)

**5. Non-[RPC] methods on MonoBehaviour subclasses are excluded.**

Adding a non-[RPC] method to InheritedRpcBase or to Loader itself did
not change indices. (Builds C and E from prior session.)

**6. Adding [RPC] to a method inserts it into the counting.**

Using Mono.Cecil to add `[RPC]` to 4 Loader methods (Awake, Start,
Update, OnSerializeNetworkView) shifted RPC_Void from position 23 → 27
(up by exactly 4). The newly-tagged Awake method appeared at position
23 — exactly where RPC_Void used to be.

This proves: `position = base_offset + count([RPC] methods with lower
MethodDef RID)`.

**7. Removing [RPC] from methods decreases subsequent positions.**

Removing `[RPC]` from BaseRpc and DerivedRpc caused RPC_Int to drop
from position 24 → 22 (down by 2). (Build D from prior session.)

### The base offset mystery

Each NetworkView has a base offset — the position of the first [RPC]
method when no other [RPC] methods have lower RIDs:

| NetworkView | Component hierarchy | Base offset |
|---|---|---|
| SecondRpc NV | SRB → MonoBehaviour | 20 |
| Primary NV | Loader → MonoBehaviour | 21 |
| InheritedRpc NV | IRD → IRB → MonoBehaviour | 22 |

**Hypothesis:** `base_offset = 20 + (number of MB-subclass constructors
with MethodDef RID lower than the first [RPC] method)`.

- SRB: SRB.ctor at RID 48, ReceiveSerializeEvent at RID 49. No other
  MB ctors before RID 49 that belong to the SRB hierarchy → +0 → 20. ✓
- Loader: Loader.ctor at RID 20, RPC_Void at RID 33. Loader.ctor
  (RID 20 < 33) → +1 → 21. ✓
- IRD: IRB.ctor(16), IRD.ctor(18), BaseRpc at RID 17. Both ctors
  are in the IRD hierarchy; IRB.ctor (16 < 17) → one before, but
  IRD.ctor (18 > 17) → not before → +1 → 21. ✗ (observed 22)

This hypothesis is close but doesn't fully explain the IRD case. The
base offset of 20 itself likely corresponds to the number of
non-static, non-constructor methods declared on MonoBehaviour (which
has exactly 21 non-static declared methods including .ctor, so 20
excluding .ctor), but this is unverified.

### The DerivedRpc anomaly

DerivedRpc on the InheritedRpc NV produces `idx=0x04` with
`reserved=0xc000`. This is the only observed case where:
- The reserved field is non-zero
- The index doesn't fit the formula

Possible explanations:
- **Bit overflow:** position exceeds 31 (the 7-bit field can hold
  0–127 at stride 4, but bits may overflow into the reserved field)
- **Special encoding for inherited methods:** BaseRpc is declared on
  InheritedRpcBase (parent), DerivedRpc on InheritedRpcDerived (child).
  The child method may use a different encoding
- **Wrapping:** the 7-bit field wraps at 128 (position 32)

### What would fully solve it

The method_index computation is in Unity's native C++ code
(`Internal_RPC` internalcall). The player binary has symbols stripped.
Disassembly of the binary or access to Unity 2018.1 source would
resolve the remaining questions. For practical purposes, the dynamic
learning protocol (§first section) makes the exact formula unnecessary.

## Related Files

- `ts/src/unity/rpc.ts` — encoder/decoder with `learnMethodIndex()`
- `ts/src/unity/server.ts` — server-side dynamic learning
- `ts/src/unity/client.ts` — client-side dynamic learning
- `docs/research/unity-legacy-networking-wire-format.md` §3.2.1–3.2.2
- `scripts/extract-method-indices.cs` — static extraction tool (uses
  approximate formula; dynamic learning is preferred)
