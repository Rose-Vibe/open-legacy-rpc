# EnableStateSynchronization() Does Not Work at Runtime (Unity 2018.1.6f1)

**Date:** 2026-06-28

## Finding

Calling `NetworkView.stateSynchronization = NetworkStateSynchronization.ReliableDeltaCompressed`
(or `.Unreliable`) at runtime in Unity 2018.1.6f1 does **not** enable state synchronization.
No `OnSerializeNetworkView` callbacks fire and no 0x1B state sync messages appear on the wire.

State synchronization must be configured in the scene file before build time.
In the Unity scene YAML (`Main.unity`), the relevant field is:

```yaml
m_StateSynchronization: 2   # 0=Off, 1=ReliableDeltaCompressed, 2=Unreliable
```

## How We Proved It

1. Built a `StateSyncTimestampExperiment` that called `EnableStateSynchronization()` at runtime
   after `OnServerInitialized()` / `OnConnectedToServer()`.
2. Ran server + client with a 70-second stagger. Zero state sync messages received.
3. Changed `Main.unity` to set `m_StateSynchronization: 2` on the PrimaryNetworkView,
   rebuilt the Unity player, and re-ran. State sync messages appeared immediately.

## Implications

- Any reimplementation that interoperates with Unity clients does not need to handle
  dynamic state sync enable/disable negotiation. The set of synchronized views is
  fixed at build time and known from the scene configuration.
- For experiment infrastructure: always set state sync mode in the scene file, not in
  experiment code.
