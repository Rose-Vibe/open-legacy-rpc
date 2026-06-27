# M15 S3: Master Server Cross-Language Tests

## Goal

Verify TS and Python master server implementations are interoperable:
TS client ↔ Python server, Python client ↔ TS server, and both against
a real Unity instance.

## Background

M14 S2 established the cross-language peer test infrastructure
(`interop-test.ts` with 4 modes). M15 S3 extends this to the master
server protocol.

## Architecture

### Peer Tests

New conformance scenarios for master server operations:

- **register-query** — client registers a host, another client queries
  and finds it
- **register-unregister** — register then remove, verify query returns
  empty
- **password-protected** — table with password, verify rejection on wrong
  password
- **multiple-registrations** — several servers register, query returns all

Run in 4 modes: ts-both, py-both, ts-server/py-client, py-server/ts-client.

### Unity Tests

Update the Unity conformance scenarios to use the TS master server:

- **unity-master-register** — remove the `startMasterServer` skip in TS
  runner, use the new TS `MasterServer` instead
- Verify Unity's `MasterServer.RegisterHost` reaches the TS server and
  produces a valid table row

### Test Infrastructure

- Add master server scenarios to `conformance/generators/` (or a new
  `master/` subdirectory)
- Extend `interop-test.ts` to include master server test category
- Update `unity-runner.ts` to use TS `MasterServer` for the
  `startMasterServer` action

## Exit Criteria

- [ ] 4-mode peer tests pass for register/query/unregister
- [ ] Unity master-register test passes with TS server (no skip)
- [ ] Python ↔ TS cross-language tests pass
- [ ] All existing tests continue to pass
- [ ] `pnpm typecheck` and `pnpm lint` pass
