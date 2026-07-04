# Exception Safety

## Goal

Add exception boundaries at all points where unhandled throws can crash the
process, leak resources, or leave the system in an inconsistent state. This
hardens the library for public use where consumers may supply faulty handlers
or encounter malformed network traffic.

## Motivation

Audit found that the TypeScript implementation lacks try/catch at the boundary
between the Node.js event loop and library code. Any exception in packet
processing or user-supplied callbacks propagates through the dgram event
emitter and crashes the process. The Python side has fewer issues due to its
synchronous poll() pattern but still has two crashers.

## Fixes

### CRITICAL — Process crash prevention

#### Fix 1: Wrap socket messageHandler in try/catch

**File:** `ts/src/raknet/socket.ts`

The `messageHandler` call inside the dgram `'message'` event is unprotected.
Any throw from packet parsing or higher layers crashes the process.

- Wrap `this.messageHandler(...)` in try/catch
- On error, call `this.errorHandler` if set, otherwise `console.error`

#### Fix 2: Wrap onConnect/onDisconnect handler invocations

**File:** `ts/src/raknet/connection.ts`

User-supplied connect/disconnect handlers that throw crash the process.

- Wrap each handler call in the `connectHandlers` and `disconnectHandlers`
  iteration loops in try/catch
- Log errors with `console.error`

#### Fix 3: Wrap tick() timer body in try/catch

**File:** `ts/src/raknet/connection.ts`

The `setInterval` callback for `tick()` has no exception boundary.

- Wrap the entire tick body (both server and client) in try/catch
- Log errors with `console.error`

### HIGH — Resource leaks and hangs

#### Fix 4: Close socket on RakNetClient connect timeout

**File:** `ts/src/raknet/connection.ts`

When `connect()` times out, the UDP socket is leaked.

- In the timeout rejection path, call `this.socket.close()`
- Set state to DISCONNECTED
- Clear any pending `checkConnect` timeout

#### Fix 5: Reject pending resolvers on MasterClient close

**File:** `ts/src/master/client.ts`

When `close()` is called with requests in flight, callers hang until their
individual timeout fires.

- In `close()`, iterate `pendingResolvers`, reject each with a "closed" error,
  clear their timeouts, and empty the map

#### Fix 6: Guard Python RakNetClient.run() against None peer

**File:** `protocol/unity_client.py`

`run()` crashes with `AttributeError` if `self._raknet.peer` is None.

- Guard `self._raknet.peer.check_retransmits()` and
  `self._raknet.peer.flush_pending_acks()` with `if self._raknet.peer:`

#### Fix 7: Fix Python SplitPacketAssembler KeyError

**File:** `protocol/raknet_transport.py`

When `len(self._pending[sid]) == self._counts[sid]` is true but not all
indices 0..count-1 are present (possible via duplicate fragments at the same
index), the list comprehension raises KeyError.

- Before assembling, verify all indices are present:
  `if not all(i in self._pending[sid] for i in range(self._counts[sid])): return None`

### MEDIUM — Handler crash propagation

#### Fix 8: Wrap UnityClient RPC handler calls in try/catch

**File:** `ts/src/unity/client.ts`

User RPC handlers that throw crash the process (unlike UnityServer which
already has try/catch).

- Wrap `handler(...)` in try/catch, log with `console.error`

#### Fix 9: Guard broadcastRpc against encoding exceptions

**File:** `ts/src/unity/server.ts`

If `encodeRpcFirstUse` throws (e.g. invalid method name chars), `broadcastRpc`
crashes mid-loop leaving some clients sent and others not.

- Wrap the encode+send in `sendRpcTo` in try/catch
- On error, log and skip that send (don't crash the broadcast loop)

#### Fix 10: Wrap handlePacket body in try/catch

**File:** `ts/src/raknet/connection.ts`

Missing safety net around `processIncoming` in `handlePacket`. Unlikely given
existing defensive parsing but still a gap.

- Wrap the body of `handlePacket` in try/catch
- Log errors with `console.error`
- Note: Fix 1 (socket-level catch) provides a backstop, but catching here
  gives better error context (we know which session/address caused it)

## Approach

All fixes use the same pattern: try/catch at the boundary, log the error,
continue operating. No errors are silently swallowed — all are logged via
`console.error` (TS) or `log.error` (Python). The library never crashes the
host process due to bad network input or faulty user callbacks.

## Exit Criteria

1. All 10 fixes implemented.
2. Existing test suites pass (no false positives).
3. Each fix has at least one test demonstrating the error is caught rather
   than propagating.
4. TypeScript compiles cleanly.
