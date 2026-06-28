# Timestamp Expansion: Findings

## Summary

The 16-bit counter at bytes 7-8 of 0x1b RPC messages is
`RakNetGetTimeMS() & 0xFFFF` — raw milliseconds since RakNet init,
truncated to 16 bits. Unity's receiver expands it using the standard
16→32 reconstruction:

```
fullTimeMs = (localRakNetTimeMs & 0xFFFF0000) | wireCounter16
info.timestamp = (fullTimeMs - clockDiff) / 1000.0
```

Where `clockDiff` is established via RakNet ping/pong.

## What RakNetGetTimeMS() Is

From the open-source RakNet 3.731 (facebookarchive/RakNet):

- **Linux**: `(gettimeofday() - initialTime) / 1000` where `initialTime`
  is captured on the very first call to `GetTimeUS()`. This is effectively
  **process uptime** in milliseconds.
- **Windows**: `QueryPerformanceCounter()` based, also process-relative.

In Unity's embedded RakNet, `initialTime` gets set during engine
initialization, so `RakNetGetTimeMS() ≈ Time.realtimeSinceStartup * 1000`.

## Experimental Proof

### Experiment 1: Unity Server → Unity Client

Server sends 15 RPCs at ~1s intervals. Both server and client are Unity
processes on the same machine (same RakNet time epoch).

| RPC# | Server Network.time | Client info.timestamp | Diff |
|------|--------------------|-----------------------|------|
| 1 | 0.890 | 0.380 | 0.016 from client Network.time |
| 2 | 1.719 | 1.209 | 0.016 |
| ... | ... | ... | 0.016 |

`info.timestamp ≈ client_Network.time - 0.016`. The constant 16ms offset
is the clockDiff. Timestamps are correct and small (process-uptime-scale).

### Experiment 2: Python Server → Unity Client (Controlled Wire Counters)

Phase 1: Fixed wire counter values sent to Unity client:

| wire_counter | info.timestamp (ms) | offset |
|-------------|---------------------|--------|
| 0 | 159 | 159 |
| 1000 | 1159 | 159 |
| 32768 | 32927 | 159 |
| 65534 | 65693 | 159 |
| 0 (repeat) | 159 | 159 |

**Linear relationship confirmed**: `timestamp_ms = wireCounter + 159`.

The 159ms offset = `-(clockDiff)` since `MYSTERY_CLOCK = 0` (client's
RakNetTime < 65536 ms because the process just started).

Phase 2: wire_counter=0 sent every 5 seconds for 80 seconds:

| Time since connect | info.timestamp (ms) | Delta from initial |
|-------------------|---------------------|-------------------|
| ~7s | 159 | 0 |
| ~12s | 10242 | +10083 |
| ~17s | 15181 | +15022 |
| ~27s | 20169 | +20010 |
| ~32s | 30263 | +30104 |
| ~37s | 35273 | +35114 |

The offset changes over time because clockDiff drifts (the Python server's
ping/pong timestamps are on a different epoch from the client's RakNet time).
This confirms the formula includes a live `clockDiff` subtraction.

### Wire Format Verification (from RpcIntExperiment pcap)

Raw bytes 7-8 of Unity-generated RPCs vs real time:

| Wire hex | Wire value | Decoded ÷2 | Pcap timestamp delta |
|----------|-----------|------------|---------------------|
| 0x024F | 591 | 295 | ~504ms process age |
| 0x0450 | 1104 | 552 | +519ms |
| 0x0652 | 1618 | 809 | +510ms |
| 0x0855 | 2133 | 1066 | +523ms |

Wire deltas (513, 514, 515) ≈ real time deltas (519, 510, 523 ms).
591 is odd — proving Unity does NOT multiply by 2 on the wire.

**The ×2 in our Python encoder is an internal convention** where the
`rpc_counter` parameter = half the wire value. The actual wire value
is raw milliseconds.

## MYSTERY_CLOCK: Likely Identified, Not Fully Proven

**Hypothesis**: `MYSTERY_CLOCK = clientRakNetGetTimeMS() & 0xFFFF0000`

This is confirmed for fresh Unity processes (MYSTERY_CLOCK = 0 when
RakNetTime < 65536ms). For distance-server's tests, MYSTERY_CLOCK ≈ 983040
= 0xF0000 — consistent with a client running for 983-1048 seconds.

**Open contradiction**: distance-server reported MYSTERY_CLOCK "persists
across game restarts." If it's `clientRakNetTime & 0xFFFF0000`, it should
reset to 0 on each restart (since `RakNetGetTimeMS()` is process-relative).
Possible explanations:
- The restarts happened quickly enough that the game reloaded into the
  same 65536ms window (same upper bits).
- Under Steam's pressure-vessel container, `gettimeofday()`'s baseline
  or a shared library may set `initialTime` at container start, not game
  process start.
- The observation was from the same session (not a true process restart).

**Open question**: `realtimeSinceStartup` was ~23s but MYSTERY_CLOCK
implies ~983s. `realtimeSinceStartup` is monotonic from process start
(NOT reset on scene loads — that's `timeSinceLevelLoad`). So either
RakNet's `initialTime` is set before Unity's process start timestamp
(e.g., in the Steam container), or the ~23s measurement was from a
different moment than the ~983s MYSTERY_CLOCK observation.

**Needs verification**: Run a client for >65 seconds before connecting
to confirm MYSTERY_CLOCK changes predictably with client uptime.

## Why the Bridge Server Works

The bridge is a Unity process on the same machine. Both client and bridge
share the same `gettimeofday()` epoch (though their `initialTime` values
differ by their start-time difference). clockDiff correctly accounts for
this offset. So:

```
expandedTime = (clientHigh | bridgeLow) ≈ bridgeFullTime ≈ clientFullTime + clockDiff
info.timestamp = expandedTime - clockDiff ≈ clientFullTime
```

The expansion correctly reconstructs the bridge's time, and after subtracting
clockDiff, produces a value close to the client's own RakNet time.

## Staggered Start Experiment (Thread A)

### Setup

Unity server started, waited 70 seconds, then Unity client connected.
Server sent 5 buffered RPCs (OthersBuffered) before client connected,
then 10 live RPCs (Others) after client connected.

### Results

Server-side clocks at send time:
- Server realtimeSinceStartup ≈ 71.4-78.9s (70s of uptime before client)
- Server Network.time ≈ 71.5-78.9

Client-side received timestamps:
```
Phase 1 (buffered):  all timestamp=0.131  Network.time=0.150
Phase 2 (live):
  RPC 101: timestamp=0.958  Network.time=0.961  (server sent at 71.465)
  RPC 102: timestamp=1.786  Network.time=1.806  (server sent at 72.293)
  RPC 103: timestamp=2.614  Network.time=2.634  (server sent at 73.121)
  ...
  RPC 110: timestamp=8.413  Network.time=8.435  (server sent at 78.919)
```

**Timestamps are correct** — within ~20ms of client `Network.time` despite
a 70-second clock skew. Unity handles staggered starts natively.

### Why It Works: 16-bit Arithmetic Cancellation

The original analysis assumed the expansion uses `(clientHigh | serverLow)`,
which fails when clientHigh ≠ serverHigh. But the math actually works
because 16-bit truncation of BOTH wireCounter and clockDiff causes the
high bits to cancel in the subtraction:

```
wireCounter = serverTime & 0xFFFF
clockDiff   = serverTime - clientTime
expanded    = (clientHigh | wireCounter)   // may not equal serverTime
timestamp   = (expanded - clockDiff) / 1000

BUT: in 16-bit arithmetic (which is effectively what happens):
  wireCounter - (clockDiff & 0xFFFF)
  = (serverTime & 0xFFFF) - ((serverTime - clientTime) & 0xFFFF)
  ≈ clientTime & 0xFFFF
```

The high bits of serverTime appear in both wireCounter and clockDiff, so
they cancel. The result is `clientTime & 0xFFFF`, which for client uptimes
under 65.5 seconds is the complete value. After that, it wraps — but the
expansion step (`clientHigh |`) handles the wrap correctly because the
client's own high bits are the right ones for its own time.

The ~20ms offset between timestamp and Network.time is the clockDiff
estimation error (half-RTT).

### Verification

For RPC 101:
- Server RakNetTime ≈ 71449ms, wireCounter = 71449 & 0xFFFF = 5913
- Client RakNetTime at receipt ≈ 958ms
- clockDiff ≈ 70491ms, clockDiff & 0xFFFF = 4955
- 16-bit result: (5913 - 4955) & 0xFFFF = 958
- timestamp = 958 / 1000 = 0.958 ✓

For RPC 102:
- wireCounter = 72293 & 0xFFFF = 6757
- 16-bit result: (6757 - 4955) = 1802
- timestamp = 1.802, actual = 1.786 (16ms clockDiff estimation error) ✓

## Why distance-server Fails

The problem is NOT the 16-bit expansion formula — that works correctly
as long as the wire counter and clockDiff are on the same clock.

distance-server's issue is one of two things:
1. **Incorrect ping/pong handling**: If the server's ping response
   timestamps are on a different epoch than the RPC counter, clockDiff
   will be wrong and the cancellation breaks.
2. **Wrong counter source**: If the server sends `sequentialCounter++`
   instead of `uptimeMs & 0xFFFF`, the counter is not on the same time
   base as the ping/pong timestamps.

The fix is straightforward: ensure the RPC wire counter and the ping/pong
timestamps use the same monotonic clock. Then the 16-bit cancellation
works automatically.

## Bug: ×2 Factor in Python Encoder/Decoder (FIXED)

The Python encoder at `encode_rpc_subsequent` / `encode_rpc_first_use`
had `counter16 = (rpc_counter * 2) & 0xFFFF` and the decoder divided by 2.
But Unity's wire value is **raw milliseconds** (verified: odd wire values
like 591 in Unity-generated traffic). The TS decoder also had `>> 1`.

Fixed: removed ×2 from Python encoder, ÷2 from both Python and TS decoders,
and ×2 from method-index-server.py. Tests updated.

## TS Server → Unity Client Verification (Step 4)

### Setup

TS server started, waited 30 seconds, then Unity client connected. Server
sent 10 RPCs at 1-second intervals using `encodeRpcFirstUse` with
`rpcCounter = uptimeMs & 0xFFFF`, where `uptimeMs` is relative to the
server's `epochNs` (same clock as ping/pong via `getTimestampMs()`).

### Results

| RPC# | Server uptimeMs | Client timestamp | Client Network.time | Error |
|------|----------------|-----------------|--------------------|----|
| 1 | 33774 | 1.185 | 1.211 | -26ms |
| 2 | 34775 | 2.186 | 2.204 | -18ms |
| 3 | 35774 | 3.185 | 3.202 | -17ms |
| 4 | 36776 | 4.187 | 4.192 | -5ms |
| 5 | 37775 | 5.165 | 5.186 | -21ms |
| 6 | 38777 | 6.167 | 6.199 | -32ms |
| 7 | 39778 | 7.168 | 7.192 | -24ms |
| 8 | 40778 | 8.168 | 8.185 | -17ms |
| 9 | 41779 | 9.169 | 9.179 | -10ms |
| 10 | 42779 | 10.165 | 10.189 | -24ms |

**All timestamps within 5-32ms of client Network.time** with a 30-second
clock skew. The 16-bit cancellation works correctly because the TS server's
RPC counter and ping/pong timestamps share the same `epochNs`-based clock.

### Conclusion

The TS implementation already produces correct timestamps. No code changes
needed beyond the ×2 bug fix. The unified epoch (`epochNs`) passed from
`UnityServer` → `RakNetServer` → `ReliabilityLayer` ensures the RPC
counter and ping/pong use the same time base.

## Remaining Questions

1. Why is `realtimeSinceStartup` (~23s) different from MYSTERY_CLOCK
   (~983s) in the Distance tests? Is it the Steam container's effect
   on RakNet's `initialTime`?
2. What exactly is wrong with distance-server's ping/pong? Is the
   epoch mismatch in their `getTimestampMs()` vs RPC counter?
3. Does MYSTERY_CLOCK truly persist across game process restarts, or was
   this an artifact of testing within the same time window?
