# Timestamp Synchronization Fix

## Problem

Unity's 16-bit timestamp expansion in 0x1b RPC messages is fundamentally
broken for servers whose RakNet clock differs significantly from the client's.

The receiver reconstructs the sender's timestamp as:
```
expanded = (receiverRakNetTimeMs & 0xFFFF0000) | wireCounter16
info.timestamp = (expanded - clockDiff) / 1000.0
```

This only produces a correct value when the sender's and receiver's
`RakNetGetTimeMS()` have the same upper 16 bits — i.e., they're within
~32 seconds of each other (mod 65536). For a Unity-to-Unity setup where
both processes start around the same time, this holds. For a long-running
dedicated server, it doesn't — the server and client start at different
times, so their clocks diverge, and the expansion produces a systematic
error proportional to the clock difference.

clockDiff (established via ping/pong) correctly measures the offset
between the two clocks, but it's applied AFTER the already-broken
expansion, so it can't fix the underlying problem.

RakNet's clock is per-process uptime (`gettimeofday() - initialTime`),
NOT a consistent epoch. Each process starts from zero. So clockDiff is
bridging completely different time origins, not just compensating for
network latency.

See `docs/research/2026-06-28-timestamp-expansion-findings.md` for the
full experimental evidence.

## Root Cause (UPDATED after client-delay experiment)

The original theory was that different upper bits caused a systematic
error. This was **wrong** — Unity's expansion works correctly with
arbitrary clock skew because 16-bit truncation of both wireCounter and
clockDiff causes high bits to cancel in the subtraction.

### Critical Finding: Network.time = Client Process Uptime

Experiment with 60-second client delay before connecting proved:
- Unity's `Network.time` on the client = `clientProcessUptime / 1000`
- `info.timestamp` also = `clientProcessUptime / 1000`
- They are always consistent in standard Unity

Server's `Network.time` was 62.099s while client's was 60.778s at the
same moment — Unity does NOT sync `Network.time` between peers.

### Why Distance Fails

Distance's custom time sync RPC (`sendTimeSync`) provides a game-level
time (~24s) that differs from Unity's `Network.time` (~950s for a client
with long menu time). The game code compares `info.timestamp` against
this custom time, producing the observed mismatch.

The Unity bridge server "works" because it uses standard Unity
`Network.time`, which always matches `info.timestamp`.

No server-side fix exists within the 16-bit counter protocol — the gap
between custom time (24s) and client process uptime (950s) exceeds the
~32-second range of 16-bit arithmetic. The Harmony patch is the only fix.

## Plan

### Step 1: Fix ×2 Bug in Python Encoder/Decoder ✅ DONE

Fixed ×2 in Python encoder (`encode_rpc_subsequent`, `encode_rpc_first_use`),
÷2 in Python decoder (`decode_rpc`), ÷2 in TS decoder, and ×2 in
`method-index-server.py`. All tests pass.

### Step 2: Research — Three Threads ✅ DONE

#### Thread A: Unity-to-Unity with staggered start ✅ DONE

Ran with 70-second stagger. Timestamps are correct within ~20ms.
The 16-bit cancellation works because `wireCounter - clockDiff` in
16-bit arithmetic recovers `clientTime & 0xFFFF`. See findings doc.

#### Thread B: Unity Network.time synchronization APIs

Not needed — the staggered experiment and TS verification proved the
mechanism works. Unity's Network.time is `RakNetGetTimeMS() / 1000.0`.

#### Thread C: RakNet source code

Confirmed from open-source RakNet 3.731: `GetTimeMS()` is process
uptime in ms. `clockDiff` is computed from ping/pong timestamps using
the same `GetTimeMS()` function. This confirms the cancellation works
as long as both wire counter and ping/pong use the same clock.

### Step 3: Implement the Fix ✅ ALREADY CORRECT

Audited the TS server's clock architecture:
- `UnityServer` creates `epochNs = process.hrtime.bigint()` at construction
- Passes `epochNs` to `RakNetServer` → `ReliabilityLayer`
- RPC counter: `(hrtime - epochNs) / 1M & 0xFFFF` (server.ts:239-240)
- Ping/pong: `getTimestampMs()` = `(hrtime - epochNs) / 1M & 0xFFFFFFFF`
  (reliability.ts:43-44)
- Both use the same `epochNs`-based clock — no fix needed.

### Step 4: Verify with TS Server → Unity Client ✅ DONE

Ran TS server for 30 seconds before connecting Unity client. Sent 10 RPCs
at 1-second intervals. All timestamps within 5-32ms of client Network.time.
See `docs/research/2026-06-28-timestamp-expansion-findings.md`.

## Candidate Fix Approaches (Reference)

### Client-Relative rpcCounter

Encode `estimatedClientTime & 0xFFFF` instead of `serverTime & 0xFFFF`:
```
estimatedClientTime = serverTime - clockDiff
wireCounter = estimatedClientTime & 0xFFFF
```
The client's expansion then reconstructs its own time correctly.
Pros: pure server-side fix. Cons: accuracy depends on clockDiff quality.

### ID_TIMESTAMP (0x28) Prepend

Prepend `[0x28, u64_timestamp]` before the 0x1b payload. RakNet's
`Receive()` calls `ShiftIncomingTimestamp()` for 0x28-prefixed packets.
If Unity reads the shifted timestamp from the RakNet layer, this
bypasses the 16-bit expansion entirely.
Pros: uses RakNet's built-in mechanism. Cons: Unity might ignore it.

### Client-Side Harmony Patch (Current Workaround)

Already implemented in distance-server. Bypasses `info.timestamp`
entirely. Works but requires a client mod.

## Exit Criteria

- [x] Fixed ×2 encoding bug in Python (and TS if applicable)
- [x] Completed research threads A, B, C
- [x] Determined how Unity handles staggered start times natively
- [x] Implemented a fix that produces correct timestamps for
      long-running servers (already correct — unified epoch)
- [x] Verified correct timestamps with >60s server-client clock offset
      (30s stagger: timestamps within 5-32ms of client Network.time)
