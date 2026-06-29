# Fix: Ordering Index Collision Between RELIABLE_ORDERED and UNRELIABLE_SEQUENCED

**Date:** 2026-06-28
**Source:** Distance server two-player multiplayer testing
**TS commit:** `60ae204`

## Problem

When RELIABLE_ORDERED RPCs and UNRELIABLE_SEQUENCED state sync frames
were interleaved on the same ordering channel, all RPCs would eventually
stop being delivered to the receiver.

## Root Cause

RakNet's **receiver** maintains separate ordering index counters for
ORDERED vs SEQUENCED reliability types. The receiver's ORDERED handler
waits for consecutive indices (0, 1, 2, ...) and buffers out-of-order
frames. The SEQUENCED handler independently tracks its own sequence.

Our **sender** used a single shared `orderingIndexOut` map for both types.
When an UNRELIABLE_SEQUENCED frame was sent, it consumed an ordering index
(e.g., index 2) that the receiver's ORDERED counter expected. The receiver
then buffered all subsequent RELIABLE_ORDERED frames (index 3, 4, 5, ...)
waiting for index 2 which would never arrive as an ORDERED frame.

## Symptom

In the Distance server: after a few seconds of gameplay (once state sync
frames started flowing), the second player could not receive any RPCs
including StartMode and CreatePlayer. The server appeared to send them
correctly but the client's reliability layer silently buffered them.

## Fix

Split the outgoing ordering index counter into two independent maps:
- `orderingIndexOut` / `_ordering_index` — for RELIABLE_ORDERED
- `sequencingIndexOut` / `_sequencing_index` — for UNRELIABLE_SEQUENCED and RELIABLE_SEQUENCED

Both TS and Python implementations fixed.

## Files Changed

| Language | File | Change |
|----------|------|--------|
| TypeScript | `ts/src/raknet/reliability.ts` | Added `sequencingIndexOut` map, route sequenced types to it |
| Python | `protocol/raknet_transport.py` | Added `_sequencing_index` dict, route sequenced types to it |
| Test | `tests/test_raknet_transport.py` | Added `test_ordering_index_separate_for_ordered_vs_sequenced` |

## Key Insight

`isOrdered()` returns true for both ORDERED and SEQUENCED types (they
both carry an ordering index on the wire), but the receiver uses separate
counter spaces. The sender must mirror this separation.
