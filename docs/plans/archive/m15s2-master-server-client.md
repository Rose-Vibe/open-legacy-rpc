# M15 S2: Master Server and Client (TS)

## Goal

Port the Python `MasterServer` (367 lines) and `MasterClient` (172 lines)
to TypeScript, using the serialization layer from M15 S1 and the existing
TS RakNet transport.

## Background

The master server is a standalone service that game servers register with
and game clients query. It uses RakNet transport with `unity_protocol=false`
(no Unity framing, just raw LightweightDatabase messages).

Python implementation:
- `protocol/master_server.py` — `MasterServer` class with Table management,
  row CRUD, ping tracking, query filtering
- `protocol/master_client.py` — `MasterClient` class with register, query,
  unregister operations

## Architecture

### `ts/src/master/server.ts`

Port of `MasterServer`:

- `Table` class — column definitions, row storage, address-to-row mapping
- `MasterServer` class — wraps `RakNetServer` (non-Unity mode), handles
  UpdateRow/QueryRequest/RemoveRow messages, manages tables
- Event-driven (no polling) — message handling via RakNet callbacks

### `ts/src/master/client.ts`

Port of `MasterClient`:

- `MasterClient` class — wraps `RakNetClient` (non-Unity mode)
- `registerHost()` — send UpdateRow
- `requestHostList()` — send QueryRequest, return results
- `unregisterHost()` — send RemoveRow
- Promise-based API (vs Python's poll-based)

### Key Difference from Python

The Python implementation uses `unity_protocol=False` on RakNetServer/Client.
The TS RakNet layer needs to support this — messages arrive as raw RakNet
application data (msg_id is the first byte of payload, not wrapped in
Unity's 0x1b framing). Check if the TS RakNet already supports this or
if a flag/mode is needed.

## Exit Criteria

- [ ] `MasterServer` handles UpdateRow, QueryRequest, RemoveRow
- [ ] `MasterClient` can register, query, and unregister
- [ ] TS server ↔ TS client self-test passes (register + query round-trip)
- [ ] `pnpm typecheck` and `pnpm lint` pass
- [ ] Unit tests for server table operations and client workflows
