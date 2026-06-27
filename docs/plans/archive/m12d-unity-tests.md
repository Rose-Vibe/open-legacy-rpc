# M12d: Unity Peer Tests

## Goal

Pre-built test scenarios against real Unity 2018.1.6f1 server/client binaries.
Each scenario mirrors a subset of the Python peer tests (M12c) so that:

1. If a test passes against Python but fails against Unity, the discrepancy
   is in the Python reference implementation
2. Debugging can happen against the Python peer (faster iteration) before
   retrying against Unity

## Architecture

### Unity Test Builds

Each scenario requires a specific Unity build (server + client). These are
built from the existing experiment project at `experiments/` using the
DLL-injection pattern established in earlier milestones.

Since Unity builds are static (no stdin/stdout step protocol), the test
runner uses **hardcoded step sequences** that match the Unity build's
behavior. The tested implementation follows the same steps as in M12c,
but against a real Unity binary instead of the Python peer.

### Test Runner

```
Usage:
  legacy-net-peer-test unity <scenario> [--unity-path PATH]

1. Starts the Unity server or client binary
2. Outputs step instructions to stdout (same JSON format as M12c)
3. The tested implementation follows the steps
4. Runner validates by observing the Unity process (exit code, log output)
5. Outputs validation JSON
```

The runner reuses the step format from M12c. An implementation that passes
M12c should be able to run M12d with no code changes — just different
step sequences and a Unity binary as the peer.

### Unity Process Management

- Server: launched with `-batchmode -nographics` and appropriate args
- Client: same, headless mode
- Network namespace: uses `netns-setup.sh` to avoid RakNet IP limit crash
- Logs: Unity's `output_log.txt` is captured for debugging
- Timeout: Unity process is killed after test timeout (30s default)
- Exit: clean exit = success; crash or timeout = test infrastructure failure

## Test Scenarios

Each scenario is identified by name and maps to a Unity experiment build.

### 1. `unity-handshake` — Basic Connection

**Mirrors:** M12c `handshake` preset #1

**Unity side:** Server, listens on port 7777, accepts one connection
**Impl side:** Client, connects to 127.0.0.1:7777

**Steps:**
1. Runner starts Unity server
2. Runner outputs: `{"action": "connect", "host": "127.0.0.1", "port": 7777}`
3. Impl connects
4. Impl reports: `{"stepIndex": 0, "status": "done"}`
5. Runner waits 2s for Unity to log "Player connected"
6. Runner outputs validation: pass if Unity logged connection

**Unity experiment:** `BasicServerExperiment` (existing or minimal new build)

---

### 2. `unity-handshake-password` — Password Authentication

**Mirrors:** M12c `handshake` preset #4

**Unity side:** Server with `Network.incomingPassword = "test123"`
**Impl side:** Client connects with password "test123"

**Steps:** Same as #1 but with password

---

### 3. `unity-rpc-int` — Integer RPC

**Mirrors:** M12c `rpc` preset #1

**Unity side:** Server, has `[RPC] void RPC_Int(int x)` that logs received value
**Impl side:** Client, sends `RPC_Int(42)` after connecting

**Steps:**
1. Connect (as above)
2. `{"action": "sendRpc", "methodName": "RPC_Int", "params": [{"type": "int", "value": 42}], "mode": "Server", "viewId": {"scope": "scene", "id": 0}}`
3. Runner checks Unity log for "RPC_Int received: 42"

---

### 4. `unity-rpc-string` — String RPC

**Mirrors:** M12c `rpc` preset #3

**Unity side:** Server with `[RPC] void RPC_String(string s)`
**Impl side:** Sends `RPC_String("hello")`

---

### 5. `unity-rpc-bytes` — Byte Array RPC

**Mirrors:** M12c `rpc` preset #6

**Unity side:** Server with `[RPC] void RPC_Bytes(byte[] data)`
**Impl side:** Sends `RPC_Bytes(known test data)`

---

### 6. `unity-rpc-multitype` — Multi-Parameter RPC

**Mirrors:** M12c `rpc` preset #7

**Unity side:** Server with `[RPC] void RPC_IntFloatString(int, float, string)`
**Impl side:** Sends `RPC_IntFloatString(1, 2.0, "hi")`

---

### 7. `unity-rpc-receive` — RPC from Unity to Impl

**Mirrors:** M12c `rpc` preset #9 (reverse direction)

**Unity side:** Server sends an RPC to connected client after 1s delay
**Impl side:** Client expects the RPC and validates params

**Steps:**
1. Connect
2. `{"action": "expectRpc", "methodName": "RPC_Int", "params": [{"type": "int", "value": 99}], "timeout": 5.0}`
3. Runner validates impl received correct params

---

### 8. `unity-state-sync` — State Sync from Unity

**Mirrors:** M12c `stateSync` preset #1

**Unity side:** Server with `OnSerializeNetworkView` writing a float
**Impl side:** Client expects state sync messages

---

### 9. `unity-state-sync-delta` — Delta Compressed State Sync

**Mirrors:** M12c `stateSync` preset #3

**Unity side:** Server with `ReliableDeltaCompressed` NetworkView
**Impl side:** Client decodes delta sync messages

---

### 10. `unity-master-server` — Master Server Registration

**Mirrors:** M12c `masterServer` preset #1

**Unity side:** Client calls `MasterServer.RegisterHost` against Python master server
**Impl side:** Runs Python master server, validates registration arrives

This scenario is inverted: Unity is the client, Python is the server.

---

### 11. `unity-master-query` — Master Server Query

**Mirrors:** M12c `masterServer` preset #1 (query part)

**Unity side:** Client calls `MasterServer.RequestHostList` against Python master server
**Impl side:** Runs Python master server with pre-registered host, validates Unity
receives the correct host list (check Unity log output)

---

### 12. `unity-disconnect` — Disconnect Cleanup

**Mirrors:** M12c `handshake` preset #3

**Unity side:** Server
**Impl side:** Client connects then disconnects
**Validates:** Unity logs "Player disconnected", server continues running

## Unity Experiment Builds Required

| Scenario | Experiment Name | New Build? | Notes |
|----------|----------------|------------|-------|
| 1, 12 | `BasicServerExperiment` | Maybe | May already exist from M8-M10 |
| 2 | `PasswordServerExperiment` | Maybe | May exist from M10e |
| 3–6 | `RPCServerExperiment` | Exists | From M8 experiments |
| 7 | `RPCSendExperiment` | May need | Server that sends RPC to client |
| 8–9 | `StateSyncExperiment` | Exists | From M8 experiments |
| 10–11 | `MasterServerExperiment` | Exists | From M11 |

Most builds already exist from prior milestones. New builds are minimal
DLL changes to the existing experiment project.

## Exit Criteria

- [ ] All 12 scenarios runnable
- [ ] Each scenario's step sequence matches the corresponding M12c test
- [ ] Pass/fail output uses the same JSON format as M12c
- [ ] Unity process management (start, monitor, kill) is robust
- [ ] Log parsing extracts validation data from Unity's output_log.txt
- [ ] Documentation maps each scenario to its M12c counterpart
- [ ] At least scenarios 1, 3, 7, 8 pass with the Python reference impl
  acting as the tested implementation (proving the test infrastructure works)
