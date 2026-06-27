# M13 Section 7: RPC Parameter Decoding

## Goal

Complete `decodeRpc` so it decodes parameters from the wire format,
matching the Python reference. Then wire decoded params through
UnityServer and UnityClient handlers so application code receives
actual values.

## Background

`decodeRpc` currently decodes headers only (method name, counter, mode,
first-use flag). The Python `decode_rpc` (unity_protocol.py:336) also
decodes parameters by looking up the method signature in
`METHOD_SIGNATURES` and reading typed values from the bitstream.

The encoder (`encodeParams` in rpc.ts:263) already handles all 8 types.
The decoder is the mirror image.

## Changes

### 1. Add `decodeParams` to `rpc.ts`

After reading the mode (and the Player target bit if mode=Player),
look up the method in `METHOD_SIGNATURES`. If found, decode each
parameter according to its type:

| Type | Read operation |
|------|---------------|
| int | `bs.readI32BE()` |
| float | `bs.readFloatBE()` |
| string | `readCompressedU32` for bit count, then Huffman decode |
| Vector3 | 3× `readFloatBE` → `[x, y, z]` |
| Quaternion | 4× `readFloatBE` → `[x, y, z, w]` |
| bytes | `readU32BE` for length, then `readBytes` |
| NetworkViewID | `readBits(16)` |
| NetworkPlayer | `readI32BE()` |

String decoding reuses the existing `decodeString` from huffman.ts
(returns `Uint8Array`, convert via `TextDecoder`).

### 2. Update `DecodedRpc` interface

Add `params: unknown[]` and `viewId: number` fields to `DecodedRpc`.
The viewId is already read (48 bits after msg_id) but currently
discarded — capture it.

### 3. Wire params through UnityServer and UnityClient

- `server.ts` `handleRpc`: change `handler(session)` →
  `handler(session, ...decoded.params)`
- `client.ts` `handleRpc`: change `handler()` →
  `handler(...decoded.params)`

### 4. Add conformance test handlers

Add `rpcFullDecode` handler to `conformance-runner.ts` that decodes
a complete RPC (headers + params) and returns all fields. Wire it
into the existing `rpcDecode` and `rpcFirstUseDecode` categories if
the validator checks params, or add new categories.

### 5. Tests

- Round-trip test for each param type: encode with `encodeRpcSubsequent`,
  decode, verify params match
- String param round-trip (Huffman encode/decode)
- Multi-param round-trip (RPC_IntFloatString)
- First-use param decoding
- bytes param with non-trivial data
- NetworkViewID and NetworkPlayer params
- Update existing server/client tests to verify decoded param values

## Exit Criteria

- [ ] `decodeRpc` returns `params: unknown[]` with correct values
- [ ] `decodeRpc` returns `viewId: number`
- [ ] All 8 param types decode correctly
- [ ] Player mode skips 1-bit target before params
- [ ] Unknown methods return empty params (no crash)
- [ ] Server RPC handler receives decoded params
- [ ] Client RPC handler receives decoded params
- [ ] Existing conformance tests still pass
- [ ] New round-trip unit tests for all param types
- [ ] `pnpm typecheck` and `pnpm lint` pass

## Risks

- **String decoding**: The Huffman decode path (`readCompressedU32` →
  bit string → `decodeString`) must match the Python exactly. The
  serialization module already has a working string round-trip, so
  the primitives are proven.
- **Bit alignment**: After the mode field (and optional Player target
  bit), params start at a specific bit position. The encoder calculates
  this correctly; the decoder must land at the same position. Conformance
  tests will catch misalignment.
