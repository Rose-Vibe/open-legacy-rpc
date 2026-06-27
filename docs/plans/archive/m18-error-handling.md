# M18: Error Handling & Defensive Coding

## Motivation

An audit of both Python and TS implementations revealed systematic error
handling gaps. The two biggest issues are: (1) TS BitStream has zero read
bounds checking — reads past the end return garbage from uninitialized
memory, and (2) catch-all blocks swallow programming errors alongside
parse errors, making bugs invisible. This milestone fixes all findings.

## Deliverables

### D1: TS BitStream bounds checking

**Problem:** `readBit()` in `bitstream.ts:62` reads past `_bitLength`
without any check. Every read method inherits this. Malformed packets
produce silent garbage instead of errors.

**Fix:**
- Add bounds check to `readBit()` — throw `BitStreamError` when
  `_pos >= _bitLength` (match Python's `BitStreamError`)
- Export `BitStreamError` from `bitstream.ts` and `index.ts`
- Add tests: read past end throws, empty stream throws

### D2: Narrow catch-all blocks (both languages)

**Problem:** 4 TS catch blocks (`server.ts:250`, `server.ts:264`,
`client.ts:169`, `client.ts:186`) and 3 Python catch blocks
(`unity_server.py:258`, `unity_client.py:118`, `unity_client.py:130`)
use bare `catch`/`except Exception` that swallow all errors including
programming bugs in user handlers. The 3 master_server.py catch blocks
(`195`, `263`, `295`) also lack exception details in their log messages.

**Fix (TS):**
- Split `handleRpc` and `handleStateSync` in both `server.ts` and
  `client.ts` so that decode errors are caught but handler errors
  propagate. Pattern:
  ```
  let decoded;
  try { decoded = decodeRpc(...); } catch { return; }
  // handler runs outside try/catch — bugs propagate
  ```
- Add `console.warn` or emit an event on decode failures (not silent)

**Fix (Python):**
- Same pattern: catch decode errors, let handler errors propagate
- Include `exc_info=True` in all warning logs (already present in
  unity_server/client, missing in master_server)
- Add exception repr to master_server log messages

### D3: Fix `val or default` param encoding (both languages)

**Problem:** Python `_encode_params` uses `val or 0` which treats `0`,
`0.0`, `''`, `b''`, and `False` as missing (all falsy). TS `encodeParams`
uses `typeof val === 'number' ? val : 0` which is better but still
coerces `undefined` silently.

**Fix (Python):**
- Replace `val or 0` with `val if val is not None else 0`
- Replace `val or 0.0` with `val if val is not None else 0.0`
- Replace `val or ''` with `val if val is not None else ''`
- Same pattern for all param types

**Fix (TS):**
- Already uses typeof checks — no change needed for TS (the `typeof`
  guards already distinguish 0 from undefined correctly)

### D4: RakNet silent payload truncation (Python)

**Problem:** `raknet.py:209` and `raknet_transport.py:147` silently
truncate payloads when `end > len(data)`. Downstream code processes
a shorter payload than `bit_length` claims, causing silent corruption.

**Fix:**
- In `raknet.py:209`: log a warning when truncating, and set
  `msg.bit_length` to the actual available bits (not the claimed bits)
- In `raknet_transport.py:147`: same — adjust `bit_length` to match
  actual payload size when truncation occurs
- This prevents BitStream from claiming more bits are available than
  actually exist, so the M17 bounds check fires correctly

### D5: RPCMode enum crash on invalid wire value (Python)

**Problem:** `unity_protocol.py:371` does `RPCMode(bs.read_bits(4))`
which raises `ValueError` for values 4, 7-15. This crashes `decode_rpc`
and gets swallowed by the catch-all.

**Fix:**
- Use `RPCMode(val)` inside a try/except, falling back to storing the
  raw integer and a string like `'unknown_4'` in the result
- Or switch to a dict lookup: `RPC_MODE_NAMES.get(val, f'unknown_{val}')`
  (matches TS's approach at `rpc.ts:269`)

### D6: TS master serialization cellIdx bounds check

**Problem:** `master/serialization.ts:346` does
`const col = columns[cellIdx] as Column` where `cellIdx` comes from
untrusted wire data. If `cellIdx >= columns.length`, `col` is
`undefined` cast to `Column`, and `col.name` throws an unhelpful
TypeError. (Python side was fixed in M17.)

**Fix:**
- Add bounds check before the cast:
  `if (cellIdx >= columns.length) throw new Error(...)`

### D7: TS `readBits(48)`/`readBits(64)` overflow

**Problem:** JS bitwise ops are 32-bit. `readBits(48)` and
`readBits(64)` silently overflow. `decodeViewIdBits` in `view-id.ts:30`
calls `readBits(48)`. Master serialization POINTER type uses 64-bit.

**Fix:**
- Add `readBitsBigInt(n)` or `readU48BE()` method that uses BigInt
  for >32-bit reads
- Or: fix `decodeViewIdBits` to use three 16-bit reads (like
  `decodeRpc` already does), and fix POINTER to use two 32-bit reads
- The pragmatic fix is the second option — avoid BigInt, just read
  in safe chunks

### D8: Python `send_raw` silent OSError swallow

**Problem:** `raknet_transport.py:311` catches `(OSError, AttributeError)`
and silently passes. Systematic send failures (socket closed, network
down) produce zero indication.

**Fix:**
- Log at DEBUG level on OSError (common during shutdown/disconnect)
- Remove `AttributeError` from the catch — that masks bugs where
  `self.sock` is None

### D9: Huffman silent truncation on corrupt data

**Problem:** Both Python (`huffman.py:89`) and TS (`huffman.ts:240`)
silently truncate on a null/None node during decode. Corrupted Huffman
data produces a partial string with no error.

**Fix:**
- Log a warning when truncation occurs (don't throw — partial decode
  may be acceptable for diagnostic purposes)
- Python: add `log.warning` in `decode_string` when `node is None`
- TS: add `console.warn` in `decodeString` when `!node`

### D10: Minor fixes

**10a:** `master_client.py:83` — add length check before
`int.from_bytes(data[1:5])`:
`if len(data) < 5: log.warning(...); return`

**10b:** `raknet_connection.py:209` — log warning when player assignment
payload is too short for player_index (< 13 bytes)

**10c:** `view-id.ts:33` — add bounds check in `encodeViewId16`: scene
id must be 0-4095, allocated id must be 0-255

**10d:** `raknet_connection.py:386` — change `errors='replace'` to
`errors='ignore'` for password decode (replace inserts `?` which could
cause false matches)

## Non-Goals

- Rewriting the split packet assembler for robustness against adversarial
  fragments (low priority, would need full fuzzing)
- Adding rate limiting or DoS protection to master server
- Removing the duplicate `BitReader` in `unity_rpc_decode.py` (dev tool)
- Adding `pos` setter validation (would break internal code that seeks
  past current position for writes)

## Test Plan

- D1: TS tests for BitStream read-past-end (match Python's existing tests)
- D2: Tests that verify handler errors propagate (mock handler that throws)
- D3: Python test encoding `int=0`, `float=0.0`, `string=''`, `bytes=b''`
  — verify they encode as the correct zero/empty values, not as missing
- D4: No new tests (existing truncated-packet tests will now hit the
  bounds check instead of reading garbage)
- D5: Python test decoding RPC with RPCMode value 4 — verify it doesn't
  crash and produces a sensible result
- D6: TS test for cellIdx out of range in decodeQueryReply
- D7: TS test for decodeViewIdBits producing correct value for 48-bit IDs
- D10c: TS test for ViewID out-of-bounds encoding

## Implementation Order

D1 → D2 → D3 → D5 → D6 → D7 → D4 → D8 → D9 → D10
