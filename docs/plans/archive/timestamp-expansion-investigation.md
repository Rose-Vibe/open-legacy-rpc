# Timestamp Expansion Investigation

## Goal

Determine exactly how Unity expands the 16-bit `rpcCounter` field in 0x1b
messages into the full `NetworkMessageInfo.timestamp` value, identify the
clock source ("MYSTERY_CLOCK"), and find a way for our non-Unity server to
produce correct timestamps.

## Background

distance-server proved the formula:
```
info.timestamp_ms = MYSTERY_CLOCK + rpcCounter - clockDiff
```
Where MYSTERY_CLOCK ≈ 983040ms (0xF0000) on their system. It persists across
game restarts and doesn't match any obvious clock (process uptime, system
uptime, Unix time, Network.time).

RakNet 3.731 source shows:
- On Linux, `GetTimeMS()` = `(gettimeofday() - initialTime) / 1000` where
  `initialTime` is captured on first call — essentially process uptime
- `ShiftIncomingTimestamp()` only fires for `ID_TIMESTAMP` (0x28) packets,
  NOT for 0x1b RPCs — so Unity's own code does the 16→32 expansion

## Hypothesis

The most likely expansion algorithm is:
```
fullTimestamp = (clientRakNetGetTime() & 0xFFFF0000) | rpcCounter16
```
Then `info.timestamp = fullTimestamp - clockDiff`.

This is the standard way to reconstruct a 16-bit truncated counter. If the
client's `RakNetGetTime()` was ~983000–1048575 ms when it received the RPC,
then `& 0xFFFF0000` = 0xF0000 = 983040. That matches MYSTERY_CLOCK exactly.

But distance-server reported client process uptime was only ~23 seconds, so
either:
1. Unity's embedded RakNet uses a different clock (not gettimeofday-subtracted)
2. `initialTime` gets set long before the game process starts (container/runtime)
3. Unity uses `clock_gettime(CLOCK_MONOTONIC)` or similar instead

## Experiments

### Experiment 1: Unity-to-Unity Baseline

**Purpose:** Establish what correct timestamp behavior looks like.

- Unity server → Unity client, both log everything
- Server sends RPCs with varying timing
- Client logs for each received RPC:
  - `info.timestamp` (the value we're investigating)
  - `Network.time`
  - `Time.realtimeSinceStartup`
  - `System.Environment.TickCount` (ms since system boot, wrapping)
  - `System.Diagnostics.Stopwatch.GetTimestamp()` / `Frequency`

**Expected:** `info.timestamp ≈ Network.time` or `info.timestamp ≈ server_Network.time`
adjusted by clock differential.

### Experiment 2: Python-to-Unity with Controlled rpcCounter

**Purpose:** Isolate MYSTERY_CLOCK and verify the expansion formula.

- Python server → Unity client
- Send RPCs with known rpcCounter values: 0, 1000, 32768, 65535
- Client logs same comprehensive clock data as Experiment 1
- From rpcCounter=0: `info.timestamp ≈ MYSTERY_CLOCK - clockDiff`
- From varying values: verify linearity

**Expected:** MYSTERY_CLOCK = `info.timestamp(rpcCounter=0) + clockDiff`.
Cross-reference with all logged clocks to identify the source.

### Experiment 3: Time Progression

**Purpose:** Determine if MYSTERY_CLOCK tracks a running clock.

- Connect Python server → Unity client
- Send rpcCounter=0 at t=0, t=5s, t=10s, t=15s
- If MYSTERY_CLOCK increases between RPCs, it's a live clock reading
- If constant, it's captured once at connection time

### Experiment 4: Multiple Restarts

**Purpose:** Verify "persists across restarts" claim and correlate with clocks.

- Run the experiment, note MYSTERY_CLOCK and all system clocks
- Kill and restart the Unity client (keep system running)
- Run again, compare MYSTERY_CLOCK delta with wall-clock delta
- If delta matches wall-clock: it's a system-level monotonic clock
- If delta matches zero: it's a constant set per-boot or per-container

## Implementation

### C# Experiment: `TimestampExpansionExperiment.cs`

One experiment file handles all roles:
- As **server**: sends RPCs at controlled intervals, logs own Network.time
- As **client**: logs comprehensive clock data for every received RPC

### Python Server: `scripts/timestamp-expansion-server.py`

Sends RPCs with precisely controlled rpcCounter values (0, 1000, 32768, 65535)
in sequence, with 2-second gaps between them.

### Run Script: `scripts/run-timestamp-expansion.sh`

Two modes:
1. `--unity-server`: runs both Unity server + Unity client (Experiment 1)
2. `--python-server`: runs Python server + Unity client (Experiments 2-4)

## Exit Criteria

- [x] Identified the clock source for MYSTERY_CLOCK (likely `clientRakNetGetTimeMS() & 0xFFFF0000`)
- [x] Confirmed the `(currentTime & 0xFFFF0000) | rpc16` hypothesis for fresh processes
- [ ] Determined whether MYSTERY_CLOCK is live or captured-once (Phase 2 confounded by clockDiff drift)
- [x] Documented findings in `docs/research/2026-06-28-timestamp-expansion-findings.md`
- [x] Found ×2 bug in Python encoder/decoder
- [x] Identified that simple server-uptime rpcCounter fix is insufficient for long-running servers
- [ ] Verify MYSTERY_CLOCK with >65s client uptime before connect
- [ ] Test ID_TIMESTAMP (0x28) prepend approach
- [ ] Fix ×2 bug in Python encoder/decoder
