# Decode Safety Caps

## Goal

Add bounds checking and caps to all decode paths where attacker-controlled
length/count fields from the wire can cause unbounded allocation, CPU loops,
or silent data corruption. All caps log a warning when triggered so
legitimate edge cases don't silently break.

## Motivation

Pre-publication audit found 8 issues where crafted packets can DoS the server
through legitimate-but-expensive decode operations. The BitStream itself is
safe (throws on read-past-end), but loop counts and allocation sizes from
untrusted input aren't capped.

## Fixes

### HIGH — Unbounded allocations

#### Fix 1: Cap numColumns/numRows in decodeQueryReply

**TS:** `ts/src/master/serialization.ts` — `decodeQueryReply`
**Python:** `protocol/master_serialization.py` — `decode_query_reply`

- Cap `numColumns` at 1000, `numRows` at 100000.
- Log warning and throw/raise if exceeded.

#### Fix 2: Cap numEntries per row in decodeQueryReply

**TS:** `ts/src/master/serialization.ts`
**Python:** `protocol/master_serialization.py`

- Cap `numEntries` to `numColumns` (can't have more entries than columns).
- Log warning and throw/raise if exceeded.

#### Fix 3: Cap BINARY cell length

**TS:** `ts/src/master/serialization.ts` — `readCell` BINARY branch
**Python:** `protocol/master_serialization.py` — `read_cell` BINARY branch

- Cap at 16MB (16 * 1024 * 1024).
- Log warning and throw/raise if exceeded.

#### Fix 4: Cap Huffman/string bit length to remaining bits

**TS:** `ts/src/master/serialization.ts` — `readHuffmanString`
**TS:** `ts/src/unity/rpc.ts` — `decodeStringParam`
**Python:** `protocol/master_serialization.py` — Huffman decode
**Python:** `protocol/unity_protocol.py` — string param decode

- Clamp `bitLength` to `bs.remaining` (can't read more than what's there).
- Log warning if clamped.

### MEDIUM — CPU/memory amplification

#### Fix 5: Cap splitPacketCount

**TS:** `ts/src/raknet/reliability.ts` — split reassembly
**Python:** `protocol/raknet_transport.py` — split reassembly

- Cap `splitPacketCount` at 128 (128 * 1464 = ~187KB, well above any
  legitimate Unity message).
- Reject fragments with `splitPacketIndex >= splitPacketCount`.
- Log warning on rejection.

#### Fix 6: Clamp frame bitLength to actual payload size

**TS:** `ts/src/raknet/packet.ts` — frame parsing
**Python:** `protocol/raknet_transport.py` — frame parsing

- After slicing payload, if `bitLength > payload.length * 8`, clamp it.
- Log warning if clamped.

#### Fix 7: Cap ACK range span

**TS:** `ts/src/raknet/reliability.ts` — `handleAck`
**Python:** `protocol/raknet_transport.py` — ACK handling

- Cap each ACK range to span at most 10000.
- Log warning if a range is wider and skip it.

#### Fix 8: Guard decodeRpc minimum bit length

**TS:** `ts/src/unity/rpc.ts` — `decodeRpc`
**Python:** `protocol/unity_protocol.py` — `decode_rpc`

- Check `bitLength >= 88` (minimum for the shortest valid subsequent-use RPC:
  msg_id + timestamp + marker + first_use_bit + method_index) at the top.
- Throw BitStreamError / raise if too short. This converts an ambiguous
  mid-parse throw into a clear early rejection.

## Warning Logging

All caps use a `console.warn` (TS) / `log.warning` (Python) with a message
like: `"RakNet decode: <field> exceeds cap (<value> > <cap>), rejecting"`

This ensures legitimate uses that happen to hit the cap are visible in logs
rather than silently failing.

## Exit Criteria

1. All 8 fixes implemented in both TS and Python.
2. Existing test suites pass (no false positives from caps).
3. Each cap has at least one unit test that triggers it and verifies the
   warning/throw behavior.
4. TypeScript compiles cleanly.
