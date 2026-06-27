# M17: Protocol Hardening & Edge Case Coverage

## Motivation

The protocol implementation is functionally complete and API-stable, but
audit reveals gaps in edge case handling that could cause real bugs in
production (RPC counter overflow in long sessions, crashes on malformed
input) and missing conformance coverage for IEEE 754 edge values. This
milestone hardens the implementation without changing any public API.

## Deliverables

### D1: RPC Counter Overflow Fix

**Problem:** The RPC counter byte is `(counter * 2) & 0xff`, so it wraps
at counter=128. Neither implementation tests this, and
`encodeRpcSubsequent` may produce incorrect wire bytes after 128 RPCs to
the same client.

**Fix:**
- Add unit tests that encode/decode RPCs with counter values 0, 1, 127,
  128, 255, 256 (and verify round-trip correctness)
- If the encoding is wrong at wrap, fix the counter logic in both
  Python (`unity_protocol.py`) and TS (`rpc.ts`)
- Add a cross-language conformance test for counter overflow

**Note:** The counter space may be intentionally limited to 128 values
(single byte, `*2`). The "fix" may be to verify wrapping works
correctly and document the 128-value cycle, not try to extend it.

**Exit criteria:** RPC counter values 0–500 encode/decode correctly in
both implementations and cross-language. Counter wrapping behavior is
documented.

### D2: Float Edge Value Conformance

**Problem:** NaN, Infinity, -Infinity, -0.0, and denormalized floats are
valid IEEE 754 values that could appear in RPCs, state sync, or Vector3/
Quaternion fields. Neither implementation tests these, and Python/TS
could handle them differently (e.g., NaN !== NaN comparison, -0.0
serialization).

**Fix:**
- Add serde conformance tests for float edge values in:
  - `bitstream_write`/`bitstream_read` categories
  - `rpcEncode`/`rpcDecode` with float params
  - `stateSync`/`stateSyncDecode` with float fields
- Verify both implementations produce identical bytes for each value
- Fix any divergences found

**Exit criteria:** NaN, +Infinity, -Infinity, -0.0, and at least one
denormalized float all round-trip correctly in both implementations and
produce identical wire bytes cross-language.

### D3: Malformed Packet Resilience

**Problem:** The TS server silently drops malformed RPCs (try/catch) but
the Python BitStream has no bounds checking — `read_bit()` throws
`IndexError` on truncated data, crashing the server.

**Fix (Python):**
- Add bounds checking to `BitStream.read_bit()` and other read methods
  — raise a descriptive `BitStreamError` (or return a sentinel) when
  reading past the end
- Wrap RPC/state-sync decode in try/except at the server level (already
  done in TS)
- Add bounds check to `master_serialization.py` decode functions —
  replace `assert` on msg_id with validation that returns/raises cleanly

**Fix (TS):**
- Verify that truncated packets are handled gracefully (the try/catch
  exists, just add tests proving it works)

**Tests:**
- Unit tests feeding truncated/corrupt payloads to decode functions
- Verify server doesn't crash on malformed input

**Exit criteria:** Both implementations handle truncated RPC, truncated
state sync, wrong msg_id, and zero-length payloads without crashing.
Error is logged or silently dropped, not propagated.

### D4: Encoding Edge Case Tests

**Problem:** Several encoding boundary conditions lack test coverage.

**Tests to add:**

1. **Zero-component vectors:** Vector3 `(0,0,0)`, Quaternion `(0,0,0,0)`
   — serde conformance tests
2. **ViewID boundary values:** scene ID 0, max scene ID (16383),
   allocated ID at boundary (`0x4000`), max allocated — serde tests
3. **Empty and large strings:** empty string (already tested), 1KB
   string, string with all printable ASCII — serde conformance
4. **Empty and large byte arrays:** 0 bytes, 1 byte, 10KB — serde
   conformance
5. **Delta state sync when clean:** all fields unchanged after first
   sync — unit test verifying null/empty output
6. **Duplicate `defineRpc` registration:** calling `defineRpc` twice
   with same name — unit test verifying second call overwrites cleanly
7. **Int32 boundary values:** MIN_INT (-2147483648), MAX_INT
   (2147483647) in RPC params — serde conformance
8. **Unknown method hash:** decode an RPC with a method hash not in the
   registry — verify graceful handling (returns 'unknown', no crash)

**Exit criteria:** All listed edge cases have passing tests in both
implementations.

### D5: Spec Status Update

**What:** Update `docs/research/spec-status.md` to mark Master Server as
resolved (currently says "out of scope" but M15 implemented it fully).

**Exit criteria:** spec-status.md accurately reflects current state.

## Non-Goals

- API changes to UnityServer/UnityClient/defineRpc
- Stress testing (max clients, rapid reconnects) — useful but not
  protocol-correctness issues
- Split packet timeout / memory leak — low priority
- Packet loss simulation — would need network simulation infrastructure

## Implementation Order

1. D5 (spec update) — trivial, do first
2. D1 (counter overflow) — highest real-bug risk
3. D2 (float edge values) — cross-language divergence risk
4. D3 (malformed packets) — crash prevention
5. D4 (encoding edge cases) — coverage breadth

D1–D4 are independent and could be done in any order.

## Test Plan

- D1: Unit tests + conformance tests for counter 0–500
- D2: Conformance tests for NaN/Inf/-0/denorm across bitstream, RPC, state sync
- D3: Unit tests with truncated/corrupt payloads for both languages
- D4: Conformance + unit tests for each listed edge case
- D5: Manual verification of spec-status.md accuracy
