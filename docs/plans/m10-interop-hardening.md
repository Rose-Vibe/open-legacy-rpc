# M10: Interop Hardening

## Goal

Verify and fix the Python reference implementation under conditions that
match real Distance gameplay: multiple concurrent clients, targeted RPCs,
large payloads, multi-view state sync, password auth, and clean disconnect.
After this milestone, the implementation is ready for Distance integration.

## Context

M9 proved basic single-client interop (1 RPC type, 1 state sync view).
Distance needs 12-24 concurrent players, 3 NetworkViews per car, targeted
RPCs, large byte[] payloads, password auth, and clean disconnect with
RemoveRPCs/DestroyPlayerObjects. All five user-requested items plus two
additional gaps are covered.

## Security Constraint

`Network.InitializeSecurity()` must NEVER be called in experiments.

---

## Milestone 10a: Multi-Client

### Background

Only 1 client has ever connected simultaneously. Distance supports 12-24.
The 0x81 player assignment message has unknown fields that may change per
client. ViewID ranges must not overlap. Concurrent message dispatch must
not corrupt state.

### Work

1. **Experiment**: Create `MultiClientExperiment` — server accepts 3
   clients. Each client sends RPC_Int with its player index. Server sends
   RPC_Int to all clients with a broadcast value.

2. **Test**: Run 1 Unity server + 3 Unity clients. Verify all 3 connect,
   each gets a unique player_index and viewid_base, RPCs arrive correctly.

3. **Test**: Run Python server + 3 Unity clients. Same verification.

4. **Test**: Run Unity server + 3 Python clients (sequential connects).

5. **Fix** any issues with concurrent peer management, ViewID allocation,
   or message dispatch.

### Exit Criteria

- 3 simultaneous clients connect and exchange RPCs
- Each gets unique player_index (1, 2, 3) and non-overlapping viewid_base
- Python server handles concurrent connects/disconnects without errors
- Python client handles being one of multiple clients
- Client disconnect + reconnect while other clients remain connected works
- Stress test with 6+ Python clients shows no resource leaks

---

## Milestone 10b: RPCMode.Player Targeting

### Background

Distance uses targeted RPCs (server → specific client) via
`networkView.RPC(name, player, data)`. The RPCMode.Player format has a
1-bit target field (always 0 in observations). Transport-level addressing
should handle targeting, but this is unverified in interop.

### Work

1. **Experiment**: Create `TargetedRpcExperiment` — server connects 2
   clients, sends RPC_Int(111) to client 1 only and RPC_Int(222) to
   client 2 only.

2. **Test**: Unity server + 2 Unity clients. Verify each client receives
   only its targeted RPC.

3. **Test**: Python server + 2 Unity clients. Same verification.

4. **Verify** the Python server's `send_rpc(target=addr)` correctly
   uses RPCMode.Player encoding.

### Exit Criteria

- Targeted RPCs reach only the intended client
- Python server can target specific clients by address
- No crosstalk between clients

---

## Milestone 10c: Large RPC Payloads (Split Packets)

### Background

Distance's primary data channel sends byte[] RPCs. Large payloads
(>~1200 bytes) trigger RakNet split packet fragmentation. Our
SplitPacketAssembler is implemented but never tested at scale.

### Work

1. **Experiment**: Create `LargeRpcExperiment` — server sends RPC_Bytes
   with payloads of increasing size: 100, 500, 1000, 2000, 5000, 10000 bytes.

2. **Test**: Unity server + Unity client. Verify all payloads arrive
   intact.

3. **Test**: Python server + Unity client with same payload sizes.

4. **Test**: Unity server + Python client.

5. **Fix** any split packet issues (reassembly, bit_length tracking,
   ordering).

### Exit Criteria

- byte[] payloads up to 10000 bytes round-trip correctly
- Split packets reassemble in order
- No data corruption at MTU boundaries
- Bidirectional large payloads (both sides sending) work simultaneously

---

## Milestone 10d: Multiple NetworkViews (State Sync)

### Background

Distance uses 3 NetworkViews per car: view0=ReliableDeltaCompressed,
view1=Unreliable, view2=Unreliable. Each has a different ViewID. Our
implementation has only been tested with a single view.

### Work

1. **Experiment**: Create `MultiViewExperiment` — server has 3
   NetworkViews with different sync modes:
   - View 0: ReliableDeltaCompressed, serializes int
   - View 1: Unreliable, serializes float
   - View 2: Unreliable, serializes Vector3

2. **Test**: Unity server + Unity client. Verify all 3 views sync
   independently with correct values.

3. **Test**: Unity server + Python client. Register handlers for all 3
   view IDs. Verify all 3 streams decode correctly.

4. **Test**: Python server + Unity client. Send state sync from all 3
   views. Verify Unity receives all 3 correctly.

### Exit Criteria

- 3 simultaneous NetworkViews with different sync modes work correctly
- Each view's data decodes independently (no cross-contamination)
- Mixed ReliableDeltaCompressed + Unreliable works in same session

---

## Milestone 10e: Password Authentication Interop

### Background

Distance sets `Network.incomingPassword` on the server. The password is
appended as plaintext ASCII to the 0x04 connection request. We've decoded
the format but never tested interop.

### Work

1. **Experiment**: Create `PasswordInteropExperiment` — server sets
   `Network.incomingPassword = "testpass"`. Client connects with matching
   password. Verify connection succeeds and RPCs work.

2. **Test**: Unity server (password) + Python client (correct password).

3. **Test**: Unity server (password) + Python client (wrong password).
   Verify rejection.

4. **Test**: Python server (password) + Unity client (correct password).

5. **Test**: Python server (password) + Unity client (wrong password).
   Verify rejection.

6. **Implement** password checking in the Python server's connection
   handler if not already present.

### Exit Criteria

- Correct password: connection succeeds, RPCs exchange normally
- Wrong password: connection is rejected (no 0x81 sent)
- Python server validates passwords from Unity clients
- Python client sends passwords to Unity servers

---

## Milestone 10f: RemoveRPCs / DestroyPlayerObjects

### Background

Distance calls `Network.RemoveRPCs(player)` and
`Network.DestroyPlayerObjects(player)` on every disconnect. The wire
protocol for these operations is unknown — they may be internal RPCs,
dedicated message types, or purely server-side operations.

### Work

1. **Experiment**: Create `DisconnectCleanupExperiment` — server connects
   client, client disconnects. Capture traffic around the disconnect to
   look for RemoveRPCs/DestroyPlayerObjects wire messages.

2. **Analyze**: Check if any new message types appear on disconnect beyond
   the existing 0x15 (ID_DISCONNECTION_NOTIFICATION).

3. **Document** findings in the spec.

4. **Implement** appropriate cleanup in the Python server.

### Exit Criteria

- Wire protocol for disconnect cleanup is documented (even if "no wire
  messages" is the answer)
- Python server cleans up ViewIDs and per-client state on disconnect
- No resource leaks after client disconnect/reconnect cycles
- No resource leaks in SplitPacketAssembler after mid-transfer disconnect

---

## Milestone 10g: Concurrent ViewID Range Management

### Background

With multiple clients, each gets a ViewID range (stride=50). Clients
allocate ViewIDs locally from their range. The server must track
allocations to route state sync and RPCs to the correct view owners.

### Work

1. **Experiment**: Use the multi-client experiment from 10a. Each client
   calls `Network.AllocateViewID()` 3 times (matching Distance's 3
   views per car).

2. **Verify**: Client 1 gets ViewIDs 50-52, Client 2 gets 100-102,
   Client 3 gets 150-152.

3. **Test**: Python server tracks all allocated ViewIDs per client.
   On disconnect, frees the correct range.

4. **Test**: Reconnect after disconnect — verify the new client gets a
   fresh range without conflicts.

### Exit Criteria

- ViewID ranges don't overlap across concurrent clients
- Server correctly tracks ViewID ownership
- Disconnect frees ViewIDs; reconnect assigns new ones
- No stale ViewID routing after disconnect

---

## Implementation Order

```
10a (Multi-client)           — foundational, unblocks 10b/10g
10b (RPCMode.Player)         — depends on 10a (needs 2+ clients)
10g (ViewID ranges)          — can combine with 10a experiment
10c (Large payloads)         — independent
10d (Multiple views)         — independent
10e (Password auth)          — independent
10f (Disconnect cleanup)     — do after 10a (needs multi-client context)
```

Recommended: **10a+10g → 10b → 10c → 10d → 10e → 10f**

10a and 10g share the same experiment (multi-client), so do them together.
10b needs multi-client infrastructure from 10a. The rest are independent
and can be done in any order.
