# Protocol Fixes from Distance Client Integration Testing

**Date:** 2026-06-27
**Source:** Live testing with Distance game client (Unity 5.5.6f1)
**TS commit:** `23fa153`

## Summary

Seven protocol corrections discovered during integration testing of the
TypeScript server implementation against a real Distance game client.
All fixes have been applied to both TypeScript and Python implementations
and verified with cross-language conformance tests.

## Fix 1: USER_RPC_CONSTANT = 0x2000 (was 0x0002)

The 16-bit constant that distinguishes user RPCs from internal RPCs was
byte-swapped in the original reverse engineering analysis. The correct
big-endian value is `0x2000`. Internal RPCs retain `0x0000`.

**Wire position:** Subsequent-use: bits 120-135. First-use: 36 bits into
the metadata block after method hash.

## Fix 2: RPC Counter is 16-bit (was 8-bit)

The invocation counter field is two bytes, not one. Encoding:
`counter16 = (rpc_counter * 2) & 0xFFFF`, written as two `writeU8` calls
(high byte, low byte). Decoding: `((high << 8) | low) >> 1`.

This changes the wrap-around from 128 to 32768.

**Wire position:** Bytes 7-8 of the RPC message (after msg_id + 48-bit ViewID).

## Fix 3: Subsequent Remaining = total_bits - 120 (was - 121)

Off-by-one in the remaining-bit-count field for subsequent-use RPCs.
The field starts at bit 104 (16-bit value) and describes how many bits
follow after bit 120, not 121.

## Fix 4: First-use Remaining = param_bits + 20 + target_bits (was + 19)

Off-by-one in the remaining-bit-count for first-use RPCs. The metadata
block's remaining count covers: 4 bits (mode) + 16 bits (constant) +
param_bits + target_bits = param_bits + 20 + target_bits.

## Fix 5: METHOD_TAG_MAP for First-use Encoding

The 4-bit `method_tag` field in first-use RPCs was hardcoded to 0.
It is actually the RPC method's ordinal position within Unity's
MonoBehaviour class hierarchy, multiplied by 4.

For the Distance game, example tags:
- Standard test RPCs: tag 0 (default)
- Game-specific RPCs: varies by class hierarchy

A registration API (`register_method_tag` / `register_method_tags`) allows
callers to set the correct tag per method name.

## Fix 6: bitLength Threading Through Transport

RPC frames are not byte-aligned — the exact bit count must be passed
through the transport layer's frame creation. The TypeScript `createFrame()`
and `queueOutgoing()` now accept an optional `bitLength` parameter.

Python's `encode_rpc_*` already returns `(bytes, total_bits)`. Callers
must pass `total_bits` when constructing transport frames.

## Fix 7: Legacy Disconnect 0x13

Unity 5.5 sends message ID `0x13` for disconnect notification, while
Unity 2018 uses `0x15`. Both must be handled identically.

**Python constant:** `ID_DISCONNECTION_NOTIFICATION_LEGACY = 0x13`

## Conformance

Cross-language conformance tests in `tests/test_cross_conformance.py`
verify that Python encoder output matches TypeScript byte-for-byte for:
- Subsequent-use: RPC_Int(42), RPC_Void, counter=500, Player mode
- First-use: RPC_Int(42), RPC_Void, with method_tag=8
- Decode: all golden values decode to matching fields
