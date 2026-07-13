# Dynamically-learned subsequent-use indices leak across connections via a shared global table

## Context

While adding real-fixture regression tests for the `decode_batch_index` bit-
layout fix (see `docs/research/2026-07-13-batch-index-decoder-was-broken.md`),
a new end-to-end test modeling CLAUDE.md's "two genuinely different
assemblies" convention
(`tests/test_cross_assembly_batch_index_dispatch.py`) surfaced a second,
unrelated bug: when two `UnityClient` instances that each dynamically learn a
*different* index for the same method name coexist in one process, one
instance's subsequent-use RPCs misdispatch on the other.

Reproduction: server sends first-use `RPC_Int` then `RPC_Float` to client A
(A's own table: `RPC_Int=4, RPC_Float=8`); a second, independent
server/client pair sends first-use in the *opposite* order to client B (B's
own table: `RPC_Float=4, RPC_Int=8`). Sending subsequent-use `RPC_Int(42)` to
client A then dispatches as `RPC_Float` with a garbage value instead of
`RPC_Int(42)`.

## Root cause

`protocol/unity_protocol.py` has one module-level global,
`INDEX_TO_METHOD = {}`, meant for two distinct purposes that must not share
storage:

1. **Static, pre-registered tables** (`register_method_indices`/
   `register_method_index_table`): a real Unity peer's compiled, per-build
   index scheme, extracted via Cecil ahead of time. Safe to be global *only*
   because a whole process talks to one known real build.
2. **Dynamically-learned, per-connection indices**: when *our own*
   implementation is the receiver of a first-use RPC, it invents its own
   index (in local first-use-arrival order) and tells the sender via `0x07`.
   This value is only meaningful for that one connection — a different peer
   (a "different assembly") may legitimately get a different index for the
   same method name, by design (that's the whole point of the receiver-
   assigns-and-announces scheme).

`unity_client.py`'s and `unity_server.py`'s `_handle_rpc` first-use branch
writes case (2) into the same global as case (1)
(`INDEX_TO_METHOD[idx] = method`, unconditional, on every first-use), and
`decode_rpc` (`unity_protocol.py:541`) resolves a subsequent-use message's
`method_name` from that same global *unconditionally* at decode time. The
caller (`_handle_rpc`'s subsequent-use branch) only consults its own correct
per-instance `_our_index_reverse` map as a fallback, and only when
`decode_rpc` already failed to resolve anything (`method_name` starting with
`unknown_0x`). Since two connections' dynamically-learned entries land in the
same global, whichever connection wrote last to a given index wins for
*every* connection's decode — the second client in the repro above
overwrites index 4's mapping from `RPC_Int` to `RPC_Float`, and the first
client's subsequent decode reads that clobbered value.

`ts/src/unity/rpc.ts` / `client.ts` / `server.ts` do not have this bug:
`learnMethodIndex` (the only TS path that touches the shared
`INDEX_TO_METHOD` map for a dynamically-learned index) is only called from a
rare recovery branch and guards with `if (INDEX_TO_METHOD.has(index)) return`
(first writer wins, never overwrites); more importantly, TS's subsequent-use
branch checks the instance-local `ourIndexReverse` map *first*, unconditionally,
before ever consulting the shared map or the fallback-learn path. Python's
decode-then-override order is backwards from this.

## Why this matters

This is exactly the scenario the project's standing "two genuinely different
assemblies" testing convention exists to catch: a `UnityServer` that talks to
multiple peers whose first-use arrival order (and thus dynamically-learned
index scheme) differs is the *normal* case, not an edge case — e.g. two
players connecting in different order, or reconnecting after a state that
altered which methods were already first-used. Right now this cannot be
demonstrated with a single real Unity client process against our server
(the real client's *own* first-use order to us is whatever it is; the
divergence bites when *our* server or client is itself hosting/managing
more than one such per-connection table, or — as this project's convention
specifically calls out — in any future test harness that runs multiple
`UnityClient`/`UnityServer` instances in one process to simulate multiple
peers/builds, which is precisely what surfaced it).

## Fix

Mirror the TS design exactly, in both `protocol/unity_client.py` and
`protocol/unity_server.py`:

1. In the first-use branch of `_handle_rpc`, stop writing to the module
   global `INDEX_TO_METHOD` at all. Only populate the per-instance
   `_our_index_reverse` (client) / `_our_indices`+`_our_index_reverse`
   (server, already per-instance, not per-peer — unaffected, see "Not in
   scope" below).
2. In the subsequent-use branch, always check the instance's own
   `_our_index_reverse.get(method_index)` first (using `result['method_index']`,
   already returned by `decode_rpc` unconditionally), regardless of whether
   `decode_rpc`'s own `method_name` resolved to something via the global or
   to `unknown_0x..`. Fall back to `decode_rpc`'s supplied name only when the
   instance has no local entry for that index — this is what preserves the
   real-Unity-interop case (a pre-registered static table via
   `register_method_indices`, which the instance never dynamically learned
   itself, must still resolve).

No change needed to `encode_batch_index`/`decode_batch_index` (already fixed
separately) or to the wire format. No change needed on the TS side (already
correct). No change needed to `_peer_indices` (server, keyed by `addr`,
already correctly per-peer for the encode direction) — this fix is purely
about the *decode* side reading its own per-instance table before a shared
global.

## Not in scope

- `unity_server.py`'s `_our_indices` (the index the *server* assigns when
  *it* is the receiver of a client's first-use RPC) is intentionally a
  single shared-across-all-peers dict, not per-peer — this is correct by
  design: the server is the one authority deciding what index it wants used
  for messages sent *to it*, and it always hands out the same value for a
  given method name to every peer that asks (first-asker-wins, later askers
  get the already-assigned value). This plan does not touch that.
- Retracting/correcting `docs/research/2026-07-13-subsequent-use-static-index-dispatch.md`'s
  now-falsified "0x07 is a red herring" claim — tracked separately (task #24
  in the current investigation), since that document's error stems from the
  `decode_batch_index` bit-layout bug, not this one.
- Any change to the static per-method-index formula itself (still governed
  by CLAUDE.md's "do not re-derive from scratch" guidance).

## Exit criteria

- `tests/test_cross_assembly_batch_index_dispatch.py`'s
  `test_subsequent_use_dispatches_correctly_with_divergent_peer_indices`
  passes (currently fails on `main` + the batch_index fix alone, before this
  additional fix).
- Full Python test suite passes (aside from the pre-existing, unrelated
  `test_recv_rpc_filtered_by_group` failure already present on `main`).
- Full TS test suite continues to pass unchanged (no TS code touched).
- A short regression test confirms the real-Unity-interop case (a
  pre-registered static `register_method_indices` table) still resolves
  correctly when the instance has no dynamically-learned entry of its own —
  guards against fixing the leak by breaking static-table resolution.
