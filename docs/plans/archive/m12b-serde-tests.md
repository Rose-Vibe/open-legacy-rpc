# M12b: Serde Unit Tests

## Goal

Implement generate + validate for every encoding category in the protocol.
Each category has preset tests (known edge cases) and random tests
(randomized values).

## Categories

### 1. `huffman` — Huffman String Encoding

Tests the RakNet StringCompressor: ASCII string → Huffman bit-string.

**Input:** `{ "string": "Hello" }`
**Output:** `{ "dataHex": "abcd...", "bitLength": 42 }`

The implementer encodes the string using the fixed English character
frequency table and returns the raw Huffman-encoded bits (the EncodeArray
output, NOT including the WriteCompressed length prefix).

**Preset tests:**
| # | Input | Why |
|---|-------|-----|
| 1 | `""` | Empty string → 0-bit output |
| 2 | `"A"` | Single character |
| 3 | `"Hello"` | Basic mixed-case |
| 4 | `" "` | Space (high frequency, short code) |
| 5 | `"zzz"` | Low-frequency character (long codes) |
| 6 | `"Hello, World!"` | Punctuation + space |
| 7 | `"\x01"` | Byte 0x01 (rare, near-max code length) |
| 8 | All 256 byte values | Full character set round-trip |

**Random tests:**
- Random ASCII strings, length 0–1000
- Random byte sequences (0x00–0xFF), length 0–500
- Validate: decode the output bits using reference tree, compare to input

---

### 2. `huffmanDecode` — Huffman String Decoding

Inverse of category 1: given Huffman bits, decode to string.

**Input:** `{ "dataHex": "abcd...", "bitLength": 42 }`
**Output:** `{ "string": "Hello" }`

**Preset tests:** Same strings as category 1 (encode with reference, give
bits as input).

**Random tests:** Encode random strings with reference, give bits as input.

---

### 3. `writeCompressed` — RakNet WriteCompressed<uint32>

Tests the variable-length uint32 encoding (skip leading zero bytes with
1-bit flags, nibble optimization on final byte).

**Input:** `{ "value": 12345 }`
**Output:** `{ "dataHex": "...", "bitLength": N }`

**Preset tests:**
| # | Input | Why |
|---|-------|-----|
| 1 | `0` | All zeros → maximum compression |
| 2 | `1` | Smallest nonzero |
| 3 | `127` | Fits in 7 bits (nibble boundary) |
| 4 | `128` | Crosses nibble boundary |
| 5 | `255` | Full single byte |
| 6 | `256` | Two bytes, second byte is 0x01 |
| 7 | `65535` | 0xFFFF, two full bytes |
| 8 | `65536` | Three bytes |
| 9 | `16777215` | 0xFFFFFF, three full bytes |
| 10 | `16777216` | Four bytes |
| 11 | `4294967295` | 0xFFFFFFFF, maximum uint32 |

**Random tests:** Random uint32 values [0, 2^32-1].
Validate: decode the output back to uint32, compare.

---

### 4. `readCompressed` — RakNet ReadCompressed<uint32>

Inverse: given compressed bytes, decode to uint32.

**Input:** `{ "dataHex": "...", "bitLength": N }`
**Output:** `{ "value": 12345 }`

**Preset + random:** Encode reference values, give as input.

---

### 5. `bitstream` — BitStream Primitive Read/Write

Tests individual BitStream operations in isolation.

**Input:** A sequence of write operations:
```json
{
  "operations": [
    {"op": "writeU8", "value": 255},
    {"op": "writeBool", "value": true},
    {"op": "writeU32BE", "value": 12345},
    {"op": "writeFloatBE", "value": 3.14},
    ...
  ]
}
```
**Output:** `{ "dataHex": "...", "bitLength": N }`

Supported operations (write direction):
- `writeU8`, `writeU16BE`, `writeI16BE`, `writeU32BE`, `writeI32BE`
- `writeFloatBE`, `writeDoubleBE`
- `writeBool`, `writeBit`, `writeBits` (value + count)
- `writeBytes` (hex string)
- `writeCompressedU32`
- `writeVector3` (x, y, z)
- `writeQuaternion` (x, y, z, w)
- `writeAlignedBytes` (hex string)
- `writeChar`

**Preset tests:**
| # | Operations | Why |
|---|-----------|-----|
| 1 | Single `writeU8(0)` | Minimal |
| 2 | `writeU8(255)` | Full byte |
| 3 | `writeBool(true) + writeU8(42)` | Bit-misaligned byte write |
| 4 | `writeBit(1) × 9` | Crosses byte boundary |
| 5 | `writeFloatBE(0.0)` | Float zero |
| 6 | `writeFloatBE(-1.0)` | Negative float |
| 7 | `writeFloatBE(NaN)` | NaN preservation |
| 8 | `writeFloatBE(Inf)` | Infinity |
| 9 | `writeDoubleBE(3.14159...)` | Double precision |
| 10 | `writeAlignedBytes` after 3 bits | Alignment padding |
| 11 | `writeVector3(1.0, 2.0, 3.0)` | Compound type |
| 12 | `writeQuaternion(0, 0, 0, 1)` | Identity quaternion |
| 13 | `writeI32BE(-1)` | Signed negative |
| 14 | `writeI16BE(-32768)` | Signed min |
| 15 | `writeBits(0x1F, 5)` | Arbitrary bit count |

**Random tests:**
- Random sequence of 3–20 operations with random values in valid ranges
- Validate: execute same operations with reference BitStream, compare output

---

### 6. `bitstreamRead` — BitStream Primitive Read

Inverse: given bytes, execute a sequence of read operations.

**Input:**
```json
{
  "dataHex": "...",
  "bitLength": N,
  "operations": [
    {"op": "readU8"},
    {"op": "readBool"},
    ...
  ]
}
```
**Output:**
```json
{
  "values": [255, true, ...]
}
```

**Preset + random:** Write reference values, give bytes + op list as input.

---

### 7. `cell` — Master Server Cell Serialization

Tests the TableSerializer cell encoding (isEmpty bit + type-specific data).

**Input:**
```json
{
  "cellType": "NUMERIC|STRING|BINARY",
  "value": ...  // number, string, or hex string; null for empty
}
```
**Output:** `{ "dataHex": "...", "bitLength": N }`

**Preset tests:**
| # | Type | Value | Why |
|---|------|-------|-----|
| 1 | NUMERIC | `0.0` | Zero double |
| 2 | NUMERIC | `42.0` | Integer as double |
| 3 | NUMERIC | `-1.5` | Negative fractional |
| 4 | NUMERIC | `null` | Empty cell |
| 5 | STRING | `"Hello"` | Basic string |
| 6 | STRING | `""` | Empty string (not null) |
| 7 | STRING | `null` | Null string |
| 8 | BINARY | `"deadbeef"` | 4 bytes |
| 9 | BINARY | `""` | Zero-length binary |
| 10 | BINARY | `null` | Null binary |
| 11 | NUMERIC | `1e308` | Near max double |
| 12 | STRING | 1000-char string | Long string |

**Random tests:**
- Random type + random value (doubles, ASCII strings, byte sequences)
- Validate: decode output with reference, compare

---

### 8. `cellDecode` — Master Server Cell Deserialization

Inverse of category 7.

**Input:** `{ "cellType": "NUMERIC|STRING|BINARY", "dataHex": "...", "bitLength": N }`
**Output:** `{ "value": ... }`

---

### 9. `updateRow` — Full UpdateRow Message

Tests the complete ID_DATABASE_UPDATE_ROW (0x4C) encode.

**Input:**
```json
{
  "tableName": "TestGame",
  "password": null,
  "updateMode": 1,
  "rowId": null,
  "cells": [
    {"name": "Game name", "type": "STRING", "value": "My Server"},
    {"name": "Port", "type": "NUMERIC", "value": 7777.0},
    ...
  ]
}
```
**Output:** `{ "dataHex": "..." }`

**Preset tests:**
| # | Scenario | Why |
|---|----------|-----|
| 1 | Standard Unity registration (8 cells) | Golden path |
| 2 | Single cell | Minimal message |
| 3 | With password | Password field encoding |
| 4 | With explicit rowId | hasRowId=true path |
| 5 | ADD_NEW_ROW mode | Update mode 2 |
| 6 | All cell types mixed | NUMERIC + STRING + BINARY in one message |
| 7 | Empty string values | Edge case for Huffman |
| 8 | Binary cell with alignment | Tests WriteAlignedBytes in context |

**Random tests:**
- Random table name, random cell count (1–12), random cell types/values
- Validate: decode output with reference, compare all fields

---

### 10. `updateRowDecode` — Full UpdateRow Decode

Inverse: given bytes, decode to UpdateRow fields.

---

### 11. `queryRequest` — Full QueryRequest Message

Tests ID_DATABASE_QUERY_REQUEST (0x4B) encode.

**Input:**
```json
{
  "tableName": "TestGame",
  "password": null,
  "columnSubset": [],
  "filters": [
    {"name": "Port", "type": "NUMERIC", "operation": "EQUAL", "value": 7777.0}
  ],
  "rowIds": []
}
```
**Output:** `{ "dataHex": "..." }`

**Preset tests:**
| # | Scenario | Why |
|---|----------|-----|
| 1 | No filters, no subset, no row IDs | Simplest query |
| 2 | Column subset (3 columns) | Subset encoding |
| 3 | EQUAL filter on NUMERIC | Basic filter |
| 4 | NOT_EQUAL filter on STRING | String comparison filter |
| 5 | IS_EMPTY filter | No-value filter variant |
| 6 | Multiple filters | Combined filtering |
| 7 | Specific row IDs | Row ID list |
| 8 | All filter operations | One of each |

**Random tests:**
- Random filters (0–5), random subsets, random row IDs
- Validate: decode output, compare

---

### 12. `queryRequestDecode` — Full QueryRequest Decode

---

### 13. `queryReply` — Full QueryReply Message

Tests ID_DATABASE_QUERY_REPLY (0x4E) encode.

**Input:**
```json
{
  "columns": [
    {"name": "Game name", "type": "STRING"},
    {"name": "Port", "type": "NUMERIC"}
  ],
  "rows": [
    {"key": 0, "cells": {"Game name": "Server 1", "Port": 7777.0}}
  ]
}
```
**Output:** `{ "dataHex": "..." }`

**Preset tests:**
| # | Scenario | Why |
|---|----------|-----|
| 1 | Single row, 2 columns | Minimal |
| 2 | Empty reply (no columns) | Empty table |
| 3 | Multiple rows (5) | Multi-row encoding |
| 4 | Full Unity schema (13 columns, 1 row) | Real-world column set |
| 5 | Sparse cells (not all columns populated) | Partial cell set |
| 6 | Row with all-null cells | isEmpty=true for every cell |

**Random tests:**
- Random column count (1–15), random row count (0–10), random cell values
- Validate: decode output, compare

---

### 14. `queryReplyDecode` — Full QueryReply Decode

---

### 15. `removeRow` — Full RemoveRow Message

Tests ID_DATABASE_REMOVE_ROW (0x4D).

**Input:** `{ "tableName": "TestGame", "password": null, "rowId": 42 }`
**Output:** `{ "dataHex": "..." }`

**Preset tests:**
| # | Scenario | Why |
|---|----------|-----|
| 1 | Basic remove | Golden path |
| 2 | With password | Password encoding |
| 3 | Row ID 0 | Boundary |
| 4 | Row ID 0xFFFFFFFF | Max uint32 |

---

### 16. `removeRowDecode` — Full RemoveRow Decode

---

### 17. `rpcEncode` — RPC Message Encoding

Tests the full 0x1B RPC message (subsequent-use format).

**Input:**
```json
{
  "methodName": "RPC_Int",
  "methodIndex": 84,
  "viewId": {"scope": "scene", "id": 0},
  "rpcCounter": 1,
  "rpcMode": "Others",
  "params": [{"type": "int", "value": 42}]
}
```
**Output:** `{ "dataHex": "...", "bitLength": N }`

**Preset tests:**
| # | Method | Params | Why |
|---|--------|--------|-----|
| 1 | `RPC_Int` | `[42]` | Single int param |
| 2 | `RPC_Float` | `[3.14]` | Single float |
| 3 | `RPC_String` | `["hello"]` | Huffman string param |
| 4 | `RPC_Vector3` | `[1.0, 2.0, 3.0]` | Vector3 param |
| 5 | `RPC_Quaternion` | `[0, 0, 0, 1]` | Quaternion param |
| 6 | `RPC_Bytes` | `["deadbeef"]` | byte[] param |
| 7 | `RPC_IntFloatString` | `[1, 2.0, "hi"]` | Multi-param |
| 8 | `RPC_Void` | `[]` | No params |
| 9 | Any, mode=Server | | RPCMode encoding |
| 10 | Any, mode=AllBuffered | | Buffered mode |
| 11 | ViewID scope=allocated | | Allocated ViewID encoding |
| 12 | High rpcCounter (255) | | Counter rollover boundary |

**Random tests:**
- Random method from known set, random valid params, random counter/mode
- Validate: decode output, compare all fields

---

### 18. `rpcDecode` — RPC Message Decoding

---

### 19. `rpcFirstUse` — First-Use RPC Encoding

Tests the first-use format (includes method hash + class GUID).

**Input:**
```json
{
  "methodName": "RPC_Int",
  "viewId": {"scope": "scene", "id": 0},
  "rpcCounter": 0,
  "rpcMode": "Others",
  "params": [{"type": "int", "value": 42}]
}
```
**Output:** `{ "dataHex": "...", "bitLength": N }`

**Preset tests:** Same methods as category 17, but first-use format.

---

### 20. `rpcFirstUseDecode` — First-Use RPC Decoding

---

### 21. `methodHash` — RPC Method Hash Derivation

Tests the Huffman-based method identifier computation.

**Input:** `{ "methodName": "RPC_Int" }`
**Output:** `{ "classGuidHex": "...", "methodHashHex": "..." }`

**Preset tests:**
| # | Method | Why |
|---|--------|-----|
| 1–13 | All 13 known methods from METHOD_SIGNATURES | Full coverage |
| 14 | `"__RPCNetworkInstantiate"` | Internal RPC |
| 15 | Single-char name `"X"` | Minimal |
| 16 | Long name (64 chars) | Long hash input |

**Random tests:** Random ASCII method names, length 1–100.

---

### 22. `methodIndex` — RPC Method Index Derivation

Tests the formula `(RID - 1 - interfaceMethodCount) × 4`.

**Input:** `{ "methodRid": 7, "interfaceMethodCount": 0 }`
**Output:** `{ "methodIndex": 24 }`

**Preset tests:**
| # | RID | iface | Expected | Why |
|---|-----|-------|----------|-----|
| 1 | 1 | 0 | 0 | Minimum |
| 2 | 7 | 0 | 24 | Known value |
| 3 | 22 | 0 | 84 | RPC_Int in test DLL |
| 4 | 5 | 2 | 8 | With interface methods |

**Random tests:** Random RID [1, 100], random iface [0, 10].

---

### 23. `stateSync` — State Sync Encoding

Tests the unreliable state sync message (UNRELIABLE_SEQUENCED).

**Input:**
```json
{
  "viewId": {"scope": "scene", "id": 0},
  "timestamp": 1234,
  "isFirst": true,
  "fields": [
    {"type": "float", "value": 1.5},
    {"type": "int", "value": 42}
  ]
}
```
**Output:** `{ "dataHex": "...", "bitLength": N }`

**Preset tests:**
| # | Fields | Why |
|---|--------|-----|
| 1 | Single float | Minimal |
| 2 | int + float + Vector3 | Mixed types |
| 3 | Quaternion | 128-bit field |
| 4 | bool | 1-bit field |
| 5 | short + char | Small fields |
| 6 | isFirst=false | Non-first flag |
| 7 | Allocated ViewID | ViewID encoding variant |

**Random tests:** Random field types and values, random timestamp.

---

### 24. `stateSyncDecode` — State Sync Decoding

---

### 25. `deltaStateSync` — ReliableDeltaCompressed State Sync

Tests dirty-flag interleaved encoding.

**Input:**
```json
{
  "viewId": {"scope": "scene", "id": 0},
  "timestamp": 1234,
  "isFirst": true,
  "fieldWidths": [32, 32, 96],
  "fieldValues": [42, 1065353216, [1.0, 2.0, 3.0]],
  "prevValues": [0, 0, [0.0, 0.0, 0.0]]
}
```
**Output:** `{ "dataHex": "...", "bitLength": N }`

**Preset tests:**
| # | Scenario | Why |
|---|----------|-----|
| 1 | All fields dirty (isFirst=true) | Full write |
| 2 | No fields dirty | Minimal delta |
| 3 | One of three dirty | Selective dirty flags |
| 4 | Single field | Minimal field count |

**Random tests:** Random field count (1–8), random widths, random values.

---

### 26. `deltaSyncDecode` — ReliableDeltaCompressed Decode

---

### 27. `viewId` — NetworkViewID Encoding

Tests the 48-bit NetworkViewID wire encoding.

**Input:** `{ "scope": "scene|allocated", "id": 5 }`
**Output:** `{ "dataHex": "..." }` (6 bytes)

**Preset tests:**
| # | Scope | ID | Why |
|---|-------|-----|-----|
| 1 | scene | 0 | Server primary view |
| 2 | scene | 1 | Second scene view |
| 3 | allocated | 1 | First allocated |
| 4 | allocated | 50 | Stride boundary |
| 5 | scene | 999 | Large scene ID |

---

### 28. `viewIdParam` — NetworkViewID as RPC Parameter (16-bit)

Tests the packed 16-bit ViewID encoding used in RPC parameters.

**Input:** `{ "scope": "scene|allocated", "id": 5 }`
**Output:** `{ "value16": N }` (uint16)

**Preset tests:**
| # | Scope | ID | Expected | Why |
|---|-------|-----|----------|-----|
| 1 | scene | 0 | 0 | Zero |
| 2 | scene | 1 | 4 | `1 << 2` |
| 3 | allocated | 1 | 16448 | `0x4000 \| (1 << 6)` |
| 4 | scene | 100 | 400 | Large scene |

---

### 29. `addressEncode` — RakNet IP Address Encoding

Tests the bitwise-inverted IPv4 + uint16 BE port format.

**Input:** `{ "ip": "192.168.1.1", "port": 7777 }`
**Output:** `{ "dataHex": "..." }` (6 bytes)

**Preset tests:**
| # | IP | Port | Why |
|---|-----|------|-----|
| 1 | `127.0.0.1` | 7777 | Loopback |
| 2 | `0.0.0.0` | 0 | All zeros |
| 3 | `255.255.255.255` | 65535 | All ones |
| 4 | `192.168.1.100` | 23466 | Typical LAN + master server port |

---

### 30. `addressDecode` — RakNet IP Address Decoding

---

## Implementation Notes

- Each encode category has a matching decode category. They share preset
  values — the encode test's expected output becomes the decode test's input.
- Random test generators use Python's `random` module with a configurable
  seed for reproducibility.
- Binary data in JSON is always hex-encoded strings with key `dataHex`.
- Float values use JSON number format. NaN and Infinity use the strings
  `"NaN"`, `"Infinity"`, `"-Infinity"` since JSON doesn't support them.
- The `bitLength` field is included whenever the output is not byte-aligned
  (i.e., trailing bits matter).

## Exit Criteria

- [ ] All 30 categories implemented (generate + validate)
- [ ] Every preset test passes with the reference implementation
- [ ] Random tests with seed=0 pass with the reference implementation
- [ ] Pipeline end-to-end test exists for each category
- [ ] JSON Schema validates all generated test objects
