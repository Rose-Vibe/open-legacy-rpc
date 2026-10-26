# Plan: Subsequent-Use RPC Support via Batch Index Protocol

## Goal

Implement the msg_id 0x07 (RPC Batch Index) protocol so that both TS and
Python implementations can send and receive subsequent-use RPCs. Currently
both always use first-use encoding (~20 extra bytes per RPC).

## Design (from user)

Two-sided index management, fully automatic — consumer does no tracking:

1. **Peer indices (for encoding outgoing RPCs):** Per-peer map of
   `methodName → peerIndex`. When a peer sends us a BATCH 0x07, we store
   their registered index. When sending subsequent-use to that peer, we
   use their registered index instead of first-use.

2. **Our indices (for decoding incoming RPCs):** Global map of
   `methodName → ourIndex`, assigned sequentially starting at 1. When we
   receive first-use for a new method, we assign the next index and send
   BATCH 0x07 back. When the peer sends subsequent-use using our index,
   we decode it via our reverse map.

## Wire Format (0x07 Batch Index)

```
byte 0:    0x07 (msg_id)
bytes 1-4: method_id_bit_count / 2 (uint32 BE)
bytes 5+:  BitStream [flag:1=0][method_id:N][method_index:7][pad]
```

Sent with UNRELIABLE reliability.

## Changes

### rpc.ts

- Add `MSG_ID_BATCH_INDEX = 0x07` export
- Add `encodeBatchIndex(methodName, methodIndex)` — encodes a 0x07 message
- Add `decodeBatchIndex(payload)` — decodes a 0x07 message, returns
  `{ methodName, methodIndex }` or null
- Add `methodIndex` optional field to `RpcEncodeOptions` — when set,
  `encodeRpcSubsequent` uses this instead of the global METHOD_INDEX_MAP
- Keep existing `learnMethodIndex` as fallback for peers that don't BATCH

### server.ts

- Add `ourIndices: Map<string, number>` — method → our assigned index
- Add `ourIndexReverse: Map<number, string>` — our index → method (decode)
- Add `nextOurIndex = 1` — counter for sequential assignment
- Add `peerIndices: Map<string, Map<string, number>>` — session → method → peer's index
- `handleMessage`: route msg_id 0x07 to new `handleBatchIndex(session, msg)`
- `handleBatchIndex`: decode BATCH, store in `peerIndices[session.id]`
- `handleRpc` (first-use path): assign our index if new, send BATCH back,
  also add to global INDEX_TO_METHOD for decode
- `sendRpcTo`: if `peerIndices[session.id]` has the method, use subsequent-use
  with that index; else use first-use
- Remove `rpcSentMethods` — replaced by checking peerIndices
- Keep `rpcReceivedFirstUse` + `learnMethodIndex` as fallback for
  subsequent-use from peers that don't send BATCH (Unity with no BATCH response)
- On connect/disconnect: init/clean per-peer state

### client.ts

- Same pattern as server, but single peer (server connection)
- `serverIndices: Map<string, number>` — server's registered indices
- `ourIndices` / `ourIndexReverse` / `nextOurIndex` — same as server
- `handleMessage`: route 0x07 to `handleBatchIndex`
- `handleRpc` (first-use): assign our index, send BATCH back
- `sendRpc`: use server's registered index if available

### unity_protocol.py

- Add `encode_batch_index(method_name, method_index)` → (bytes, bit_length)
- Add `decode_batch_index(payload)` → dict with method_name, method_index

### unity_server.py

- Same structural changes as TS server
- `_our_indices`, `_our_index_reverse`, `_next_our_index`
- `_peer_indices` — addr → {method → index}
- Handle 0x07 in poll loop
- Send BATCH on first-use receive
- Use peer index for subsequent-use send

### unity_client.py (if it exists with RPC handling)

- Same pattern

## Exit Criteria

1. TS server sends BATCH after receiving first-use from Unity
2. TS server uses peer's BATCH index for subsequent-use encoding
3. TS server decodes subsequent-use using our assigned index
4. Python server same as above
5. Existing tests pass (backward compat — always-first-use still works)
6. New unit tests for BATCH encode/decode
