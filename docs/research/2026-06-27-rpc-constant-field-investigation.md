# RPC "Constant" Field Investigation (2026-06-27)

## Field Location

In subsequent-use RPCs: bits 120–135 (16 bits), after the `remaining` field.
In first-use RPCs: within the 52-bit internal metadata block, bits 36–51 of
that block (after tag + zeros + remaining).

## Derivation (SOLVED)

The "constant" field is a 16-bit NetworkViewID encoding. It identifies which
NetworkView the RPC is being sent through. The encoding differs for scene-baked
vs allocated views:

| View Type | Formula | Flag Bit 13 |
|-----------|---------|-------------|
| Internal RPC | `0x0000` | 0 |
| Scene-baked | `sceneViewIndex << 1` | 0 |
| Allocated | `0x2000 \| (allocatedID << 5)` | 1 |

Bit layout:
```
Scene:     [0 0 0 sceneViewIndex(12..1) 0]
Allocated: [0 0 1 allocatedID(10..5) 00000]
```

**The field is NOT class-derived.** Same class on different allocated IDs
produces different constants. Different classes on the same allocated ID
produce the same constant.

## Verified Values

| View | Type | AllocatedID | Formula | Constant |
|------|------|-------------|---------|----------|
| Loader (SceneID 1) | Scene-baked | — | 1 << 1 | 0x0002 |
| SecondRpcBehaviour (SceneID 2) | Scene-baked | — | 2 << 1 | 0x0004 |
| InheritedRpcDerived (SceneID 3) | Scene-baked | — | 3 << 1 | 0x0006 |
| SecondRpcBehaviour (alloc) | Allocated | 50 | 0x2000 \| (50 << 5) | 0x2640 |
| SecondRpcBehaviour (alloc) | Allocated | 51 | 0x2000 \| (51 << 5) | 0x2660 |
| SecondRpcBehaviour (alloc) | Allocated | 52 | 0x2000 \| (52 << 5) | 0x2680 |
| SecondRpcBehaviour (alloc) | Allocated | 54 | 0x2000 \| (54 << 5) | 0x26c0 |
| InheritedRpcDerived (alloc) | Allocated | 51 | 0x2000 \| (51 << 5) | 0x2660 |
| Distance NetworkInstancedEventTransceiver | Allocated | 50 | 0x2000 \| (50 << 5) | 0x2640 |
| Internal (`__RPCNetworkInstantiate`) | Internal | — | 0 | 0x0000 |

All 10 values match the formula exactly.

## Key Findings

1. **It's a ViewID encoding, not a class constant.** The "constant" encodes
   which NetworkView the RPC is sent through, using a 16-bit packed format
   similar to (but distinct from) the 16-bit ViewID used in RPC parameters.

2. **NOT class-derived.** Earlier hypothesis that this was per-class was wrong.
   The correlation with class was an artifact of each class only having one
   NetworkView in our test scenes. Distance's `NetworkInstancedEventTransceiver`
   and our `SecondRpcBehaviour` both produce 0x2640 because both use
   AllocatedID:50 (the first allocated ID for player 1).

3. **Receivers don't validate it.** Clients accept RPCs regardless of the
   constant value. A server can safely use a fixed value.

4. **Bit 13 is the scene/allocated discriminator.** 0 = scene-baked,
   1 = allocated. This parallels bit 14 in the 16-bit ViewID-as-RPC-parameter
   encoding (§14 in the wire format spec).

5. **Different shifts for different types.** Scene-baked views use a 1-bit
   left shift (stride of 2). Allocated views use a 5-bit left shift (stride
   of 32) with a 0x2000 base.

## Experiment Details

### Phase 1 Experiments (2026-06-27)

**A: MultiAllocConstantExperiment** — Allocated 4 views (IDs 50, 51, 52, 54)
with the same class (SecondRpcBehaviour). Constants increment with ID:
0x2640, 0x2660, 0x2680, 0x26c0. Confirmed stride = 32 per allocated ID,
and skipping an ID (53) doesn't affect subsequent constants.

**B: AllocDiffClassConstantExperiment** — Allocated 2 views with different
classes (SecondRpcBehaviour ID:50, InheritedRpcDerived ID:51), plus a
scene-baked Loader RPC. Results: constants depend on AllocatedID, not class.
SecondRpc@50 = 0x2640, InheritedRpc@51 = 0x2660, Loader@SceneID:1 = 0x0002.

**C: SceneVsAllocConstantExperiment** — Same class (SecondRpcBehaviour) on
both scene-baked (SceneID:2) and allocated (ID:50) views. Scene = 0x0004,
Allocated = 0x2640. Confirms the constant encodes view identity and type,
not class identity.

## Relay Format

When the server relays an RPCMode.Others RPC to other clients:
- Counter is re-assigned (server's own sequence)
- Mode is preserved (Others=1 stays Others=1)
- 5 zero bits are appended after the params
- The `remaining` field increases by 5 to account for the extra bits
- All other fields (constant, tag, method hash) are preserved

## Previously Wrong Hypotheses

- ~~Per-class, not per-method or per-assembly~~ → Per-view-ID, not per-class
- ~~Correlates with class hierarchy~~ → Correlates with AllocatedID
- ~~Suspicious match for direct MonoBehaviour subclasses~~ → Coincidence:
  Loader extends MonoBehaviour via TypeRef row 2, constant 0x0002 = SceneID 1 << 1
