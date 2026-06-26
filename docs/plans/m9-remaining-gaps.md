# M9: Remaining Gaps & Cleanup

## Goal

Close the remaining unknowns from M8 and the unfinished cleanup items from
M3, then verify end-to-end interop. After this milestone, the spec and
reference implementation are complete enough that no further Unity captures
are needed for basic client/server interop.

## Context

M8 left three partial milestones with opaque encodings. M3's code cleanup
(M7) was partially done. The core protocol is fully reversed — these are
edge-case types and quality-of-life fixes.

## Security Constraint

`Network.InitializeSecurity()` must NEVER be called in experiments.

---

## Milestone 9a: NetworkViewID 16-bit Encoding

### Background

NetworkViewID appears as a 16-bit value in RPC params and state sync, but
the encoding is opaque. Observed: SceneID:1 → 0x0004, AllocatedID:50 →
0x4C80. The 48-bit header encoding (§5) is understood, but the 16-bit
param encoding is not.

### Work

1. **Experiment**: Send RPC_NetworkViewID with a range of known ViewIDs
   (SceneID:0, SceneID:1, AllocatedID:50, AllocatedID:51, AllocatedID:99).
   Use the server to call `Network.AllocateViewID()` multiple times and
   send each result as an RPC param.

2. **Analyze**: Map input ViewID → 16-bit wire value. Look for bitfield
   structure (owner bits + index bits), shifted encoding, or compressed
   format.

3. **Document** the encoding in spec §14.

### Exit Criteria

- 16-bit NetworkViewID encoding fully decoded
- At least 5 known value pairs documented
- Encode/decode functions in `unity_protocol.py`
- Tests

---

## Milestone 9b: NetworkPlayer RPC Param

### Background

The RPC_NetworkPlayer experiment in M8 failed because the RPC was sent
before the connection was established. The encoding is likely int32 BE
(matching Distance's BitStreamWriter), but unverified.

### Work

1. **Experiment**: Fix timing in RpcNetworkPlayerExperiment — gate the RPC
   send on `OnPlayerConnected` (server) or `OnClientConnected` (client).
   Send `NetworkPlayer` values for both server (index 0) and client
   (index 1).

2. **Analyze**: Confirm encoding is int32 BE or discover otherwise.

3. **Document** in spec and update `_encode_params`/`_decode_params`.

### Exit Criteria

- NetworkPlayer RPC param encoding verified from capture
- Spec updated
- Tests

---

## Milestone 9c: Instantiate Prefab Identifier

### Background

The `__RPCNetworkInstantiate` params contain 133 bits of prefab identifier
data (bits 16-148) that isn't Huffman text or ASCII. The encoding might be
a hash, a serialized asset GUID, or an index.

### Work

1. **Experiment**: Create a second prefab ("NetworkPrefab2") and run
   Instantiate with it. Compare the 133-bit region between the two
   captures.

2. **Experiment**: Also vary the group parameter (0 vs 1) and check if
   it appears in the pre-transform or post-transform data.

3. **Analyze**: Differential analysis on the changed bits to isolate
   prefab identifier from group/ViewID/owner fields.

### Exit Criteria

- Prefab identifier field boundaries identified
- Group field location identified
- Spec §13.3 and §13.4 updated
- Decode support (at minimum field extraction, even if encoding is opaque)

---

## Milestone 9d: Code Cleanup (from M3/M7)

### Background

Deferred cleanup items from the M3 plan's milestone 7.

### Work

1. **Silent exception swallowing**: Replace bare `except Exception` in
   `unity_client.py` and `unity_server.py` with logging.

2. **Bit-length threading**: Ensure the RakNet encapsulated message
   `bit_length` is threaded through to `decode_rpc()` and
   `decode_state_sync()` instead of using `len(payload) * 8`.

3. **Import cleanup**: Remove any remaining `sys.path.insert` hacks.

4. **Verify `pip install -e .`** works with the existing `pyproject.toml`.

### Exit Criteria

- No silent exception swallowing in RPC/state sync handlers
- `bit_length` from RakNet header used everywhere
- `pip install -e .` works
- All tests pass

---

## Milestone 9e: End-to-End Interop Verification

### Background

The reference implementation has been tested in pieces (unit tests, single
captures) but not verified as a complete client→server→client flow recently.

### Work

1. **Python server ↔ Unity client**: Start `unity_server.py`, connect a
   Unity headless client, verify handshake + RPC + state sync all work.

2. **Python client ↔ Unity server**: Start a Unity headless server, connect
   `unity_client.py`, verify handshake + RPC reception.

3. **Fix any issues** discovered during interop testing.

### Exit Criteria

- Python server accepts Unity client connection and exchanges RPCs
- Python client connects to Unity server and receives RPCs
- No regressions in existing tests

---

## Implementation Order

```
9a (ViewID encoding)      — experiment, high value (unblocks 8f decode)
9b (NetworkPlayer param)  — experiment, quick fix
9c (Instantiate prefab)   — experiment, lower priority (Distance doesn't use it)
9d (Code cleanup)         — no experiments needed, can interleave
9e (End-to-end interop)   — final verification, do last
```

Recommended: **9d → 9a → 9b → 9c → 9e**

9d first because bit-length threading affects decode accuracy for 9a/9b.
9a before 9b because it unblocks the state sync decode from M8f.
9c is lowest priority since Distance doesn't use Network.Instantiate.
9e last as the integration gate.

## Decisions

- **Prefab encoding (9c)**: If two experiments don't crack the encoding,
  document what we know and move on. Distance doesn't use Instantiate.
- **State sync string type**: Unity docs say `BitStream.Serialize(ref string)`
  is unsupported. Not worth an experiment unless evidence suggests otherwise.
