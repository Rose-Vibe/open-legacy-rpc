# Wire Format Finding: Bytes 1-8 Are a u64 Timestamp

## Fundamental Finding: Our Wire Format Is Wrong

I proved this from pcap evidence. Two experiments using the **same** `ctx.PrimaryNetworkView` (viewId=0), different server uptimes:

```
RpcInt (server up 591ms):    bytes 1-8 = 00 00 00 00 00 00 02 4f  (u64 = 591)
Staggered (server up 92957ms): bytes 1-8 = 00 00 00 00 00 01 6b 1d  (u64 = 92957)
```

Byte 6 changes from `0x00` to `0x01` despite using the same viewId=0. It's not a viewId — it's the timestamp overflowing past 65535. **Bytes 1-8 are a u64 `senderRakNetGetTimeMS()`, not viewId(6)+counter(2).**

RakNet confirms this: `ReceiveIgnoreRPC()` calls `ShiftIncomingTimestamp(data+1)` on any packet where `data[0] == 0x1B (ID_TIMESTAMP)`, reading bytes 1-8 as a u64 and subtracting `clockDiff`.

The actual wire format is:

```
byte 0:     0x1B (ID_TIMESTAMP / msg_id)
bytes 1-8:  u64 BE senderRakNetGetTimeMS()
byte 9:     sub-type (0x0B = RPC, 0x80 = first state sync, 0x7F = subsequent state sync)
bytes 10+:  sub-type-specific data (viewId, method, params, etc.)
```

## Question 1: Two Unity Peers (70s offset)

Server process started 70.5s before client process. Data from staggered experiment `StaggeredTimestamp-20260628-123948`. RPC 101 is the first live (non-buffered) RPC.

### Values on the wire

| What | Where | Raw bytes | Value | Derived from |
|---|---|---|---|---|
| **Ping (client→server)** | `[0x00][u64 BE]`, 9 bytes | `00 00 00 00 00 00 00 96` | 150ms | Client's `RakNetGetTimeMS()` at ping send |
| **Pong (server→client)** | `[0x03][u64 echo][u64 server]`, 17 bytes | echo: `00..96`, server: `00 00 00 00 00 01 16 D4` | echo=150, server=71380 | Server's `RakNetGetTimeMS()` at pong send |
| **RPC 101 timestamp** | bytes 1-8 of 0x1B msg, u64 BE | `00 00 00 00 00 01 17 1C` | 71452 | Server's `RakNetGetTimeMS()` at send |
| **RPC 101 sub-type** | byte 9 | `0x0B` | "this is an RPC" | Constant for RPC messages |
| **RPC data** | bits 80+ | `6c 00 00 00 33 00 02 ...` | method_index, target_view=0x0002, mode, params | Bit-packed RPC fields |

### Values available locally

| What | Where | Value | Derived from |
|---|---|---|---|
| **Server `RakNetGetTimeMS()`** | Server process, at RPC 101 send | ~71452 ms | `gettimeofday() - initialTime` (process uptime) |
| **Server `Time.realtimeSinceStartup`** | Server process | 71.452 s | Unity engine clock (process uptime) |
| **Server `Network.time`** | Server process | 71.472 s | ≈ `RakNetGetTimeMS() / 1000` + ~20ms init offset |
| **Client `RakNetGetTimeMS()`** | Client process, at RPC 101 receipt | ~965 ms | `gettimeofday() - initialTime` (process uptime) |
| **Client `Time.realtimeSinceStartup`** | Client process | 0.965 s | Unity engine clock (process uptime) |
| **Client `Network.time`** | Client process | 0.977 s | ≈ `RakNetGetTimeMS() / 1000` + ~12ms init offset |
| **Client `clockDiff`** | Computed from pong | ~70487 | `serverPongTime - (clientNow/2 + clientPingTime/2)` ≈ serverRakNetTime − clientRakNetTime |
| **`ShiftIncomingTimestamp` result** | RakNet modifies bytes 1-8 in place | 71452 − 70487 = **965** | `wireU64 − clockDiff` |
| **Client `info.timestamp`** | Delivered to game code | **0.965 s** | `shiftedU64 / 1000.0` |
| **`Network.time − info.timestamp`** | Available to game code | 0.977 − 0.965 = **0.012 s** | Represents network delay (half-RTT + clockDiff error) |

**Summary**: `info.timestamp` tracks the client's `RakNetGetTimeMS() / 1000`, which ≈ `Network.time`. The 12ms gap is clockDiff estimation error. All timing is correct.

## Question 2: Unity Client + Our TS Server

### What our encoder currently sends

```typescript
// server.ts line 236-237
const uptimeMs = Number((process.hrtime.bigint() - this.epochNs) / 1_000_000n);
const rpcTimestamp = uptimeMs & 0xffff;  // ← TRUNCATION TO 16 BITS

// rpc.ts line 195-200
bs.writeU8(MSG_ID_RPC);                     // byte 0: 0x1B
bs.writeBytes(encodeViewId(opts.viewId));    // bytes 1-6: viewId as 48-bit BE
bs.writeU8((counter16 >> 8) & 0xff);        // byte 7: counter high
bs.writeU8(counter16 & 0xff);               // byte 8: counter low
bs.writeU8(0x0b);                           // byte 9: marker
```

Versus what Unity writes:
```
byte 0:     0x1B
bytes 1-8:  u64 BE senderRakNetGetTimeMS()   ← FULL 64-bit timestamp
byte 9:     0x0B
bytes 10+:  RPC data
```

### Case A: Server uptime 33774ms (< 65536) — our tested scenario

| What | Where | Our value | Unity-equivalent value | Match? |
|---|---|---|---|---|
| **Wire bytes 1-8** | 0x1B msg bytes 1-8 | `00 00 00 00 00 00 83 EE` (u64=33774) | `00 00 00 00 00 00 83 EE` (u64=33774) | **YES** — viewId=0 zeros + 16-bit counter = same as u64 timestamp when < 65536 |
| **Ping time** | `[0x00][u64]` | `00 00 00 00 00 00 83 EE` (u32 at offset 5) | same | **YES** |
| **Pong server time** | bytes 9-16 of pong | `00 00 00 00 00 00 83 EE` (u32 at offset 13) | same | **YES** |
| **clockDiff** | Client computes from pong | ~32589 | ~32589 | **YES** |
| **info.timestamp** | After ShiftIncomingTimestamp | 33774 − 32589 = 1185 → **1.185s** | same | **YES** |
| **Client Network.time** | Unity client | 1.211s | 1.211s | **YES** |

Works because server uptime fits in 16 bits.

### Case B: Server uptime 74865ms (> 65536) — the Distance failure scenario

| What | Where | Our value | Unity-equivalent value | Match? |
|---|---|---|---|---|
| **Wire bytes 1-8** | 0x1B msg bytes 1-8 | `00 00 00 00 00 00 24 71` (u64=**9329**) | `00 00 00 00 00 01 24 71` (u64=**74865**) | **NO** — we lost 65536 (0x10000) |
| **Pong server time** | bytes 9-16 of pong | u64=**74865** (correct — `getTimestampMs()` uses u32, not truncated to 16) | u64=74865 | **YES** — pong is fine |
| **clockDiff** | Client computes from pong | 74865 − 941000 = **−866135** (correct) | same | **YES** — clockDiff is correct |
| **ShiftIncomingTimestamp** | RakNet on client | 9329 − (−866135) = **875464** | 74865 − (−866135) = **941000** | **NO** |
| **info.timestamp** | Delivered to game | **875.464s** | **941.000s** | **NO** — error = 65.536s = exactly 65536ms |
| **Client Network.time** | Unity client | ~941s (process uptime) | ~941s | YES |
| **Network.time − info.timestamp** | Game formula input | 941 − 875.464 = **65.5s** (WRONG) | 941 − 941 = **~0s** (correct) | **NO** |

### Case C: Server uptime 200000ms — bigger example

| What | Our value | Unity value |
|---|---|---|
| Wire u64 | 200000 & 0xFFFF = **3392** | **200000** |
| clockDiff | −741000 (correct) | −741000 |
| info.timestamp | (3392+741000)/1000 = **744.392** | (200000+741000)/1000 = **941.000** |
| Error | 941.000 − 744.392 = **196.608s** = 3 × 65.536 | — |

The error is always a multiple of 65.536 seconds (65536ms / 1000), growing by one quantum every 65.5 seconds of server uptime.

## The Bugs

1. **`server.ts:237`** — `uptimeMs & 0xffff` truncates the timestamp to 16 bits. Should pass the full value.

2. **`rpc.ts:196`** — `encodeViewId(opts.viewId)` writes 6 bytes of viewId at bytes 1-6. Should write the high 6 bytes of the u64 timestamp instead. The viewId is NOT at bytes 1-6 — it's encoded later in the RPC bitstream (at the "target view constant" position, bit 120+ for subsequent-use).

3. **`rpc.ts:197-199`** — Writes counter as 2 bytes at bytes 7-8. Should write the low 2 bytes of the u64 timestamp. (Currently `opts.rpcCounter & 0xffff`, which is already 16 bits of the timestamp — just needs the full value to be written across all 8 bytes.)

The ping/pong format (`connection.ts:297-303`) is correct — `getTimestampMs()` returns a u32 which is written into a u64 pong field with zero-padding. This gives the client a correct `clockDiff`. The mismatch is ONLY in the RPC 0x1B message where we write viewId+counter16 instead of u64 timestamp.

## Does Fixing This Fix the Distance Bug?

No. The distance-server agent reported `info.timestamp = 941.559` — which is the **correct** value (it matches `clientRakNetTime / 1000`). If our encoder were producing a 65536ms error, the value would have been ~876 instead. So either the server's uptime was < 65536ms in that test run, or something else is going on.

The actual Distance problem is that `info.timestamp` (941.559) doesn't match `Network.time` (24.1). That's a ~917 second gap. For the game formula `LTSNT = serverTime - info.timestamp` to work, `Network.time` and `info.timestamp` need to be on the same time base. In the Unity 2018.1.6f1 experiment they always are — both equal `clientRakNetTime / 1000`. But on the Distance client (Unity 5.5.6f1 under Steam pressure-vessel), they clearly aren't.

The u64 fix is a real correctness bug that will bite any server running > 65 seconds, but it's a separate issue from the 917-second gap Distance sees. That gap comes from `Network.time` and `RakNetGetTimeMS()` having different epochs on the client — something we can't control from the server side.
