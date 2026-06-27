# M14 S2: Cross-Language Peer Testing

## Goal

Prove wire compatibility by running TS against Python peers cross-process.
Currently both peer runners execute both sides in-process (ts-both, py-both).
This milestone adds true cross-language modes:

- **TS-server / Python-client**: TS runs server steps, Python runs client steps
- **Python-server / TS-client**: Python runs server steps, TS runs client steps

## Background

The conformance framework generates step-driven scenarios. Each step has a
`role` field (`server` or a client name like `c1`). The current peer runners
ignore role boundaries — both sides run in the same process.

For cross-language testing, we need to split a scenario into server-side and
client-side step sequences, run them in separate processes, and synchronize
them enough that both sides make progress without timing out.

The user specified the flow as:
```
generate test → start python peer → start ts peer → fail at each step
if we errored or if python peer has exited with a fail
```

## Architecture

### Role-Aware Peer Runner Mode

Both TS and Python peer runners need a `--role` flag:
- `--role server` — execute server-side steps
- `--role client` — execute client-side steps (all client names: c1, c2, etc.)

Steps don't have a `role` field. Role ownership is inferred from the step's
`action`, `from`, `on`, and `client` fields:

**Server-owned steps:**
- `startServer`
- `assertServerConnections`
- `expectServerDisconnect`
- `sendRpc` / `sendStateSync` where `from: "server"`
- `expectRpc` / `expectStateSync` where `on: "server"`

**Client-owned steps:**
- `connect`, `disconnect`, `assertConnected`, `assertDisconnected`
- `assertPlayerIndex`, `expectConnectTimeout`
- `sendRpc` / `sendStateSync` where `from` is a client name or `"client"`
- `expectRpc` / `expectStateSync` where `on` is a client name or absent
  (default client)
- Steps with a `client` field (e.g., `{"action": "connect", "client": "c1"}`)

**Both-sides steps (always execute):**
- `sleep` — timing synchronization
- `poll` — both sides should poll to process messages

Steps belonging to the other role are treated as timing hints: the runner
waits a brief interval (matching the step's expected duration) to stay
roughly synchronized. This avoids the complexity of a cross-process
synchronization protocol.

### Wait Strategy for Non-Local Steps

When a runner encounters a step it doesn't own:

| Step Action | Wait Duration |
|------------|---------------|
| `startServer` | 0.5s (server startup) |
| `connect` | 1.0s (handshake) |
| `sendRpc` | 0.1s |
| `expectRpc` | 0.1s (other side is waiting) |
| `sendStateSync` | 0.1s |
| `expectStateSync` | 0.1s |
| `disconnect` | 0.3s |
| `sleep` | step.duration |
| `poll` | step.duration or 0.1s |
| `assertConnected` | 0s |
| `assertDisconnected` | 0s |
| `assertPlayerIndex` | 0s |
| `assertServerConnections` | 0.2s (convergence) |
| `expectConnectTimeout` | step.timeout or 3s |
| `expectServerDisconnect` | 0.5s |

### Cross-Language Driver

The test driver (`ts/scripts/interop-test.ts` or a new script) orchestrates:

1. Generate scenarios for a category
2. For each scenario:
   a. **TS-server/Py-client**: Start TS peer-runner as server subprocess,
      start Python peer-runner as client subprocess, wait for both, check
      both exit codes
   b. **Py-server/TS-client**: Start Python peer-runner as server subprocess,
      start TS peer-runner as client subprocess, wait for both, check both
      exit codes
3. Report structured results

Each subprocess gets the full scenario JSON on stdin plus `--role server`
or `--role client`. The driver monitors both processes and fails fast if
either exits with a non-zero code.

### Port Assignment

The driver assigns each scenario a unique port and passes it via the
scenario JSON's `port` field (already supported by both runners).

### Python Peer Runner Changes

Add `--role` flag to `conformance/peer_runner.py`:
- Accept `--role server` or `--role client` via CLI
- When set, the runner skips execution of steps whose `role` doesn't match
- For skipped steps, sleep the appropriate wait duration
- The existing both-sides mode remains the default (no `--role` flag)

### TS Peer Runner Changes

Add `--role` flag to `ts/scripts/peer-runner.ts`:
- Same behavior as Python: skip non-matching steps, wait instead
- Already accepts scenario JSON on stdin

### Multi-Client Considerations

Some scenarios have multiple clients (`c1`, `c2`, `c3`, `c4`). For
cross-language testing, `--role client` should handle ALL client roles.
The test proves that one implementation's server works with the other's
client(s), not that individual client instances cross boundaries.

## Scope

### In Scope

- `--role` flag for both TS and Python peer runners
- Cross-language driver (extend `interop-test.ts` or new script)
- All 5 peer categories: handshake (6), rpc (11), stateSync (5),
  multiClient (4), edgeCases (4) = 30 scenarios
- Two cross-language modes per scenario = 60 additional test runs
- Structured result reporting

### Out of Scope

- Unity binary interop (separate milestone M14 S3)
- masterServer category (TS has no master server)
- Random-mode scenarios (basic mode is sufficient)
- Performance measurement

## Test Matrix

| Category | Tests | TS-server/Py-client | Py-server/TS-client |
|----------|-------|---------------------|---------------------|
| handshake | 6 | All | All |
| rpc | 11 | All | All |
| stateSync | 5 | All | All |
| multiClient | 4 | All | All |
| edgeCases | 4 | All | All |

Total: 30 scenarios × 2 cross-language modes = 60 test runs.

## Exit Criteria

- [ ] Python peer runner accepts `--role server` and `--role client`
- [ ] TS peer runner accepts `--role server` and `--role client`
- [ ] Role-aware runners correctly execute only their role's steps
- [ ] Cross-language driver runs TS-server/Py-client for all 30 scenarios
- [ ] Cross-language driver runs Py-server/TS-client for all 30 scenarios
- [ ] All 60 cross-language test runs pass
- [ ] Existing both-sides modes still pass (no regression)
- [ ] Structured JSON results with pass/fail per mode
- [ ] `pnpm typecheck` and `pnpm lint` pass

## Risks

- **Timing sensitivity**: Cross-process synchronization relies on wait
  durations. If waits are too short, the other side hasn't completed its
  step yet. Mitigation: generous waits + the existing timeout mechanisms
  in `expectRpc`/`assertConnected`.

- **Port races**: Both processes must agree on the port before the client
  connects. Mitigation: driver assigns port, passes in scenario JSON.

- **Multi-client edge cases**: Scenarios with 4 clients may be sensitive
  to connection ordering. The client runner handles all client roles
  sequentially, which should match the scenario's step order.
