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

3. **The constant IS the routing key.** Unity uses this field — not the
   48-bit view_id header — to route incoming RPCs to the correct
   NetworkView. Wrong constant → RPC dropped or delivered to wrong view.
   See Phase 2 delivery test results below.

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

### Phase 2: Delivery Test (2026-06-27)

**ConstantDeliveryExperiment** — Python server sends 10 RPCs (RPC_Int) to
a Unity client with various constant values. Only RPCs with the correct
constant (0x0002 = SceneID:1, matching the Loader's NetworkView) are
delivered. All others are dropped.

| # | Constant | Target View | Delivered? | Unity Error |
|---|----------|-------------|------------|-------------|
| 1 | 0x0002 | SceneID:1 (Loader) | **YES** (100) | — |
| 2 | 0x0002 | SceneID:1 (Loader) | **YES** (101) | — |
| 3 | 0x0004 | SceneID:2 (SecondRpc) | NO | "RPC_Int does not exist in any script attached to 'SecondRpc'" |
| 4 | 0x0010 | SceneID:8 | NO | "networkView 'SceneID: 8' doesn't exist" |
| 5 | 0x2640 | AllocatedID:50 | NO | "networkView 'AllocatedID: 50' doesn't exist" |
| 6 | 0x0000 | SceneID:0 | NO | "networkView 'SceneID: 0' doesn't exist" |
| 7 | 0xFFFF | (malformed) | NO | "Could not read encoded network ID" |
| 8 | 0x2000 | AllocatedID:0 | NO | "networkView 'AllocatedID: 0' doesn't exist" |
| 9 | 0x1234 | SceneID:26, LP:9 | NO | "networkView 'SceneID: 26 Level Prefix: 9' doesn't exist" |
| 10 | 0x0002 | SceneID:1 (Loader) | **YES** (900) | — |

Key observations:
- **3/10 delivered** — exactly the 3 with the correct constant (0x0002)
- Test #3 (0x0004) proves routing: the RPC reached SecondRpcBehaviour
  (which exists at SceneID:2) but was rejected because SecondRpc doesn't
  have RPC_Int
- 0xFFFF causes a parse error ("Could not read encoded network ID"),
  suggesting the constant has a maximum valid range
- 0x1234 decodes as SceneID:26 with LevelPrefix:9, revealing that higher
  bits encode the level prefix

## Additional Findings

### method_tag field (4-bit, first-use encoding)

**Erratum (2026-07-12):** the formula below is empirically disproven for
12 of 13 tested Loader RPC methods — see
`docs/research/2026-07-12-method-tag-real-derivation.md`. RPC_Int's match
here is coincidental (as is RPC_Void's, the only other match), not
evidence the formula generalizes. `method_tag` must be captured
empirically per compiled assembly, not derived.

The 4-bit method_tag in first-use RPC messages equals `method_index & 0x0F`
(bottom 4 bits of the 7-bit subsequent-use method_index). Verified by
packet capture: RPC_Int has method_index=104 (0x68) and method_tag=8 (0x8).

### method_index computation

The subsequent-use method_index = `(method_rid - 1 - interface_method_count) * 4`
where method_rid is the method's row in the MethodDef table and
interface_method_count is the total number of interface methods whose RIDs
come before it. For the current Loader build:
- RPC_Void: index=100, RPC_Int: index=104, ..., RPC_Gamma: index=148

### 48-bit view_id header vs constant

The 48-bit view_id in the RPC header is NOT used for routing. All
allocated-view RPCs from Unity use view_id=0x000000000000 in the header.
The 16-bit constant field is the actual routing mechanism.

## Previously Wrong Hypotheses

- ~~Per-class, not per-method or per-assembly~~ → Per-view-ID, not per-class
- ~~Correlates with class hierarchy~~ → Correlates with AllocatedID
- ~~Suspicious match for direct MonoBehaviour subclasses~~ → Coincidence:
  Loader extends MonoBehaviour via TypeRef row 2, constant 0x0002 = SceneID 1 << 1
- ~~Receivers don't validate it~~ → The constant IS the routing key; wrong
  constant = wrong view or dropped RPC
