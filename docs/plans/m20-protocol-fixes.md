# M20: Port 7 Protocol Fixes from Distance Integration Testing

## Background

During integration testing with a real Distance client (Unity 5.5.6f1), 7 protocol
corrections were discovered and applied to the TypeScript implementation (commit
`23fa153`). These need to be ported to the Python implementation and documented.

The fixes were discovered via the distance-server project's live testing against
a real Unity 5.5 game client.

## Fixes

### Fix 1: USER_RPC_CONSTANT = 0x2000 (was 0x0002)
The 16-bit constant distinguishing user RPCs from internal RPCs was byte-swapped
in the original RE analysis. Correct value is `0x2000`.

### Fix 2: Counter is 16-bit, not 8-bit
The RPC invocation counter is written as two bytes `(rpc_counter * 2) & 0xFFFF`,
split into high and low bytes. Decoder reconstructs as
`((high << 8) | low) >> 1`. Wraps at 32768, not 128.

### Fix 3: Subsequent remaining = total_bits - 120 (was - 121)
Off-by-one in the remaining-bit-count for subsequent-use RPCs.

### Fix 4: First-use remaining = param_bits + 20 + target_bits (was + 19)
Off-by-one in the remaining-bit-count for first-use RPCs.

### Fix 5: METHOD_TAG_MAP for first-use encoding
The 4-bit `method_tag` field in first-use RPCs is the method's ordinal position
in Unity's MonoBehaviour class hierarchy, multiplied by 4. It was hardcoded to 0.
Now looked up from a registered map.

### Fix 6: bitLength threading through transport
RPC frames are not byte-aligned — the exact bit count must be passed through
`createFrame()` / `queueOutgoing()` / `sendTo()`. Python already returns
`(bytes, total_bits)` from encode functions; need to verify the transport layer
uses the bit count in frame creation.

### Fix 7: Legacy disconnect 0x13
Unity 5.5 sends `0x13` for disconnect notification (vs `0x15` in Unity 2018).
Both must be handled.

## Changes

### Python (`protocol/unity_protocol.py`)
1. `USER_RPC_CONSTANT`: `0x0002` → `0x2000`
2. `encode_rpc_subsequent`: counter from 8-bit to 16-bit (two `write_u8` calls)
3. `encode_rpc_subsequent`: remaining `total_bits - 121` → `total_bits - 120`
4. `encode_rpc_first_use`: counter from 8-bit to 16-bit
5. `encode_rpc_first_use`: remaining `param_bits + 19` → `param_bits + 20`
6. `encode_rpc_first_use`: add `METHOD_TAG_MAP` lookup instead of hardcoded 0
7. Add `METHOD_TAG_MAP`, `register_method_tag()`, `register_method_tags()`
8. `decode_rpc`: counter from 8-bit to 16-bit

### Python (`protocol/raknet_connection.py`)
9. Add `ID_DISCONNECTION_NOTIFICATION_LEGACY = 0x13`
10. Handle `0x13` the same as `0x15` in both client and server message handlers

### Tests (`tests/test_unity_protocol.py`)
11. Update `test_rpc_counter_overflow_wraps_at_128` → wraps at 32768
12. Update `test_rpc_counter_overflow_first_use` → wraps at 32768
13. Update `test_user_rpc_constant_two` → check for `0x2000`
14. Add `test_method_tag_registration` — register tags and verify in first-use output
15. Add `test_legacy_disconnect_0x13` — verify 0x13 is handled

### Conformance Tests (`tests/test_cross_conformance.py`)
16. Generate RPC bytes from Python and known-good TS output, compare byte-for-byte
17. Test all 7 fixes produce matching output across languages

## Exit Criteria
- All 7 fixes applied to Python
- All existing tests updated and passing
- New tests for method_tag, legacy disconnect, 16-bit counter range
- Cross-language conformance tests comparing Python output to TS golden values
