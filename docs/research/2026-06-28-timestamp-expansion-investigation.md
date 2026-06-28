# Time Sync Issue: `info.timestamp` Expansion in Unity 0x1b Messages

## The Problem

When our TS server sends RPCs (0x1b messages) to the Distance game client, Unity's native code reconstructs a full timestamp from the 16-bit `rpcCounter` field (bytes 7-8 of the 0x1b message). The resulting `info.timestamp` is wildly wrong (~983 seconds off), which breaks `localToServerNetworkTime_` and prevents the game from functioning (camera stuck, car invisible, ModeTime hugely negative).

## What We Proved

### The Formula

Through controlled experiments (setting rpcCounter=0, toggling clockDiff), we proved:

```
info.timestamp_ms = MYSTERY_CLOCK + rpcCounter - clockDiff
```

Where:
- `rpcCounter` = bytes 7-8 of the 0x1b message (our `uptimeMs & 0xFFFF`)
- `clockDiff` = RakNet's clock differential from ping/pong (`sendPongTime - (timeMS/2 + sendPingTime/2)`)
- `MYSTERY_CLOCK` ≈ 983040 ms (= 15 × 65536 = 0xF0000) — a system-level constant that persists across game restarts but is NOT process uptime, NOT system uptime, NOT Unix time

### Test Results

| Test | clockDiff | rpcCounter | info.timestamp (ms) | Computed base |
|------|-----------|------------|---------------------|---------------|
| 1 (echo, normal rpc) | ~0 | 50330 | 1033370 | 983040 |
| 2 (echo, rpc=0) | ~0 | 0 | 983066 | 983066 ≈ 983040 |
| 3 (proper clockDiff) | ~13645 | 44941 | 1014336 | 969395 = 983040-13645 |

All three tests confirm: `base = MYSTERY_CLOCK - clockDiff`, and `info.timestamp_ms = base + rpcCounter`.

### Why the Bridge Works

The bridge is a Unity server. Its rpcCounter = `bridge_RakNetGetTime() & 0xFFFF`. The client's MYSTERY_CLOCK happens to equal `bridge_RakNetGetTime() & 0xFFFF0000` because they share the same time epoch (both are Unity processes on the same system). So the expansion perfectly reconstructs the bridge's full timestamp, and `info.timestamp ≈ serverNetworkTime`.

### Why Our Server Fails

Our TS server's rpcCounter is based on our process uptime (completely different epoch from Unity's internal clock). The client expands it using MYSTERY_CLOCK, producing a value ~983 seconds too large.

## What We Don't Know

**What IS MYSTERY_CLOCK?** It's ~983040 ms on this system. It persists across game process restarts. It's NOT:
- Client process uptime (was ~23 seconds)
- System uptime (was ~20076 seconds)
- Unix timestamp (wrapped to u32)
- Client's `Network.time` (was ~23 seconds)
- Client's `realtimeSinceStartup` (was ~23 seconds)
- Server datagram header timestamp
- Any value from the RakNet ping/pong exchange

It IS affected by clockDiff (subtracted from the expansion base). The 16-bit expansion likely happens in Unity's native C++ networking code when dispatching 0x1b RPCs to C# handlers.

## Investigation Requests

1. **Find the expansion code**: The 16-bit → full timestamp expansion must be in Unity's native networking layer. Can you find it in the Unity 5.5.6f1 native libraries or through reverse engineering? The code would read a u16 from the 0x1b message and expand it to a full timestamp for `NetworkMessageInfo.m_TimeStamp`.

2. **Identify MYSTERY_CLOCK**: What time source does Unity's native code use for the expansion base? It's a ~983-second value that persists across game restarts on this system. Could it be related to the Steam runtime, the pressure-vessel container, or a shared memory clock?

3. **Can ID_TIMESTAMP (0x28) help?**: RakNet's `Receive()` calls `ShiftIncomingTimestamp()` for any packet starting with 0x28. If we prepend `[0x28, u64_timestamp]` before our 0x1b data, does Unity's native code use the shifted timestamp for `info.timestamp` instead of expanding the rpcCounter? This would bypass the expansion entirely.

4. **Can we control Network.time?**: Unity's `Network.time` on the client stays at local process uptime — it's not adjusted by clockDiff. Is there a specific message or mechanism Unity servers use to sync `Network.time`? The bridge (native Unity server) somehow syncs it.

---

## Changes Made to the Library

### 1. `ts/src/raknet/connection.ts` — Fixed ping/pong timestamp format

**handlePing (server-side)**: The original code was broken — it wrote the ping echo as a u32 at offset 1 and the server timestamp as a u32 at offset 5, which clobbered each other and left the actual server timestamp field (bytes 9-16) as zeros. The client never received valid clock differential data.

**Before (broken):**
```typescript
private handlePing(session: ClientSession, payload: Uint8Array): void {
    if (payload.length < 5) return;
    const pingTime = readU32BE(payload, 1);
    const pong = new Uint8Array(17);
    pong[0] = 0x03;
    writeU32BE(pong, 1, pingTime);      // bytes 1-4 only (should be 1-8)
    writeU32BE(pong, 5, session.reliability.getTimestamp());  // overwrites bytes 5-8 (wrong field!)
    session.reliability.queueOutgoing(pong, Reliability.UNRELIABLE);
}
```

**After (fixed):**
```typescript
private handlePing(session: ClientSession, payload: Uint8Array): void {
    if (payload.length < 9) return;
    const pong = new Uint8Array(17);
    pong[0] = 0x03;
    pong.set(payload.subarray(1, 9), 1);  // echo full u64 ping timestamp at bytes 1-8
    writeU32BE(pong, 13, session.reliability.getTimestampMs());  // server timestamp at bytes 13-16 (u64 BE, high 32=0)
    session.reliability.queueOutgoing(pong, Reliability.UNRELIABLE);
}
```

**Why**: RakNet pong format is `[0x03, echo_u64(8 bytes), serverTs_u64(8 bytes)]` = 17 bytes total. The client reads bytes 1-8 as `sendPingTime` (u64 BE) and bytes 9-16 as `sendPongTime` (u64 BE). The original code only wrote 4 bytes for each, overlapping them, so the client always computed bogus values that got rejected by the ping guard (`ping < 1200`). Also changed from `getTimestamp()` (microseconds) to `getTimestampMs()` (milliseconds) since RakNet ping/pong timestamps are in milliseconds.

### 2. `ts/src/raknet/connection.ts` — Added server-initiated pings

Added a ping counter in `tick()` that sends pings to connected clients every 15 ticks. This was already in the diff — just noting it's part of the ping/pong infrastructure.

### 3. `ts/src/raknet/connection.ts` — Epoch propagation

Added `epochNs` option to `RakNetServer` constructor, propagated to `ReliabilityLayer` instances. This ensures all timestamp calculations (datagram headers, ping timestamps) use the same epoch as the `UnityServer`/`DistanceServer`.

### 4. `ts/src/raknet/connection.ts` — handlePing for RakNetClient

Also fixed the client-side `handlePing` to use the same correct format (full u64 echo + `getTimestampMs()`).

### 5. `ts/src/unity/server.ts` — epochNs support

Added `epochNs` option to `UnityServerOptions` and propagated it to `RakNetServer`. The `sendRpcTo` method uses this epoch for computing `uptimeMs` (and thus `rpcCounter`).

### 6. `ts/src/unity/server.ts` — rpcCounter

The `rpcCounter` is `uptimeMs & 0xFFFF` where `uptimeMs = (process.hrtime.bigint() - epochNs) / 1_000_000n`. This was temporarily set to 0 for testing and has been reverted to normal.

---

## Current Workaround

We have a client-side Harmony patch that bypasses `info.timestamp` entirely and sets `localToServerNetworkTime_ = serverNetworkTime - Network.time` directly. This works but is a client mod workaround — ideally the server should produce correct timestamps without needing client patches.
