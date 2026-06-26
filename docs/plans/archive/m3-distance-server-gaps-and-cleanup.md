# M3: Distance Server Gaps & Cleanup

## Goal

Close the remaining gaps between the current spec/implementation and what's
needed to build a Distance game server. Then clean up code quality issues
from the M2 sprint.

## Context

The M2 reference spec and Python implementation cover core RPC, state sync,
and connection handshake — enough for bidirectional interop with vanilla
Unity networking. Distance uses a subset of Unity's networking features on
top of this, plus some features we haven't reversed yet.

Key simplifications from Distance's design:
- No `Network.Instantiate` — manual ViewID allocation + local spawning
- No buffered RPCs — all state management is application-level
- No `NetworkPlayer` or `NetworkViewID` as direct RPC parameter types —
  these are embedded in custom structs serialized via byte[]
- `RemoveRPCs` / `DestroyPlayerObjects` are server-side cleanup only,
  no wire messages needed for a replacement server

---

## Milestone 3: NetworkGroups

### Background

Distance uses three network groups to gate message delivery:
- **GlobalGroup** — always enabled for all players
- **GameModeGroup** — enabled during active gameplay
- **LobbyGroup** — enabled in lobby

The server calls `Network.SetSendingEnabled(group, player, enabled)` and
`Network.SetReceivingEnabled(group, player, enabled)` to control which
messages each player receives during scene transitions.

### Work

1. **Capture**: Create a Unity experiment with multiple network groups.
   Send RPCs on different groups, toggle groups on/off, observe what
   changes on the wire (msg_id, header fields, or separate control message).
2. **Spec**: Document the group field location in the RPC/sync headers,
   or the control message format for SetSendingEnabled/SetReceivingEnabled.
3. **Implement**: Add group support to `unity_server.py` — per-client
   group membership tracking, message filtering on send.
4. **Test**: Unit tests for group filtering. Interop test with Unity client
   verifying that disabled groups suppress delivery.

### Exit Criteria

- Wire format for network groups documented in spec
- Python server can filter messages by group per-client
- Interop test: Unity client in group A does not receive group B messages

---

## Milestone 4: ViewID Allocation

### Background

Distance clients call `Network.AllocateViewID()` three times on connect
(one per NetworkView: player entity + two car views). The server must
support this allocation protocol so clients can create their car objects.

### Work

1. **Capture**: Create a Unity experiment where the client calls
   `Network.AllocateViewID()` and observe the wire exchange. Determine
   whether it's an RPC, a dedicated message type, or implicit.
2. **Spec**: Document the allocation request/response format and the
   ViewID number space (how the server partitions IDs across clients).
3. **Implement**: Add `allocate_view_id()` to `RakNetServer` /
   `UnityServer`. Track allocated IDs per client. Support
   `Network.RemoveRPCs()` / `DestroyPlayerObjects()` as server-side
   cleanup (free allocated IDs on disconnect).
4. **Test**: Unit test for ID allocation and cleanup. Interop test with
   Unity client that allocates ViewIDs and sends RPCs targeting them.

### Exit Criteria

- ViewID allocation protocol documented in spec
- Python server allocates ViewIDs on client request
- Cleanup on disconnect frees allocated IDs
- Interop test passes

---

## Milestone 5: ReliableDeltaCompressed State Sync

### Background

Unity's `NetworkStateSynchronization.ReliableDeltaCompressed` mode sends
state sync with RELIABLE reliability and delta-encodes changes from the
previous acknowledged state. Distance uses this for one of its three
per-car NetworkViews (the other two use Unreliable).

### Work

1. **Capture**: Create a Unity experiment with a NetworkView set to
   `ReliableDeltaCompressed`. Serialize changing values and capture the
   wire format. Compare to the Unreliable format we already know.
2. **Differential analysis**: Send identical values repeatedly to see
   what "no change" looks like. Then change one field at a time to
   isolate the delta encoding.
3. **Spec**: Document the delta compression header, how fields are
   flagged as changed/unchanged, and the reliability/ordering behavior.
4. **Implement**: Add delta-compressed state sync encode/decode to
   `unity_protocol.py`. Add server-side per-client state tracking for
   delta computation.
5. **Test**: Unit tests for delta encode/decode round-trips. Interop
   test with Unity client receiving delta-compressed state.

### Exit Criteria

- Delta compression wire format documented in spec
- Python server can send ReliableDeltaCompressed state sync
- Unity client receives and applies delta-compressed state correctly

---

## Milestone 6: First-Use RPC Metadata (52 Unknown Bits)

### Background

First-use RPC encoding has 52 bits of metadata between the method hash
and the RPCMode field. Unity populates these with non-zero values, but
our encoder writes zeros. Our workaround (pre-registering all methods to
force subsequent-use encoding) works but means the Python server can't
send RPCs for methods the client hasn't seen before.

### Work

1. **Capture**: Send RPCs with varying parameters, method names, view IDs,
   and player counts. Correlate the 52 metadata bits with known variables.
2. **Differential analysis**: Isolate which bits change when specific
   inputs change. Focus on the non-zero regions observed in captures
   (around bits 28-40 of the metadata).
3. **Spec**: Document the metadata field structure.
4. **Implement**: Update `encode_rpc_first_use()` to populate the
   metadata correctly.
5. **Test**: Interop test: Python server sends first-use RPC to Unity
   client, verify Unity invokes it (currently silently dropped).

### Exit Criteria

- First-use RPCs from Python are accepted by Unity
- Metadata field structure documented in spec
- Pre-registration workaround no longer needed

---

## Milestone 7: Code Cleanup

### Background

Reviewer suggestions from M2 that were deferred during interop debugging.

### 7a: Package-Relative Imports

Convert `sys.path.insert` hacks in test files and `unity_rpc_decode.py`
to proper package-relative imports. Add a minimal `pyproject.toml` or
`setup.py` so `pip install -e .` works.

### 7b: Silent Exception Swallowing

The `_handle_rpc` methods in `unity_client.py` and `unity_server.py`
catch `Exception` and silently discard it. Replace with:
- Logging the exception (at minimum the method name and error)
- Optionally, a configurable error handler callback

### 7c: Bit-Length Through Transport

The RakNet encapsulated message header carries `bit_length`, but our
transport layer converts to `len(payload) * 8` on receive. This loses
sub-byte precision for messages that aren't byte-aligned (like RPCs with
mode=Player). Thread the actual `bit_length` from the encapsulated header
through to the Unity protocol decoder.

### Exit Criteria

- No `sys.path.insert` in any file
- `pip install -e .` works for the protocol package
- RPC decode errors are logged, not silently swallowed
- `bit_length` from RakNet header used in protocol decoding
- All 50+ existing tests still pass

---

## Implementation Order

```
M3 (NetworkGroups)          — independent, captures needed
M4 (ViewID Allocation)      — independent, captures needed
M5 (Delta Compressed Sync)  — independent, captures needed
M6 (First-Use Metadata)     — independent, captures needed
M7 (Code Cleanup)           — independent, no captures needed
```

M3–M6 each require new Unity experiments and pcap analysis. They are
independent of each other and can be done in any order. M7 is pure
code cleanup and can be done at any time.

Recommended order: **M7 → M3 → M4 → M5 → M6**

- M7 first because it improves code quality for everything that follows
  (especially bit-length threading, which affects M5/M6 accuracy).
- M3 before M4 because groups are simpler and build capture methodology
  confidence.
- M5 before M6 because delta compression is more useful for Distance
  than first-use metadata (the pre-registration workaround is adequate).
- M6 last because it's the hardest and least critical (workaround exists).

## Decisions

- **Security (`Network.InitializeSecurity`)**: Deferred. Will test whether
  the Distance client connects to an unsecured server before investing in
  reversing the encryption handshake.
- **`Network.Instantiate`**: Not needed — Distance doesn't use it.
- **Buffered RPCs**: Not needed — Distance doesn't use them.
- **`RemoveRPCs` / `DestroyPlayerObjects`**: Server-side cleanup only.
  Implemented as part of M4 (free allocated ViewIDs on disconnect).
  No wire messages needed.
