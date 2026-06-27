# M19: Documentation, Code Comments, and Production Hardening

## Motivation

Three parallel audits found gaps across documentation, code comments, and
production robustness. The TS implementation will see direct production use,
making the hardening items load-bearing. This milestone addresses all findings.

---

## Section A: Documentation

### A1: Create README.md

Write a project-level README covering:
- What the project is (one paragraph)
- Repository structure (protocol/, ts/, experiments/, docs/)
- Prerequisites (Python 3.10+, Node 18+)
- Quick start: install deps, run tests (both languages)
- Link to the reference spec (`docs/research/unity-legacy-networking-wire-format.md`)
- Link to master server spec (`docs/research/master-server-wire-format.md`)
- Brief usage example for both Python and TS (connect to a Unity server)
- Network namespace setup (reference CLAUDE.md's existing snippet)
- Shell scripts: what `run-experiment.sh`, `run-interop-tests.sh`,
  `run-server-only.sh` do and when to use them

### A2: Update CLAUDE.md

- Remove "Current Objective" or replace with a maintenance-oriented
  description reflecting that the spec and implementations are complete
- Remove references to `docs/architecture/`, `docs/roadmap/`, `docs/adr/`
- Remove ADR convention from the Conventions section

### A3: Remove empty directories

- Delete `docs/architecture/` (empty, no design docs were written)

**Exit criteria:** README.md exists and is accurate. CLAUDE.md has no
stale references. No empty placeholder directories.

---

## Section B: Code Comments

### B1: Fix wrong Python poll() docstrings

- `raknet_connection.py:97` — `RakNetClient.poll`: change docstring to
  "Returns list of (msg_id, payload, reliability, bit_length) tuples."
- `raknet_connection.py:296` — `RakNetServer.poll`: change docstring to
  "Returns list of (addr, msg_id, payload, reliability, bit_length) tuples."

### B2: Add JSDoc to key TS functions

Add one-line JSDoc (matching Python's existing docstrings) to:

- `bitstream.ts` — `BitStream` class: "Bit-level reader/writer for
  Unity/RakNet wire format. All multi-byte integers use big-endian."
- `rpc.ts:encodeRpcSubsequent` — "Encode a subsequent-use RPC
  (method already registered on receiver)."
- `rpc.ts:encodeRpcFirstUse` — "Encode a first-use RPC (includes
  method name hash)."
- `rpc.ts:decodeRpc` — "Decode a Unity RPC message."
- `rpc.ts:isRpc` — "Check if a 0x1b message is an RPC (byte 9 === 0x0b)
  vs state sync."
- `method-hash.ts:computeMethodId` — "Compute the first-use method
  identifier: 2 zero bits + Huffman(name). Returns classGuid + methodHash."
- `method-hash.ts:computeMethodIndex` — "Compute 7-bit method index
  from .NET metadata RID."
- `view-id.ts:encodeViewId` — "Encode a NetworkViewID as 48-bit
  big-endian bytes."
- `address.ts:encodeAddress` — "Encode IPv4 + port in RakNet's
  bitwise-inverted format."
- `huffman.ts:encodeStringForWire` — "Encode a string for RakNet wire
  format with byte-alignment padding."

### B3: Add JSDoc to TS API methods with non-obvious behavior

- `rpc-schema.ts:defineRpc` — "Define an RPC with typed fields and Zod
  validation. Registers the method signature for encode/decode."
- `server.ts:onTypedRpc` — "Register a typed RPC handler. RPCs failing
  Zod validation are silently dropped."
- `server.ts:sendTypedRpc` — "Send a typed RPC. Throws if args fail
  Zod validation."
- `client.ts:onStateSync` — "Register a state sync handler. Pass
  viewId=null for a catch-all handler."
- `client.ts:onTypedRpc` — "Register a typed RPC handler. RPCs failing
  Zod validation are silently dropped."
- `network-groups.ts:addClient` — "Add a client session. Auto-subscribes
  to group 0."
- `object-state-tracker.ts:update` — "Update field values. Returns
  per-field dirty flags."
- `master_client.py:register_host` — add docstring
- `master_client.py:request_host_list` — add docstring

**Exit criteria:** No HIGH or MEDIUM comment findings remain. All public
API methods with non-obvious behavior have doc comments.

---

## Section C: Production Hardening (TS focus)

### C1: Bytes param decode size limit

**Both languages.** Cap `bytes` param decode at 1MB (1_048_576). A
malicious packet with count=0xFFFFFFFF would attempt a 4GB allocation.

- `rpc.ts` `decodeParams`: check `count > MAX_BYTES_PARAM` before
  `readBytes(count)`, throw if exceeded
- `unity_protocol.py` `_decode_params`: same check
- Add constant `MAX_BYTES_PARAM_SIZE = 1_048_576` in both

### C2: Sequence number 24-bit wrapping

**Both languages.** RakNet uses 24-bit sequence numbers.

- TS `reliability.ts:72`: `this.sendSeq = (this.sendSeq + 1) & 0xFFFFFF`
  (and other increment sites at lines 130, 151)
- Python `raknet_transport.py`: mask `_send_seq` with `& 0xFFFFFF` after
  increment

### C3: `seenReliable` bounded dedup (TS)

Replace the unbounded `Set<number>` with a sliding window. Keep a
`minReliable` watermark; entries below it are implicitly "seen." On each
add, if the set grows past 10,000 entries, advance the watermark to the
lowest entry + some window and prune.

### C4: Connection timeout tick timer cleanup (TS)

In `RakNetClient.connect()`, if the promise rejects (timeout or failure),
clear `this.tickTimer`. Add cleanup in the `reject` paths.

### C5: ViewID allocation range overflow check (Python)

In `unity_server.py:allocate_view_id`, check that the allocated view_id
doesn't exceed the client's stride range. Throw if it would overflow
into another client's range. Match TS `ViewIdAllocator`'s behavior.

### C6: `max_connections` enforcement (Python)

In `raknet_connection.py:_handle_open_connection_request`, check
`len(self.peers) >= self.max_connections` before accepting. If at
capacity, don't create a new peer.

### C7: `orderingQueues` max depth (TS)

Add a max queue depth (e.g., 512) to `processOrdered`. If a channel's
queue exceeds this, drop the oldest entries and log a warning. Prevents
unbounded memory growth from lost frames.

### C8: `SplitPacketAssembler` timeout/limit (Python)

Add a max pending split count (e.g., 64) and a max age (e.g., 30s).
On each `add()`, prune entries older than max age or if count exceeds
limit (evict oldest). Prevents memory leak from incomplete fragments.

### C9: `splitAssembler` bounded (TS)

Same pattern as C8 but for `reliability.ts:27`'s
`splitAssembler: Map<number, SplitState>`. Add a max pending split
count (e.g., 64). On each new split ID, if the map exceeds the limit,
evict the oldest entry. Prevents unbounded memory growth from lost
fragments on long-lived connections.

**Exit criteria:** All MODERATE and MINOR hardening findings addressed.
No unbounded memory growth vectors remain in TS.

---

## Non-Goals

- Python reliable message dedup and ordered resequencing: significant
  transport rewrite, Python impl is reference-only not production
- Python split message sending: same rationale
- Python/TS network groups semantic alignment: different APIs are
  intentional (Python is reference, TS is production)
- ACK spoofing protection: would need sequence number tracking
  infrastructure, low-priority for non-adversarial use

## Implementation Order

A1 → A2 → A3 → B1 → B2 → B3 → C1 → C2 → C3 → C4 → C5 → C6 → C7 → C8 → C9

A-section and B-section are independent of C-section.

## Test Plan

- A: Manual verification of README accuracy
- B: No tests (doc comments only)
- C1: Test decoding an RPC with bytes count > limit — should throw
- C2: Test encoding a sequence number > 0xFFFFFF — should wrap
- C3: Test that seenReliable doesn't grow unbounded (add 20K entries,
  verify size stays bounded)
- C4: Test that tickTimer is null after failed connect
- C5: Test that allocating past stride throws
- C6: Test that connections beyond max_connections are rejected
- C7: Test that ordering queue doesn't grow past max depth
- C8: Test that stale split fragments are pruned
- C9: Test that TS splitAssembler doesn't grow past max entries
