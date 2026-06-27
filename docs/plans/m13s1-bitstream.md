# M13 Section 1: BitStream and Encoding Primitives

## Goal

Port the bit-level I/O primitives from Python to TypeScript. These are the
foundation for every protocol message.

## Modules

### `src/bitstream.ts` — BitStream

Bit-level read/write over a `Uint8Array` buffer.

**Write operations:**
- `writeBit(value: 0 | 1)` — single bit
- `writeBits(value: number, count: number)` — N bits from a number
- `writeU8(value: number)` — 8-bit unsigned
- `writeU16BE(value: number)` — 16-bit big-endian
- `writeU32BE(value: number)` — 32-bit big-endian
- `writeI32BE(value: number)` — 32-bit signed big-endian
- `writeFloatBE(value: number)` — IEEE 754 float (4 bytes, big-endian)
- `writeBytes(data: Uint8Array)` — raw byte array
- `writeCompressedU32(value: number)` — RakNet compressed uint32
- `writeAlignedBytes(data: Uint8Array)` — align to byte boundary, then write

**Read operations:** mirror of write ops.

**Properties:**
- `bitLength: number` — total bits written
- `readOffset: number` — current read position in bits

**Conversion:**
- `toBytes(): Uint8Array` — padded to byte boundary
- `static fromBytes(data: Uint8Array, bitLength?: number): BitStream`

Port from: `protocol/bitstream.py` (222 lines)

### `src/huffman.ts` — Huffman Codec

RakNet's Huffman encoding tree (256 entries, hardcoded frequencies).

**API:**
- `encodeString(s: string): { data: Uint8Array; bitLength: number }`
- `decodeString(data: Uint8Array, bitLength: number): string`
- `encodeStringForWire(s: string): string` — returns bit string (used internally)

Port from: `protocol/huffman.py` (138 lines)

### `src/raknet/address.ts` — Address Encoding

RakNet's bitwise-inverted IP address format.

**API:**
- `encodeAddress(ip: string, port: number): Uint8Array`
- `decodeAddress(data: Uint8Array): { ip: string; port: number }`

Port from: `protocol/raknet_transport.py` (address functions only)

## Conformance Test Mapping

| Category | What it validates |
|----------|-------------------|
| `writeCompressed` | `writeCompressedU32` output |
| `readCompressed` | `readCompressedU32` output |
| `bitstream` | All write operations |
| `bitstreamRead` | All read operations |
| `huffman` | `encodeString` output |
| `huffmanDecode` | `decodeString` output |
| `addressEncode` | `encodeAddress` output |
| `addressDecode` | `decodeAddress` output |

After implementing each module, add it to the conformance bridge and
run the corresponding serde tests. All 8 categories must pass in both
basic and random modes.

## Exit Criteria

- [ ] BitStream class with all read/write operations
- [ ] Huffman codec with full 256-entry tree
- [ ] Address encoder/decoder
- [ ] All 8 conformance test categories pass (basic + random)
- [ ] Unit tests for edge cases not covered by conformance tests
  - BitStream: empty stream, single bit, byte alignment, buffer growth
  - Huffman: empty string, all-256-bytes string, single char
  - Address: 0.0.0.0, 255.255.255.255, port 0, port 65535
- [ ] `pnpm typecheck` and `pnpm lint` pass
