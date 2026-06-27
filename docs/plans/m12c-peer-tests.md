# M12c: Python Peer Tests

## Goal

Implement test scenarios where a Python server or client acts as the
"known-good" peer and the tested implementation connects to it. Tests
are step-driven: each step tells either the Python peer or the tested
implementation what to do next.

## Architecture

### Step Model

Each test scenario is a sequence of steps. Steps have a `role` field:

- `"peer"` — executed by the Python test runner (the known-good side)
- `"impl"` — instructions the tested implementation must follow

The Python runner executes its own steps internally and outputs the `impl`
steps as JSON lines to stdout so the tested implementation knows what to
do. After each `impl` step, the runner waits for the implementation to
report completion before continuing.

### Communication Protocol

```
                  Python Runner (legacy-net-peer-test run)
                     ↕ UDP (actual protocol traffic)
                  Tested Implementation
                     ↕ stdin/stdout (JSON step instructions)
                  Test Harness (whatever drives the impl)
```

**stdout from Python runner:**
- Step instructions (JSON lines): `{"step": "connect", "host": "127.0.0.1", "port": 7777}`
- Validation results: `{"testInfo": {...}, "validation": {"pass": true, ...}}`

**stdin to Python runner:**
- Step completion signals: `{"stepIndex": 0, "status": "done"}`
- Step completion with data: `{"stepIndex": 0, "status": "done", "data": {...}}`

### Step Types

Common fields: `{"stepIndex": N, "role": "peer|impl", "action": "...", ...}`

#### Connection Steps
- `connect` — connect to the peer
  - impl: `{"action": "connect", "host": "...", "port": N}`
  - peer: starts listening or connects
- `disconnect` — graceful disconnect
- `waitForConnection` — peer waits for incoming connection
- `assertConnected` — verify connection state

#### RPC Steps
- `sendRpc` — send an RPC
  - `{"action": "sendRpc", "methodName": "...", "params": [...], "mode": "...", "viewId": {...}}`
- `expectRpc` — wait for and validate an incoming RPC
  - `{"action": "expectRpc", "methodName": "...", "params": [...], "timeout": 5.0}`
- `sendFirstUseRpc` — send using first-use format
- `expectFirstUseRpc` — expect first-use format

#### State Sync Steps
- `sendStateSync` — send unreliable state sync
  - `{"action": "sendStateSync", "viewId": {...}, "fields": [...]}`
- `expectStateSync` — wait for state sync
- `sendDeltaSync` — send reliable delta compressed
- `expectDeltaSync` — wait for delta sync

#### Master Server Steps
- `registerHost` — register with master server
  - `{"action": "registerHost", "gameType": "...", "name": "...", ...}`
- `expectRowId` — wait for RowID response
- `requestHostList` — query host list
- `expectHostList` — wait for and validate host list
- `unregisterHost` — remove registration

#### Raw Steps
- `sendRaw` — send raw bytes (for testing error handling)
  - `{"action": "sendRaw", "dataHex": "...", "reliability": "RELIABLE_ORDERED"}`
- `expectRaw` — wait for raw bytes matching a pattern
- `expectDisconnect` — wait for the peer to disconnect us
- `sleep` — pause for a duration (e.g., waiting for timeout behavior)

## Test Categories

### 1. `handshake` — Connection Handshake

Tests the RakNet + Unity handshake sequence.

**Preset tests:**

| # | Name | Steps | What it validates |
|---|------|-------|-------------------|
| 1 | Basic connect | peer:listen → impl:connect → peer:assertConnected | Full handshake completes |
| 2 | Client connect | peer:connect → impl:listen → impl:assertConnected | Reversed roles |
| 3 | Connect + disconnect | connect → assertConnected → impl:disconnect → peer:expectDisconnect | Graceful teardown |
| 4 | Password auth | peer:listen(password="test") → impl:connect(password="test") → assertConnected | Password handshake |
| 5 | Wrong password | peer:listen(password="test") → impl:connect(password="wrong") → impl:expectDisconnect | Rejection |
| 6 | Player assignment | connect → peer:assertPlayerIndex(impl, 0) | 0x81 ViewID block |

**Random tests:**
- Random password strings (including empty, special chars)
- Multiple sequential connect/disconnect cycles

---

### 2. `rpc` — RPC Send/Receive

**Preset tests:**

| # | Name | Steps | What it validates |
|---|------|-------|-------------------|
| 1 | Int RPC | connect → impl:sendRpc(RPC_Int, [42]) → peer:expectRpc(RPC_Int, [42]) | Basic int param |
| 2 | Float RPC | sendRpc(RPC_Float, [3.14]) → expectRpc | Float precision |
| 3 | String RPC | sendRpc(RPC_String, ["hello"]) → expectRpc | Huffman string |
| 4 | Bytes RPC | sendRpc(RPC_Bytes, ["deadbeef"]) → expectRpc | byte[] param |
| 5 | Vector3 RPC | sendRpc(RPC_Vector3, [1,2,3]) → expectRpc | Vector3 param |
| 6 | Quaternion RPC | sendRpc(RPC_Quaternion, [0,0,0,1]) → expectRpc | Quaternion param |
| 7 | Multi-param RPC | sendRpc(RPC_IntFloatString, [1, 2.0, "hi"]) → expectRpc | Multiple params |
| 8 | Void RPC | sendRpc(RPC_Void, []) → expectRpc | No params |
| 9 | Bidirectional | impl:send → peer:expect → peer:send → impl:expect | Both directions |
| 10 | RPCMode.Server | impl:sendRpc(mode=Server) → peer:expectRpc | Mode encoding |
| 11 | RPCMode.Others | (3 clients) client1:send(Others) → client2:expect, client3:expect | Broadcast |
| 12 | Large byte[] | sendRpc(RPC_Bytes, [10KB]) → expectRpc | Split packet |
| 13 | RPC counter sequence | send 5 RPCs → expect all 5 with incrementing counters | Counter tracking |
| 14 | First-use RPC | impl:sendFirstUse → peer:expectFirstUse | First-use format |
| 15 | ViewID param RPC | sendRpc(RPC_NetworkViewID, [...]) → expectRpc | 16-bit ViewID param |
| 16 | NetworkPlayer param | sendRpc(RPC_NetworkPlayer, [0]) → expectRpc | Player index param |

**Random tests:**
- Random method from known set, random valid params
- Random sequence of 3–10 RPCs
- Random byte[] payloads (size 0–5000)

---

### 3. `stateSync` — State Synchronization

**Preset tests:**

| # | Name | Steps | What it validates |
|---|------|-------|-------------------|
| 1 | Float sync | connect → impl:sendStateSync(float) → peer:expectStateSync | Basic unreliable |
| 2 | Multi-field sync | sendStateSync(int, float, Vector3) → expectStateSync | Multiple fields |
| 3 | Delta sync (first) | sendDeltaSync(isFirst=true) → expectDeltaSync | Full initial send |
| 4 | Delta sync (update) | sendDeltaSync(prev) → expectDeltaSync | Dirty flag encoding |
| 5 | Delta no changes | sendDeltaSync(same values) → expectDeltaSync(no dirty) | Zero-diff delta |
| 6 | Bidirectional sync | impl:send → peer:expect → peer:send → impl:expect | Both directions |
| 7 | Mixed views | send to viewId 0 + viewId 1 → expect both | Multiple NetworkViews |

**Random tests:**
- Random field types and values, 1–8 fields
- Random delta sequences (3–5 updates with random changes)

---

### 4. `masterServer` — Master Server Operations

**Preset tests:**

| # | Name | Steps | What it validates |
|---|------|-------|-------------------|
| 1 | Register + query | impl:register("TestGame", "Server1") → peer:query("TestGame") → peer:expectHostList([Server1]) | Basic registration |
| 2 | Multiple registrations | register 3 hosts → query → expectHostList(3 entries) | Multi-row |
| 3 | Unregister | register → unregister → query → expectHostList([]) | Row removal |
| 4 | Query empty table | query("NonExistent") → expectHostList([]) | Empty response |
| 5 | Disconnect removes | register → disconnect → query → expectHostList([]) | Cleanup |
| 6 | Multiple game types | register("Game1") + register("Game2") → query each → correct isolation | Table isolation |
| 7 | Filter query | register(port=7777) + register(port=8888) → query(filter port=7777) → expect 1 result | Filter operation |
| 8 | IP injection | register → query → host.ip == actual_addr | Server overrides IP |
| 9 | Version mismatch | connect → send UpdateRow with wrong version → expect error msg | Version check |

**Random tests:**
- Random game type names, server names, comments
- Random port numbers, player counts
- Random filter combinations

---

### 5. `multiClient` — Multi-Client Scenarios

**Preset tests:**

| # | Name | Steps | What it validates |
|---|------|-------|-------------------|
| 1 | Two clients | client1:connect + client2:connect → server:assertBothConnected | Multi-peer |
| 2 | RPCMode.Others broadcast | client1:sendRpc(Others) → client2:expectRpc (server relays) | Broadcast relay |
| 3 | RPCMode.Player targeted | client1:sendRpc(Player, target=1) → client2:expectRpc | Targeted relay |
| 4 | Client disconnect cleanup | client1:disconnect → server:assertRemoved | Connection tracking |

---

### 6. `edgeCases` — Error Handling and Edge Cases

**Preset tests:**

| # | Name | Steps | What it validates |
|---|------|-------|-------------------|
| 1 | Rapid reconnect | connect → disconnect → connect | Connection reuse |
| 2 | Duplicate connect | connect → connect again → second fails or is idempotent | Double-connect |
| 3 | Send before connect | sendRpc without connecting → error | Pre-connect send |
| 4 | Empty RPC name | Valid encoding with edge-case name | Boundary |
| 5 | Max-size payload | 1400-byte payload (near MTU) | Fragment boundary |

## Output Format

For each test, the Python runner outputs a JSON validation object:

```json
{
  "testInfo": {
    "testId": "uuid",
    "testName": "Basic connect",
    "testDescription": "Tests full handshake sequence",
    "category": "handshake",
    "mode": "basic"
  },
  "validation": {
    "pass": true,
    "failures": []
  }
}
```

On failure, the runner exits after outputting the validation with `pass: false`
and the `failures` list populated.

## Exit Criteria

- [ ] All 6 categories implemented (generate + run)
- [ ] All preset tests pass with Python-as-both-sides (reference → reference)
- [ ] Step protocol documented (stdin/stdout JSON lines format)
- [ ] Timeout handling: steps that wait for network events have configurable timeouts
- [ ] Clean shutdown on test completion or failure
- [ ] Random tests with seed=0 pass reference-vs-reference
