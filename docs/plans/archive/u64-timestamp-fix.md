# Fix: Write u64 Timestamp in RPC Bytes 1-8

## Problem

Our RPC encoder writes `[0x1B][viewId 6 bytes][counter16 2 bytes][0x0B][...]`
in bytes 1-8. Unity writes `[0x1B][u64 BE senderRakNetGetTimeMS()][0x0B][...]`.

RakNet's `ShiftIncomingTimestamp` reads bytes 1-8 as a u64 and subtracts
`clockDiff`. With the correct u64, the result is `clientRakNetTimeMS` and
`info.timestamp ≈ Network.time`. With our truncated/wrong bytes, the
subtraction produces garbage — confirmed by bridge server comparison data
showing `info.timestamp=941` vs `Network.time=24` with our server, but
`info.timestamp≈Network.time≈171` with the bridge.

## Root Cause

Two bugs:
1. `server.ts:237` — `uptimeMs & 0xffff` truncates timestamp to 16 bits
2. `rpc.ts:195-200` — writes viewId(48 bits) + counter16(16 bits) instead
   of a u64 timestamp. The viewId is NOT at bytes 1-6; it's in the RPC
   bitstream at the routing constant position (already handled by `targetView`).

## Changes

### `ts/src/unity/rpc.ts`

**RpcEncodeOptions**: Rename `rpcCounter` → `timestampMs` (full millisecond
timestamp, not a 16-bit counter).

**encodeRpcSubsequent / encodeRpcFirstUse**: Replace the 6-byte viewId +
2-byte counter16 write with a single 8-byte u64 BE write of `timestampMs`.
BitStream has no `writeU64BE`, so write as two `writeU32BE` calls (high 32
then low 32). Remove the `encodeViewId` import usage in the header.

**DecodedRpc**: Rename `rpcCounter` → `timestampMs`. Remove `viewId`
(was reading timestamp bytes as viewId — always wrong).

**decodeRpc**: Read bytes 1-8 as u64 (two u32 reads → combine). Store as
`timestampMs`. Remove viewId decode from bytes 1-6.

### `ts/src/unity/server.ts`

Remove `& 0xffff` truncation at line 237. Pass full `uptimeMs` as
`timestampMs` instead of `rpcCounter`. Remove `lastRpcViewId` assignment
(was storing timestamp bytes as viewId — dead code, never read).

### `ts/src/unity/client.ts`

Add `epochNs` capture at construction. Replace incrementing `rpcCounter`
with `(hrtime - epochNs) / 1M` to match the server pattern. Pass as
`timestampMs`.

### `protocol/unity_protocol.py`

Same changes: write u64 BE timestamp at bytes 1-8 instead of viewId +
counter16. Rename `rpc_counter` → `timestamp_ms` in encode functions.
Update decoder to read u64 from bytes 1-8.

### `protocol/unity_server.py`

Replace `_rpc_counters` (sequential counter per peer) with uptime-based
timestamps.

### Tests

- Update all `rpcCounter` → `timestampMs` references
- Update `viewId` assertions in decoded output (remove or change)
- Replace "counter wraps at 65536" test with a u64 round-trip test
- Replace "captures viewId from header" test with timestamp round-trip

## Exit Criteria

- [ ] TS encoder writes u64 BE timestamp at bytes 1-8
- [ ] TS decoder reads u64 timestamp from bytes 1-8
- [ ] Server passes full uptimeMs, no truncation
- [ ] Client uses uptime-based timestamp
- [ ] Python encoder/decoder updated to match
- [ ] All existing tests pass (with updated assertions)
- [ ] New test: u64 timestamp > 65535 round-trips correctly
