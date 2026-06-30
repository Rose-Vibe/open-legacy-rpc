# Plan: targetView extraction, ViewID ownership enforcement, player index recycling

**Date:** 2026-06-29
**Source:** TS commits d5ceffa, c7bf20c, 09264e0

## What

Three features implemented in TS by the distance-server agent need to be:
1. Added to the wire format spec where applicable
2. Ported to the Python implementation
3. Covered by conformance tests

### Feature 1: targetView extraction from decoded RPCs

**TS commit:** d5ceffa

The 16-bit `user_rpc_constant` (§3.6) is already documented in the spec, but
`decode_rpc()` didn't extract it. The TS version now reads it at:
- First-use: bit offset `160 + hashExtraBits + 36` (16-bit read)
- Subsequent-use: bit offset `120` (16-bit read)

**Python status:** `decode_rpc()` in `unity_protocol.py` does NOT extract targetView.
**Spec status:** Field already documented (§3.2 calls it `user_rpc_constant` at bits 120-135 for subsequent-use). No spec change needed.

**Python work:**
- Add `result['target_view'] = bs.read_u16_be()` at the right offsets in `decode_rpc()`
- Pass `target_view` through `_handle_rpc()` → handler callback in `unity_server.py`

**Conformance work:**
- Add `targetView` to the `rpcDecode` conformance output schema
- Add `targetView` to the `rpcFirstUseDecode` conformance output schema
- Generators already encode with a known `target_view`; validators just need to check the decoded value

### Feature 2: ViewID ownership enforcement

**TS commit:** c7bf20c

Server drops incoming RPCs whose `targetView` is an allocated view not in the
sender's ViewID block. Prevents re-broadcast loops.

**Python status:** Not implemented.
**Spec status:** Not documented — this is server behavior, not wire format. Add to §7.4.

**Python work:**
- Add `enforce_viewid_ownership` option to `UnityServer.__init__()` (default True)
- In `_handle_rpc()`, decode targetView, check if it's allocated and outside sender's block
- Add `on_viewid_violation` callback option

**Conformance work:** This is server behavior, not serde. No conformance test needed —
it's better tested as a Python unit test in `test_python_integration.py`.

### Feature 3: Player index recycling

**TS commit:** 09264e0

Disconnected player indices go into a free list; new connections draw from it first.

**Python status:** Not implemented — `_next_player_index` only increments.
**Spec status:** §7.4 says server "Frees all allocated ViewIDs on player disconnect"
but doesn't mention index recycling. Add a note.

**Python work:**
- Add `_free_player_indices = []` to `RakNetServer.__init__()`
- In `_handle_player_ready()`, pop from free list before incrementing
- In disconnect handler, push player index to free list

**Conformance work:** Connection-level behavior, not serde. Unit test in `test_python_integration.py`.

## Exit criteria

1. Python `decode_rpc()` returns `target_view` for both first-use and subsequent-use
2. Python `UnityServer` enforces ViewID ownership (with opt-out)
3. Python `RakNetServer` recycles player indices
4. Conformance rpcDecode/rpcFirstUseDecode validators check `targetView`
5. Wire format spec §7.4 updated with ownership enforcement and index recycling
6. All tests pass
