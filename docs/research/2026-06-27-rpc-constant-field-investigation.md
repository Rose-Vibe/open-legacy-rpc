# RPC "Constant" Field Investigation (2026-06-27)

## Field Location

In subsequent-use RPCs: bits 120–135 (16 bits), after the `remaining` field.
In first-use RPCs: within the 52-bit internal metadata block, bits 36–51 of
that block (after tag + zeros + remaining).

## Observed Values

| Value  | Context                                          |
|--------|--------------------------------------------------|
| 0x0000 | Internal RPCs (`__RPCNetworkInstantiate`)         |
| 0x0002 | Our Loader class (all experiments, both 5.5/2018) |
| 0x2000 | Distance: 4 of 5 RPC classes                     |
| 0x2640 | Distance: `NetworkInstancedEventTransceiver`      |

## Key Findings

1. **Per-class, not per-method or per-assembly.** All RPCs from the same
   MonoBehaviour subclass share the same constant. Different classes within
   the same assembly can have different constants.

2. **Consistent across Unity versions.** Our Loader produces 0x0002 on both
   Unity 5.5.6f1 and 2018.1.6f1 (different builds, different assembly MVIDs,
   same source code structure).

3. **Correlates with class hierarchy, not method metadata.** The Distance
   outlier (0x2640) comes from `NetworkInstancedEventTransceiver`, which has
   a different inheritance chain than the 0x2000 classes:
   - 0x2000 classes: `→ NetworkStaticEventTransceiver → MonoBehaviour`
     or `→ ManagerAbstract → MonoBehaviour`
   - 0x2640 class: `→ NetworkTransceiver → MonoBehaviour`

4. **Suspicious match for direct MonoBehaviour subclasses.** Our Loader
   extends `MonoBehaviour` directly via TypeRef row 2, and its constant is
   0x0002. This could be coincidence or could indicate the constant encodes
   a class metadata token from the inheritance chain.

5. **Exact derivation unknown.** Checked: assembly MVID, assembly name/version,
   TypeDef RID, method RID, field list, method list, parent class extends
   value. None produce a clean formula across all observed values. The
   encoding likely happens in Unity's native C++ runtime, not in managed code.

## Distance Class Details

| Class | TypeDef | Extends | Constant | RPCs |
|-------|---------|---------|----------|------|
| NetworkInstancedEventTransceiver | 1216 | NetworkTransceiver (2849) | 0x2640 | ReceiveSerializeEvent |
| ClientToClientNetworkTransceiver | 2856 | NetworkStaticEventTransceiver (2879) | 0x2000 | ReceiveBroadcastAllEvent |
| ClientToServerNetworkTransceiver | 2861 | NetworkStaticEventTransceiver (2879) | 0x2000 | ReceiveClientToServerEvent |
| NetworkingManager | 2893 | ManagerAbstract (528) | 0x2000 | Submit/ReceiveServerNetworkTimeSync |
| ServerToClientNetworkTransceiver | 2920 | NetworkStaticEventTransceiver (2879) | 0x2000 | ReceiveServerToClient*, ReceiveTargeted* |

## Practical Impact

Receivers do not appear to validate this field strictly — Distance clients
work correctly when our server sends 0x2000 regardless of which class the
RPC targets. The field is implemented as configurable (`userRpcConstant`
parameter) with 0x2000 as the default.

## Further Investigation

To definitively determine the encoding, create an experiment with a second
MonoBehaviour subclass that has [RPC] methods, in addition to Loader, and
observe whether the constant differs between them.
