# M15 S1: Master Server Serialization (TS)

## Goal

Port the LightweightDatabase wire format encoding/decoding from
`protocol/master_serialization.py` (339 lines) to TypeScript. This is the
foundation for both master server and master client.

## Background

The Unity Master Server protocol uses RakNet's LightweightDatabaseServer
plugin. Messages are:

- `UpdateRow` (76) — register/update a game server
- `QueryRequest` (75) — search for servers
- `RemoveRow` (77) — unregister
- `QueryReply` (78) — server list response
- `RowId` (200) — row ID assignment
- `UnknownTable` (79) / `IncorrectPassword` (80) — errors

The Python `master_serialization.py` handles all encode/decode for these
messages using BitStream and Huffman StringCompressor — both already
ported to TS.

## Architecture

### `ts/src/master/serialization.ts`

Port of `protocol/master_serialization.py`:

- Constants: message IDs, column types, update modes, filter operations
- `encodeUpdateRow` / `decodeUpdateRow`
- `encodeQueryRequest` / `decodeQueryRequest`
- `encodeRemoveRow` / `decodeRemoveRow`
- `encodeQueryReply` / `decodeQueryReply`
- `encodeRowId` / `decodeRowId` (if present in Python)
- `encodeUnknownTable` / `encodeIncorrectPassword` — error responses
- Huffman string read/write helpers wrapping the existing TS BitStream

### Conformance

Existing serde test generators in `conformance/generators/serde/` already
produce test vectors for these messages. The TS conformance runner should
already pick them up once the decoders are registered.

## Exit Criteria

- [ ] All message types encode/decode matching Python output
- [ ] Existing serde conformance tests pass for master protocol messages
- [ ] `pnpm typecheck` and `pnpm lint` pass
- [ ] Unit tests for round-trip encode/decode
