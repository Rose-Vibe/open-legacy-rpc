# M14 S3: Unity Interop Testing

## Goal

Build a TS test driver that runs the 11 static Unity conformance scenarios
against a real Unity 2018.1.6f1 headless binary. The TS implementation
programs against the same scenarios that the Python `UnityTestRunner`
already handles, proving the TS client/server can interoperate with
actual Unity instances.

## Background

The Python conformance framework includes:

- `conformance/generators/unity/scenarios.py` — 11 static scenarios with
  actions like `startUnityServer`, `connectToUnity`, `sendRpc`,
  `waitForUnityLog`, `expectRpc`, etc.
- `conformance/unity_runner.py` — `UnityTestRunner` that starts Unity as
  a subprocess, connects with Python client/server, and validates via log
  polling and RPC callbacks.

The TS implementation needs an equivalent runner that:
1. Starts the Unity binary with the right experiment flags
2. Connects using the TS `UnityClient` / `UnityServer`
3. Validates behavior through the same step-driven scenario format

## Architecture

### TS Unity Runner (`ts/scripts/unity-runner.ts`)

A Node.js module that mirrors `conformance/unity_runner.py`:

- `UnityProcess` class: manages a Unity subprocess (`child_process.spawn`)
  with batchmode/nographics flags, log file tailing, and `waitForLog(pattern)`
- `UnityTestRunner` class: step-driven executor that handles all Unity
  scenario actions

### Action Handlers

| Action | Implementation |
|--------|---------------|
| `startUnityServer` | Spawn Unity binary with `--server --experiment <name> --port <port>`, wait for "Server ready" log |
| `startUnityClient` | Spawn Unity binary with `--client --experiment <name> --port <port> --address 127.0.0.1` |
| `connectToUnity` | Create `UdpSocket` + TS `UnityClient`, connect to Unity server on localhost:port |
| `assertConnected` | Check `client.connected === true` |
| `waitForUnityLog` | Poll Unity's log file for regex pattern match |
| `sendRpc` | Encode and send RPC via TS client |
| `expectRpc` | Register handler, poll TS client, wait for matching RPC |
| `expectServerRpc` | Wait for RPC on TS server from Unity client |
| `waitForUnityConnect` | Wait for Unity client to connect to TS server |
| `startPythonServer` | Create `UdpSocket` + TS `UnityServer`, pre-register RPC handlers, bind and listen (despite the name, creates a TS server in this context) |
| `disconnect` | Graceful disconnect |
| `sleep` | setTimeout-based wait |

### Test Driver (`ts/scripts/unity-test.ts`)

CLI entry point that:
1. Accepts optional scenario name filter
2. Imports scenarios from the Python framework via subprocess
   (`python3 -c "from conformance.generators.unity.scenarios import ..."`)
3. Runs each scenario through `UnityTestRunner`
4. Reports structured JSON results

### Log File Tailing

Unity writes logs to a specified path (`-logFile`). The TS runner:
1. Creates a temp directory for each test
2. Passes `-logFile <tempdir>/output_log.txt` to Unity
3. Periodically reads the file (every 200ms) looking for pattern matches
4. Checks if Unity process has exited (fast-fail on crash)
5. Cleans up temp dirs after test completion

### Network Namespace

Unity tests require the network namespace to avoid the RakNet >10 IP
crash. The test driver checks if it's running inside `unitynet` namespace
and warns/errors if not. The user runs:
```bash
sudo bash netns-setup.sh
sudo ip netns exec unitynet npx tsx ts/scripts/unity-test.ts
```

### Scenario Import

Rather than duplicating the 11 scenarios in TS, import them from Python:
```bash
python3 -c "
import json
from conformance.generators.unity.scenarios import SCENARIOS
print(json.dumps(list(SCENARIOS.values())))
"
```

This keeps a single source of truth for scenario definitions.

## Scope

### In Scope

- TS Unity process manager (start, log tail, stop)
- TS Unity test runner with all 12 action types
- Test driver CLI
- All 11 Unity scenarios:
  - unity-handshake (Python→Unity connect)
  - unity-handshake-password (with password)
  - unity-rpc-int (Python→Unity RPC_Int)
  - unity-rpc-string (Python→Unity RPC_String)
  - unity-rpc-bytes (Python→Unity RPC_Bytes)
  - unity-rpc-multitype (Python→Unity RPC_IntFloatString)
  - unity-rpc-receive (Unity→Python RPC_Int)
  - unity-state-sync (Unity→Python unreliable sync)
  - unity-state-sync-delta (Unity→Python delta sync)
  - unity-master-register (Unity→Python master server)
  - unity-disconnect (connect + disconnect lifecycle)
- Structured result output (JSON)

### Out of Scope

- Creating new Unity experiment scripts
- Modifying the Unity project
- Running without network namespace (Unity requirement)
- Automated CI integration (requires namespace + Unity binary)

## Exit Criteria

- [ ] `UnityProcess` class starts/stops Unity binary correctly
- [ ] Log file tailing finds patterns within timeout
- [ ] All 12 action handlers implemented
- [ ] unity-handshake passes
- [ ] unity-handshake-password passes
- [ ] unity-rpc-int passes
- [ ] unity-rpc-string passes
- [ ] unity-rpc-bytes passes
- [ ] unity-rpc-multitype passes
- [ ] unity-rpc-receive passes
- [ ] unity-state-sync passes (or skips gracefully if no sync handler)
- [ ] unity-state-sync-delta passes (or skips gracefully)
- [ ] unity-master-register passes (or skips if no master server impl)
- [ ] unity-disconnect passes
- [ ] `pnpm typecheck` and `pnpm lint` pass
- [ ] Test can run manually inside network namespace

## Risks

- **Unity binary availability**: The binary must exist at
  `UnityProject/Builds/Linux/Player.x86_64`. If missing, tests skip
  gracefully with a clear message.

- **Network namespace**: Tests must run inside `unitynet` namespace.
  The driver should detect this and fail with instructions if not.

- **Unity startup time**: Headless Unity can take 5-10 seconds to
  initialize. Log polling must be patient (15s default timeout).

- **State sync validation**: The current scenarios just sleep and
  disconnect — they don't validate sync data content. The TS runner
  can still pass these by connecting and disconnecting cleanly.

- **Master server scenario**: Uses `startPythonServer` action which
  creates a Python-side server. For the TS runner, this becomes a TS
  `UnityServer`. If the master server protocol differs, this may need
  special handling or be skipped initially.
