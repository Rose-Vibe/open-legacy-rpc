# M11: Master Server Protocol

## Goal

Reverse-engineer, document, and implement the Unity Master Server protocol
in Python — both server and client sides. The end state is:

1. A reference spec documenting the wire format
2. A Python master server that Unity clients can register with and query
3. A Python master server client that can register with and query a real
   Unity master server (or our Python one)

## Context

The Unity Master Server is open source (cloned to `~/unity-master-server`).
It uses RakNet's `LightweightDatabaseServer` plugin — a flat-table database
over RakNet transport. The protocol is:

- **Transport**: RakNet (same UDP handshake as game connections)
- **Application layer**: Table operations (query, update row, remove row)
  using RakNet's `StringCompressor` (Huffman) for field names and
  `TableSerializer` for cell values

Distance uses it at `[REDACTED]` for server browser registration.
The NAT facilitator runs on `:50005` (out of scope for now).

## Security Constraint

`Network.InitializeSecurity()` must NEVER be called in experiments.

---

## Protocol Summary (from source analysis)

### Message IDs

| ID | Name | Direction |
|----|------|-----------|
| 75 | ID_DATABASE_QUERY_REQUEST | Client → Server |
| 76 | ID_DATABASE_UPDATE_ROW | Client → Server |
| 77 | ID_DATABASE_REMOVE_ROW | Client → Server |
| 78 | ID_DATABASE_QUERY_REPLY | Server → Client |
| 79 | ID_DATABASE_UNKNOWN_TABLE | Server → Client |
| 80 | ID_DATABASE_INCORRECT_PASSWORD | Server → Client |
| 200 | ID_DATABASE_ROWID | Server → Client |
| 201 | ID_MASTERSERVER_REDIRECT | Server → Client |
| 202 | ID_MASTERSERVER_MSG | Server → Client |

### Version Check

Every query/update starts with:
- `msg_id` (1 byte)
- `version` (3 bytes): client version `[2, 0, 0]`

Server checks version. Mismatched versions get `ID_MASTERSERVER_REDIRECT`
(with fallback server address) or `ID_MASTERSERVER_MSG` (error string).

### Client Header (shared by query/update/remove)

After the version bytes:
1. `tableName` — Huffman-encoded string (max 32 chars)
2. `hasPassword` — 1 bit (bool)
3. If hasPassword: `password` — Huffman-encoded string (max 32 chars)

### Table Schema (auto-created per game type)

When a game type is first registered, the server creates a table with
these columns (indices matter for special handling):

| Index | Name | Type | Notes |
|-------|------|------|-------|
| 0 | `__SystemAddress` | BINARY | Internal, auto-set |
| 1 | `__SystemGuid` | BINARY | Internal, auto-set |
| 2 | `__lastPingResponseTime` | NUMERIC | Internal, for liveness |
| 3 | `__nextPingSendTime` | NUMERIC | Internal, for liveness |
| 4 | `NAT` | NUMERIC | NATINDEX — bool, NAT enabled |
| 5 | `Game name` | STRING | Server display name |
| 6 | `Connected players` | NUMERIC | Current player count |
| 7 | `Player limit` | NUMERIC | Max players |
| 8 | `Password protected` | NUMERIC | Bool |
| 9 | `IP address` | BINARY | External IP (injected by server) |
| 10 | `Port` | NUMERIC | Game port (injected by server) |
| 11 | `Comment` | STRING | Arbitrary metadata |
| 12 | `GUID` | STRING | RakNet GUID |

### UpdateRow (ID_DATABASE_UPDATE_ROW = 76)

Wire format after header:
1. `updateMode` (1 byte): RUM_UPDATE_EXISTING_ROW=0, RUM_UPDATE_OR_ADD_ROW=1, RUM_ADD_NEW_ROW=2
2. `hasRowId` (1 bit)
3. If hasRowId: `rowId` (uint32)
4. `numCellUpdates` (1 byte)
5. For each cell update:
   - `columnName` — Huffman string
   - `columnType` (1 byte): NUMERIC=0, STRING=1, BINARY=2, POINTER=3
   - Cell value (format depends on type)

Cell value serialization (all fields are bit-packed via RakNet BitStream):
- **NUMERIC**: `isEmpty` (1 bit) + `double` (64 bits, IEEE 754 big-endian)
- **STRING**: `isEmpty` (1 bit) + Huffman string (max 65535)
- **BINARY**: `isEmpty` (1 bit) + `length` (uint32) + byte-aligned payload

Note: `hasPassword`, `hasRowId`, `isEmpty`, etc. are all single-bit fields
in the RakNet BitStream. BINARY cell data is written with `WriteAlignedBytes`
which pads to byte boundary before writing raw bytes.

Server response: `ID_DATABASE_ROWID` (200) + `rowId` (uint32)

Server overrides:
- IP column: replaced with actual client IP
- Port column: replaced with actual client port
- GUID column: auto-set from RakNet GUID
- Internal columns (`__System*`, `__last*`, `__next*`): auto-managed

### QueryTable (ID_DATABASE_QUERY_REQUEST = 75)

Wire format after header:
1. `numColumnSubset` (1 byte): columns to return (0 = all)
2. For each: `columnName` — Huffman string
3. `numFilters` (1 byte)
4. For each filter (`DatabaseFilter`):
   - `columnName` — Huffman string
   - `columnType` (1 byte): NUMERIC=0, STRING=1, BINARY=2, POINTER=3
   - `operation` (1 byte): QF_EQUAL=0, QF_NOT_EQUAL=1, QF_GREATER_THAN=2,
     QF_GREATER_THAN_EQ=3, QF_LESS_THAN=4, QF_LESS_THAN_EQ=5,
     QF_IS_EMPTY=6, QF_NOT_EMPTY=7
   - If operation not IS_EMPTY/NOT_EMPTY: cell value (same format as cell serialization)
5. `numRowIDs` (1 byte): specific row IDs to return (0 = all)
6. For each: `rowId` (uint32)

Server response: `ID_DATABASE_QUERY_REPLY` (78) + serialized table:
1. Column count (uint32)
2. For each column: Huffman name + type byte
3. Row count (uint32)
4. For each row: `rowId` (uint32) + `numCells` (uint32) + cells

NAT handling: if querying client has same external IP as a registered
server, the server injects internal IPs instead of external (for LAN play).

### RemoveRow (ID_DATABASE_REMOVE_ROW = 77)

Wire format after header:
1. `rowId` (uint32)

### Lifecycle

- Tables are created dynamically on first registration per game type
- `oneRowPerSystemAddress = true` — each IP gets one entry
- `removeRowOnDisconnect = true` — entry removed when connection drops
- `removeRowOnPingFailure = true` — server pings registered hosts every
  15s, removes after 75s of no response
- Empty tables are deleted automatically
- Re-registration every ~5 minutes to stay alive

### Unity Client API Mapping

- `MasterServer.RegisterHost(gameType, name, comment)` →
  `ID_DATABASE_UPDATE_ROW` with RUM_UPDATE_OR_ADD_ROW
- `MasterServer.RequestHostList(gameType)` →
  `ID_DATABASE_QUERY_REQUEST`
- `MasterServer.UnregisterHost()` →
  `ID_DATABASE_REMOVE_ROW`

---

## Milestone 11a: Wire Format Verification ✅ COMPLETE

### Work

1. Build the C++ master server from source (or use the pre-built binary)
2. Run it locally on port 23466
3. Connect a Unity client, call `MasterServer.RegisterHost("TestGame", "MyServer", "test")`
4. Capture the traffic on the wire
5. Decode the UpdateRow message, verify it matches the source-derived format
6. Query from another client, decode the QueryReply
7. Document any discrepancies between source and wire

### Exit Criteria

- At least one UpdateRow and one QueryReply decoded from live capture
- Wire format matches source analysis (or discrepancies documented)
- Version bytes confirmed

---

## Milestone 11b: Reference Spec ✅ COMPLETE

### Work

1. Write `docs/research/master-server-wire-format.md` covering:
   - Transport (RakNet, same handshake as game connections)
   - Message IDs and version check
   - Client header format
   - UpdateRow, QueryTable, RemoveRow wire formats
   - Table schema
   - Cell serialization (NUMERIC, STRING, BINARY)
   - Lifecycle (ping/timeout, auto-remove)
   - NAT IP injection

### Exit Criteria

- Complete spec that an implementer can use without reading C++ source
- All field offsets and encoding documented

---

## Milestone 11c: Python Master Server ✅ COMPLETE

### Work

1. Implement `protocol/master_server.py` — a Python master server that:
   - Accepts RakNet connections
   - Handles UpdateRow, QueryTable, RemoveRow
   - Auto-creates tables per game type
   - Pings registered hosts, removes stale entries
   - Injects external IP / port
   - Sends version check, redirect, and error messages

2. Implement the table/cell serialization in `protocol/unity_protocol.py`
   (extends existing module — no new file needed since it shares the
   Huffman StringCompressor already there)

3. Tests:
   - Python master server + Python client (unit/integration)
   - Python master server + Unity client (interop)

### Exit Criteria

- Unity client can `RegisterHost` and `RequestHostList` against Python server
- Stale entries are removed after timeout
- Multiple game types work independently
- Version mismatch handling works (redirect or error message)
- NAT IP injection tested (client on same IP gets internal addresses)

---

## Milestone 11d: Python Master Server Client ✅ COMPLETE

### Work

1. Implement `protocol/master_client.py` — a Python client that:
   - Connects to a master server (Unity or Python)
   - `register_host(game_type, name, comment, ...)` → UpdateRow
   - `request_host_list(game_type)` → QueryTable → returns list of hosts
   - `unregister_host()` → RemoveRow
   - Handles `ID_DATABASE_ROWID`, `ID_DATABASE_QUERY_REPLY`
   - Deserializes table responses into Python dicts

2. Tests:
   - Python client + Python master server
   - Python client + C++ master server (if built)
   - Verify Distance game type listing against `[REDACTED]`
     (fallback: test against local C++ or Python master server if live
     server is down)

### Exit Criteria

- Can register a host and query the host list
- Can list Distance servers from the live master server
- Re-registration loop works

---

## Implementation Order

```
11a (Wire verification)  — verify source analysis against live capture
11b (Reference spec)     — document the format
11c (Python server)      — implement server
11d (Python client)      — implement client
```

11a validates our understanding before we write code. 11b documents it.
11c and 11d can proceed in parallel after 11b since they share the
serialization layer but are otherwise independent.
