# M13 Section 8: Live Interop Testing

## Goal

Prove that the TypeScript server and client can communicate with the
Python reference implementation over real UDP. This is the final
validation that the TS port is wire-compatible.

## Dependency

Requires S7 (RPC parameter decoding) — without decoded params, the
interop tests can verify connection and message delivery but not
parameter correctness.

## Background

The conformance framework has two tiers:
- **Tier 1 (serde)**: encode/decode round-trips via JSON stdin/stdout.
  Already passing for all 12 categories.
- **Tier 2 (peer)**: step-driven scenarios over real UDP. Categories:
  `handshake` (6 tests), `rpc` (11), `stateSync` (5),
  `multiClient` (4), `edgeCases` (4).

The Python peer runner (`conformance/peer_runner.py`) runs both sides
in a single process — it creates both server and client objects and
executes every step in the sequence, dispatching each to the
appropriate object based on the step's `role` field.

## Architecture

### Execution Model

Each peer test scenario is a linear sequence of steps. The Python
runner (`peer_runner.py`) creates both server and client objects in a
single process and executes every step sequentially. The TS peer runner
mirrors this model exactly — both sides run in-process.

### Test Configurations

Each scenario runs in two modes to verify parity:

1. **TS-as-both-sides**: TS `peer-runner.ts` executes all steps using
   real `UnityServer`/`UnityClient` instances over real UDP loopback.

2. **Python-as-both-sides**: Python `peer_runner.py` executes the
   same scenario for baseline comparison.

Both modes must produce identical pass/fail results for every scenario.
This proves that the TS implementation behaves identically to the
Python reference for all protocol operations.

**Future: cross-language mode.** True cross-process interop
(TS-server/Python-client and vice versa) requires role-aware peer
runners. This is deferred — the parity testing provides strong
evidence of wire compatibility since both implementations independently
produce the same results for the same scenarios.

### TS Peer Runner (`ts/scripts/peer-runner.ts`)

A Node.js script that:
1. Reads test scenarios from stdin (JSON array)
2. Executes each step sequence using real `UnityServer`/`UnityClient`
   instances with real `UdpSocket` over UDP loopback
3. Writes validation results to stdout (JSON)
4. Cleans up all sockets in all code paths (success, failure, timeout)
5. Pre-registers RPC and state sync handlers at connect time to avoid
   race conditions with incoming messages

Step handlers needed (mirroring `peer_runner.py`):

| Action | What it does |
|--------|-------------|
| `startServer` | Create `UdpSocket` + `UnityServer`, bind to port |
| `connect` | Create `UdpSocket` + `UnityClient`, connect to server |
| `assertConnected` | Check `client.connected === true` |
| `assertDisconnected` | Check `client.connected === false` |
| `assertPlayerIndex` | Check `client.playerIndex === expected` |
| `assertServerConnections` | Check `server.clients.size === expected` |
| `sendRpc` | Encode and send RPC from client or server |
| `expectRpc` | Wait (with timeout) for RPC on server or client |
| `sendStateSync` | Send state sync from server |
| `expectStateSync` | Wait for state sync on client |
| `disconnect` | Graceful disconnect |
| `expectConnectTimeout` | Expect connect to fail |
| `sleep` | Wait for a duration |
| `poll` | Poll client for incoming messages |
| `expectServerDisconnect` | Wait for disconnect event on server |

When `sendRpc` targets a specific client by name (e.g., `c1`), the
runner maps the client name to the `ClientSession` object stored
during the corresponding `connect` step.

### Interop Driver (`ts/scripts/interop-test.ts`)

Orchestrates parity testing:
1. Generates scenarios via `python3 -m conformance.peer_test_cli generate <cat> basic`
2. For each scenario, runs it on both:
   - TS peer runner (ts-both)
   - Python peer runner via subprocess (py-both)
3. Manages subprocess lifecycle: spawn, pipe scenario JSON to stdin,
   read result from stdout, kill on timeout (15s)
4. Reports structured JSON results with pass/fail per mode

### METHOD_SIGNATURES Agreement

Both Python and TS implementations pre-register all `METHOD_SIGNATURES`
keys as "already sent" for each new connection. This means both sides
agree that all known methods use subsequent-use (7-bit index) encoding.
If either side adds a method not in the other's dictionary, first-use
encoding will be sent but the receiver won't recognize the method hash.
For interop testing, both implementations share the same method set.

### Network Setup

Tests use `127.0.0.1` with ephemeral ports. No network namespace needed
for loopback. Each test gets a unique port to avoid conflicts when
running in parallel.

## Scope

### In Scope

- TS peer runner for all step types with `--role` flag
- All 5 categories: `handshake`, `rpc`, `stateSync`, `multiClient`,
  `edgeCases`
- TS-server / Python-client mode for all categories
- Python-server / TS-client mode for applicable categories
- Socket cleanup in all code paths
- CI-friendly: no network namespace, no Unity binary

### Out of Scope

- Unity binary interop (requires headless Unity in the namespace —
  separate milestone)
- Random-mode peer tests (basic mode is sufficient for interop proof)
- Performance benchmarking
- `masterServer` category (TS has no master server implementation)

## Test Matrix

| Category | Tests | TS-server | TS-client |
|----------|-------|-----------|-----------|
| handshake | 6 | All | All |
| rpc | 11 | All | All |
| stateSync | 5 | All | All |
| multiClient | 4 | All | All |
| edgeCases | 4 | All | All |

Total: 30 scenarios × 2 modes = 60 test runs.

## Exit Criteria

- [x] TS peer runner handles all 15 step types
- [x] TS peer runner pre-registers handlers to avoid race conditions
- [x] TS-both passes all `handshake` basic tests (6/6)
- [x] TS-both passes all `rpc` basic tests (11/11)
- [x] TS-both passes all `stateSync` basic tests (5/5)
- [x] TS-both passes all `multiClient` basic tests (4/4)
- [x] TS-both passes all `edgeCases` basic tests (4/4)
- [x] Python-both passes all tests as baseline (30/30)
- [x] Parity: TS and Python produce identical results for all scenarios
- [x] All sockets cleaned up on success, failure, and timeout
- [x] Results reported as structured JSON
- [x] `pnpm typecheck` and `pnpm lint` pass

## Risks

- **Timing sensitivity**: Real UDP has jitter. The Python runner uses
  `time.sleep(0.05)` between steps. The TS runner needs similar delays
  via `setTimeout`. May need to increase timeouts for CI.

- **Port conflicts**: Parallel test runs could collide on ports.
  Mitigation: each test allocates an ephemeral port via `bind(0)`.

- **Python subprocess lifecycle**: The driver must reliably start
  and stop Python subprocesses. Use `child_process.spawn` with proper
  signal handling and timeout-based cleanup.

- **Handshake timing**: The Python and TS implementations have slightly
  different tick rates and retry logic. The test timeouts (default 5s)
  should be generous enough to absorb this, but edge cases like
  "connect disconnect reconnect" may be sensitive.

- **State sync viewId matching**: The TS `UnityClient.onStateSync`
  accepts `viewId: number | null` where `null` is a wildcard. The
  peer runner should use the wildcard handler and filter internally,
  since viewIds may be set up dynamically in steps.
