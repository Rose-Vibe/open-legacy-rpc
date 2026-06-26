# Unity Master Server Wire Format

## Overview

The Unity Master Server provides a server browser — game servers register
themselves, and clients query for available servers. The server is a thin
C++ wrapper around RakNet's `LightweightDatabaseServer` plugin.

Source: `~/unity-master-server/` (open source, built from Unity's release).

## Transport

Standard RakNet transport — same UDP handshake (open connection request 1 & 2,
connection request/accept) as game connections. Default port: **23466**.
No encryption (`Network.InitializeSecurity()` is never used).

The master server accepts up to 1000 concurrent connections (configurable via
`-c` flag).

## String Encoding: Huffman StringCompressor

All string fields in the protocol are Huffman-compressed using RakNet's
`StringCompressor`. The compressor uses a fixed frequency table
(`englishCharacterFrequencies` in `StringCompressor.cpp`) to build the
Huffman tree at initialization time.

### Huffman String Wire Format

```
compressed_uint32    stringBitLength   (how many bits of Huffman data follow)
bits[stringBitLength]  huffman_data    (Huffman-encoded characters)
```

`compressed_uint32` uses RakNet's `WriteCompressed` encoding:
- For a 4-byte unsigned int, starting from the highest byte:
  - If the byte is 0: write a `1` bit, move to next lower byte
  - Otherwise: write a `0` bit, then write the remaining bytes (from high to low)
- For the last byte: if upper nibble is 0, write `1` + 4 bits; else write `0` + 8 bits

The Huffman tree is deterministic — built from `GenerateFromFrequencyTable()`
using insertion-sort-based tree construction (see appendix for the full
256-entry frequency table). Zero-frequency entries are treated as weight 1.

## Bit-Level Encoding

The entire protocol payload (after the 1-byte message ID) is bit-packed via
RakNet's `BitStream`. Fields are written MSB-first within each byte.

All integer values (`Write(uint32)`, `Write(uint8)`, etc.) are big-endian.
Booleans are single bits. `double` values are 64-bit IEEE 754 big-endian.

## Message IDs

| ID (decimal) | ID (hex) | Name | Direction |
|---|---|---|---|
| 75 | 0x4b | ID_DATABASE_QUERY_REQUEST | Client → Server |
| 76 | 0x4c | ID_DATABASE_UPDATE_ROW | Client → Server |
| 77 | 0x4d | ID_DATABASE_REMOVE_ROW | Client → Server |
| 78 | 0x4e | ID_DATABASE_QUERY_REPLY | Server → Client |
| 79 | 0x4f | ID_DATABASE_UNKNOWN_TABLE | Server → Client |
| 80 | 0x50 | ID_DATABASE_INCORRECT_PASSWORD | Server → Client |
| 200 | 0xc8 | ID_DATABASE_ROWID | Server → Client |
| 201 | 0xc9 | ID_MASTERSERVER_REDIRECT | Server → Client |
| 202 | 0xca | ID_MASTERSERVER_MSG | Server → Client |

## Client Header (shared prefix)

UpdateRow and QueryRequest share this header format:

```
uint8     msg_id          (0x4c or 0x4b)
uint8[3]  version         [2, 0, 0]
huffman   tableName       (game type, e.g. "TestGame", max 32 chars)
bit       hasPassword
[huffman  password]       (only if hasPassword=1, max 32 chars)
```

RemoveRow uses a simpler header (no version check):

```
uint8     msg_id          (0x4d)
huffman   tableName
bit       hasPassword
[huffman  password]
uint32    rowId
```

### Version Check

The server compares the client's 3-byte version against its own. On
mismatch:
- If a redirect server is configured: sends `ID_MASTERSERVER_REDIRECT` (201)
  with the redirect address
- Otherwise: sends `ID_MASTERSERVER_MSG` (202) with an error string

## UpdateRow (0x4c)

Sent by game servers to register with the master server.

### Wire Format

```
--- Client Header ---
uint8     msg_id = 0x4c
uint8[3]  version = [2, 0, 0]
huffman   tableName       (game type string)
bit       hasPassword
[huffman  password]

--- Update Body ---
uint8     updateMode      (0=UPDATE_EXISTING, 1=UPDATE_OR_ADD, 2=ADD_NEW)
bit       hasRowId
[uint32   rowId]          (only if hasRowId=1)
uint8     numCellUpdates

--- Per Cell ---
huffman   columnName
uint8     columnType      (0=NUMERIC, 1=STRING, 2=BINARY, 3=POINTER)
          cellValue       (see Cell Serialization below)
```

Unity's `MasterServer.RegisterHost()` sends `updateMode=1`
(UPDATE_OR_ADD_ROW), `hasRowId=0`, with these cells:

| Column | Type | Example Value |
|--------|------|---------------|
| NAT | NUMERIC (0) | 0.0 |
| Game name | STRING (1) | "MyTestServer" |
| Connected players | NUMERIC (0) | 0.0 |
| Player limit | NUMERIC (0) | 4.0 |
| Password protected | NUMERIC (0) | 0.0 |
| IP address | BINARY (2) | 16 bytes: "10.200.1.2\0\0\0\0\0\0" |
| Port | NUMERIC (0) | 7777.0 |
| Comment | STRING (1) | "test_comment" |

### Server Response

```
uint8     msg_id = 0xc8 (ID_DATABASE_ROWID)
uint32    rowId           (assigned row ID, 0-based)
```

### Server-Side Overrides

After receiving the update, the server:
1. Overwrites the IP address column with the client's actual external IP
2. Overwrites the Port column with the client's actual port  
3. Sets the GUID column from the RakNet connection's GUID
4. Sets internal columns (`__SystemAddress`, `__SystemGuid`, `__lastPingResponseTime`, `__nextPingSendTime`)

## QueryTable (0x4b)

Sent by clients to list registered servers.

### Wire Format

```
--- Client Header ---
uint8     msg_id = 0x4b
uint8[3]  version = [2, 0, 0]
huffman   tableName
bit       hasPassword
[huffman  password]

--- Query Body ---
uint8     numColumnSubset   (0 = return all columns)
[huffman  columnName] × N   (columns to return, if N > 0)

uint8     numFilters
--- Per Filter (DatabaseFilter) ---
huffman   columnName
uint8     columnType        (0=NUMERIC, 1=STRING, 2=BINARY, 3=POINTER)
uint8     operation         (see Filter Operations below)
          cellValue         (only if operation != IS_EMPTY and != NOT_EMPTY)

uint8     numRowIDs         (0 = return all rows)
[uint32   rowId] × N        (specific rows, if N > 0)
```

Unity's `MasterServer.RequestHostList()` sends `numColumnSubset=0`,
`numFilters=0`, `numRowIDs=0` (return everything).

### Filter Operations

| Value | Name |
|-------|------|
| 0 | QF_EQUAL |
| 1 | QF_NOT_EQUAL |
| 2 | QF_GREATER_THAN |
| 3 | QF_GREATER_THAN_EQ |
| 4 | QF_LESS_THAN |
| 5 | QF_LESS_THAN_EQ |
| 6 | QF_IS_EMPTY |
| 7 | QF_NOT_EMPTY |

### Server Response: QueryReply (0x4e)

```
uint8     msg_id = 0x4e

--- SerializeColumns ---
uint32    numColumns
--- Per Column ---
huffman   columnName
uint8     columnType        (0=NUMERIC, 1=STRING, 2=BINARY, 3=POINTER)

--- Rows ---
uint32    numRows

--- Per Row (SerializeRow) ---
uint32    rowKey            (row ID)
uint32    numEntries        (number of cells in this row)
--- Per Entry ---
uint32    cellIndex         (column index)
          cellValue         (see Cell Serialization)
```

If the table doesn't exist or has zero rows, the server sends just:
```
uint8     msg_id = 0x4e
```
(no table data — 1 byte total)

### NAT IP Injection

If the querying client's external IP matches a registered server's IP, the
master server replaces the server's entry with internal IPs (for LAN play):
- NAT column → 0.0
- IP address column → internal IPs (binary, multiple 16-byte blocks)
- Port column → internal port

## RemoveRow (0x4d)

Sent by game servers to unregister.

```
uint8     msg_id = 0x4d
huffman   tableName
bit       hasPassword
[huffman  password]
uint32    rowId
```

## Cell Serialization

Cells are serialized via `TableSerializer::SerializeCell`:

### NUMERIC (type 0)

```
bit       isEmpty
[double   value]          (64-bit IEEE 754 big-endian, only if isEmpty=0)
```

### STRING (type 1)

```
bit       isEmpty
[huffman  value]          (Huffman string, max 65535 chars, only if isEmpty=0)
```

### BINARY (type 2)

```
bit       isEmpty
[uint32   length          (byte count, only if isEmpty=0)
 align    pad to byte boundary
 bytes    data[length]]
```

The `align` step pads the current bit position to the next byte boundary
before writing raw bytes (`WriteAlignedBytes`).

### POINTER (type 3)

```
bit       isEmpty
[uint64   ptr]            (platform-dependent, not used in practice)
```

## Table Schema

Tables are auto-created on first registration. The server pre-creates
4 internal columns, then the client's UpdateRow adds the game columns:

| Index | Column Name | Type | Source |
|-------|-------------|------|--------|
| 0 | `__SystemAddress` | BINARY | Server-managed |
| 1 | `__SystemGuid` | BINARY | Server-managed |
| 2 | `__lastPingResponseTime` | NUMERIC | Server-managed |
| 3 | `__nextPingSendTime` | NUMERIC | Server-managed |
| 4 | `NAT` | NUMERIC | Client |
| 5 | `Game name` | STRING | Client |
| 6 | `Connected players` | NUMERIC | Client |
| 7 | `Player limit` | NUMERIC | Client |
| 8 | `Password protected` | NUMERIC | Client |
| 9 | `IP address` | BINARY | Client (overridden by server) |
| 10 | `Port` | NUMERIC | Client (overridden by server) |
| 11 | `Comment` | STRING | Client |
| 12 | `GUID` | STRING | Server-managed |

Column indices 4, 5, 6, 7, 8, 9, 10, 11, 12 correspond to constants
NATINDEX, GAMEINDEX, PLAYERINDEX, LIMITINDEX, PASSWORDINDEX, IPINDEX,
PORTINDEX, COMMENTINDEX, GUIDINDEX in the C++ source.

## Lifecycle

- **One row per IP**: `oneRowPerSystemAddress = true` — each system address
  gets one entry per table. Re-registering updates the existing row.
- **Remove on disconnect**: Entries are removed when the connection drops.
- **Ping liveness**: Server pings registered hosts every 15 seconds. If no
  response after 75 seconds, the entry is removed.
- **Re-registration**: Unity clients re-register approximately every 5 minutes.
- **Empty table cleanup**: Tables with zero rows are deleted.

## RakNet Transport Details

- Messages use `RELIABLE_ORDERED` reliability (channel 0)
- Priority: `HIGH_PRIORITY`
- Standard RakNet connection handshake (no password by default)

## Verified Against Live Capture

All formats verified against traffic captured between Unity 2018.1.6f1
clients/server and the open-source C++ master server running locally.
Capture file: `/tmp/master_server.pcap` (pcapng format).

Decoded messages:
- Frame 7: UpdateRow — 8 cells, version [2,0,0], table "TestGame"
- Frame 15: RowID — row_id=0
- Frame 35: QueryRequest — version [2,0,0], table "TestGame", no filters
- Frame 46: QueryReply — 13 columns, 1 row with all cell values

## Appendix: English Character Frequency Table

The 256-entry frequency table used by `StringCompressor` to build the
Huffman tree (index = byte value, value = frequency weight):

```
  0:     0,   1:     0,   2:     0,   3:     0,   4:     0,   5:     0,
  6:     0,   7:     0,   8:     0,   9:     0,  10:   722,  11:     0,
 12:     0,  13:     2,  14:     0,  15:     0,  16:     0,  17:     0,
 18:     0,  19:     0,  20:     0,  21:     0,  22:     0,  23:     0,
 24:     0,  25:     0,  26:     0,  27:     0,  28:     0,  29:     0,
 30:     0,  31:     0,  32: 11084,  33:    58,  34:    63,  35:     1,
 36:     0,  37:    31,  38:     0,  39:   317,  40:    64,  41:    64,
 42:    44,  43:     0,  44:   695,  45:    62,  46:   980,  47:   266,
 48:    69,  49:    67,  50:    56,  51:     7,  52:    73,  53:     3,
 54:    14,  55:     2,  56:    69,  57:     1,  58:   167,  59:     9,
 60:     1,  61:     2,  62:    25,  63:    94,  64:     0,  65:   195,
 66:   139,  67:    34,  68:    96,  69:    48,  70:   103,  71:    56,
 72:   125,  73:   653,  74:    21,  75:     5,  76:    23,  77:    64,
 78:    85,  79:    44,  80:    34,  81:     7,  82:    92,  83:    76,
 84:   147,  85:    12,  86:    14,  87:    57,  88:    15,  89:    39,
 90:    15,  91:     1,  92:     1,  93:     1,  94:     2,  95:     3,
 96:     0,  97:  3611,  98:   845,  99:  1077, 100:  1884, 101:  5870,
102:   841, 103:  1057, 104:  2501, 105:  3212, 106:   164, 107:   531,
108:  2019, 109:  1330, 110:  3056, 111:  4037, 112:   848, 113:    47,
114:  2586, 115:  2919, 116:  4771, 117:  1707, 118:   535, 119:  1106,
120:   152, 121:  1243, 122:   100, 123:     0, 124:     2, 125:     0,
126:    10, 127:     0, 128-255:  0
```

Zero-weight entries are treated as weight 1 during tree construction.
