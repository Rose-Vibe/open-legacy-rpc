# M22: user_rpc_constant Deep Investigation

## Goal

Determine the exact derivation of the 16-bit `user_rpc_constant` field in
Unity RPC messages. Current knowledge: scene-baked views use
`sceneViewIndex * 2`, allocated views produce a different value (0x2640 for
AllocatedID:50). The exact formula for allocated views is unknown.

## Open Questions

1. **Scene reload**: Does the constant increment if the same scene is loaded
   again (creating new copies of the scene-baked NetworkViews)?
2. **Multiple allocated views, same class**: If we allocate 3 views all using
   SecondRpcBehaviour, do they share the same constant or does it change?
3. **Multiple allocated views, different classes**: Do different MonoBehaviour
   classes on allocated views produce different constants?
4. **Class name influence**: Do classes with similar names (e.g. `FooRpc`,
   `FooRpc2`) produce similar constants? What about completely different names?
5. **Multiple classes + multiple views**: With N classes each having M allocated
   views, what pattern emerges?
6. **Allocated ID number influence**: Does the AllocatedID itself affect the
   constant, or is it purely class-derived?

## Approach

### Phase 1: Experiments with existing classes (no rebuild needed)

These use the existing Unity player and classes (Loader, SecondRpcBehaviour,
InheritedRpcDerived) with dynamically allocated views.

**Experiment A: MultiAllocConstantExperiment**
- Allocate 3 ViewIDs (consecutive: 50, 51, 52)
- Create 3 GameObjects, each with SecondRpcBehaviour + NetworkView
- Send an RPC (ReceiveSerializeEvent) on each allocated view
- Also allocate a 4th ID but skip it, use the 5th (tests whether
  AllocatedID number itself matters vs allocation order)
- Extract the constant from each RPC
- Tests: same class → same constant? Does AllocatedID number matter?

**Experiment B: AllocDiffClassConstantExperiment**
- Allocate 3 ViewIDs
- Create one with SecondRpcBehaviour, one with InheritedRpcDerived,
  one with Loader (tests 3 different classes including one that also
  has a scene-baked view at SceneID 1 with constant 0x0002)
- Send RPCs on each
- Extract constants — are they different per class?
- Key question: if Loader's allocated constant matches SecondRpc's (0x2640),
  then the constant is NOT class-derived for allocated views

**Experiment C: SceneVsAllocConstantExperiment**
- Send RPC on scene-baked SecondRpc (SceneID 2, expected constant 0x0004)
- Allocate a new view with SecondRpcBehaviour
- Send RPC on the allocated view
- Compare: same class, different view type → same or different constant?
- Hypothesis: if constants differ, the constant is not purely class-derived
  but encodes something about the view's origin (scene vs allocated)

**Note:** Distance's `NetworkInstancedEventTransceiver` and our
`SecondRpcBehaviour` are completely different classes yet both produced
0x2640 for allocated views. If Phase 1 confirms this is view-type-derived
(not class-derived), Phase 2 class-name experiments become unnecessary.

### Phase 2: New classes + rebuild

Add new MonoBehaviour classes to the Unity project to test name influence.
These must be in Assembly-CSharp (scene-baked or dynamically attached).

**New classes to add to UnityProject/Assets/Scripts/:**

| Class Name | Parent | RPC Method | Purpose |
|------------|--------|------------|---------|
| `AaaRpc` | MonoBehaviour | `TestRpc(int)` | Short name, starts with A |
| `ZzzRpc` | MonoBehaviour | `TestRpc(int)` | Short name, starts with Z |
| `AaaRpc2` | MonoBehaviour | `TestRpc(int)` | Similar name to AaaRpc |
| `LongNameBehaviourRpc` | MonoBehaviour | `TestRpc(int)` | Long name |

Update SetupScene.cs to add these as scene-baked NetworkViews (SceneIDs 4-7).
Rebuild the Unity player.

**Experiment D: ClassNameConstantExperiment**
- Send RPCs from each new scene-baked view
- Verify scene-baked formula still holds: SceneID 4→0x0008, 5→0x000a, etc.
- Then allocate views for each new class
- Extract allocated constants — correlate with class name, hierarchy, etc.

**Experiment E: MultiAllocPerClassExperiment**
- For each of the 4 new classes, allocate 2 views
- Send RPCs on all 8 allocated views
- Check: same class → same constant? Different class → different constant?
- Look for pattern: does the constant encode something about the class?

### Phase 3: Analysis

Write an analysis script that:
1. Parses pcap from each experiment
2. Extracts (view_type, allocated_id, class_name, constant) tuples
3. Looks for correlations: class metadata token, name hash, inheritance depth
4. Cross-references with Distance's known values

## Exit Criteria

- Confirmed whether allocated-view constant depends on class identity,
  AllocatedID number, or both
- Confirmed whether class name influences the constant
- Either derive the exact formula or document precisely which factors
  affect it and which don't
- Update the protocol spec §3.6 with findings

## Implementation Order

1. Write Phase 1 experiments (A, B, C)
2. Build DLL, run experiments, analyze pcaps
3. Based on Phase 1 results, decide if Phase 2 is needed
4. If needed: add classes, rebuild Unity, write Phase 2 experiments (D, E)
5. Run Phase 2, analyze, update spec
