import * as process from 'node:process';
import { BitStream } from '../src/bitstream.js';
import { decodeString, encodeBytesForWire } from '../src/huffman.js';
import { encodeAddress, decodeAddress } from '../src/raknet/address.js';

interface TestCase {
  testInfo: { category: string; [k: string]: unknown };
  input: Record<string, unknown>;
  output?: Record<string, unknown>;
}

type CategoryHandler = (input: Record<string, unknown>) => Record<string, unknown>;

function hexToBytes(hex: string): Uint8Array {
  const result = new Uint8Array(hex.length / 2);
  for (let i = 0; i < hex.length; i += 2) {
    result[i / 2] = parseInt(hex.slice(i, i + 2), 16);
  }
  return result;
}

function bytesToHex(data: Uint8Array): string {
  let hex = '';
  for (let i = 0; i < data.length; i++) {
    hex += data[i]!.toString(16).padStart(2, '0');
  }
  return hex;
}

// ── BitStream write executor ──

interface WriteOp {
  op: string;
  value?: number | boolean | string;
  count?: number;
  dataHex?: string;
  x?: number;
  y?: number;
  z?: number;
  w?: number;
}

function execWrite(bs: BitStream, op: WriteOp): void {
  switch (op.op) {
    case 'writeU8':
      bs.writeU8(op.value as number);
      break;
    case 'writeU16BE':
      bs.writeU16BE(op.value as number);
      break;
    case 'writeI16BE':
      bs.writeI16BE(op.value as number);
      break;
    case 'writeU32BE':
      bs.writeU32BE(op.value as number);
      break;
    case 'writeI32BE':
      bs.writeI32BE(op.value as number);
      break;
    case 'writeFloatBE':
      bs.writeFloatBE(op.value as number);
      break;
    case 'writeDoubleBE':
      bs.writeDoubleBE(op.value as number);
      break;
    case 'writeBool':
      bs.writeBool(op.value as boolean);
      break;
    case 'writeBit':
      bs.writeBit(op.value as number);
      break;
    case 'writeBits':
      bs.writeBits(op.value as number, op.count!);
      break;
    case 'writeBytes':
      bs.writeBytes(hexToBytes(op.dataHex!));
      break;
    case 'writeCompressedU32':
      bs.writeCompressedU32(op.value as number);
      break;
    case 'writeVector3':
      bs.writeVector3(op.x!, op.y!, op.z!);
      break;
    case 'writeQuaternion':
      bs.writeQuaternion(op.x!, op.y!, op.z!, op.w!);
      break;
    case 'writeAlignedBytes':
      bs.writeAlignedBytes(hexToBytes(op.dataHex!));
      break;
    case 'writeChar':
      bs.writeChar(op.value as string);
      break;
    default:
      throw new Error(`Unknown write op: ${op.op}`);
  }
}

// ── BitStream read executor ──

interface ReadOp {
  op: string;
  count?: number;
}

function execRead(bs: BitStream, op: ReadOp): unknown {
  switch (op.op) {
    case 'readU8':
      return bs.readU8();
    case 'readU16BE':
      return bs.readU16BE();
    case 'readI16BE':
      return bs.readI16BE();
    case 'readU32BE':
      return bs.readU32BE();
    case 'readI32BE':
      return bs.readI32BE();
    case 'readFloatBE':
      return bs.readFloatBE();
    case 'readDoubleBE':
      return bs.readDoubleBE();
    case 'readBool':
      return bs.readBool();
    case 'readBit':
      return bs.readBit();
    case 'readBits':
      return bs.readBits(op.count!);
    case 'readBytes':
      return bytesToHex(bs.readBytes(op.count!));
    case 'readCompressedU32':
      return bs.readCompressedU32();
    case 'readVector3': {
      const [x, y, z] = bs.readVector3();
      return { x, y, z };
    }
    case 'readQuaternion': {
      const [x, y, z, w] = bs.readQuaternion();
      return { x, y, z, w };
    }
    case 'readAlignedBytes':
      return bytesToHex(bs.readAlignedBytes(op.count!));
    case 'readChar':
      return bs.readChar();
    default:
      throw new Error(`Unknown read op: ${op.op}`);
  }
}

// ── Category handlers ──

const handlers = new Map<string, CategoryHandler>();

handlers.set('bitstream', (inp) => {
  const bs = new BitStream();
  for (const op of inp['operations'] as WriteOp[]) {
    execWrite(bs, op);
  }
  return { dataHex: bytesToHex(bs.toBytes()), bitLength: bs.bitLength };
});

handlers.set('bitstreamRead', (inp) => {
  const bs = BitStream.fromBytes(hexToBytes(inp['dataHex'] as string), inp['bitLength'] as number);
  const values: unknown[] = [];
  for (const op of inp['operations'] as ReadOp[]) {
    values.push(execRead(bs, op));
  }
  return { values };
});

handlers.set('writeCompressed', (inp) => {
  const bs = new BitStream();
  bs.writeCompressedU32(inp['value'] as number);
  return { dataHex: bytesToHex(bs.toBytes()), bitLength: bs.bitLength };
});

handlers.set('readCompressed', (inp) => {
  const bs = BitStream.fromBytes(hexToBytes(inp['dataHex'] as string), inp['bitLength'] as number);
  return { value: bs.readCompressedU32() };
});

handlers.set('huffman', (inp) => {
  const stringHex = inp['stringHex'] as string;
  if (stringHex === '') {
    return { dataHex: '', bitLength: 0 };
  }
  const data = hexToBytes(stringHex);
  const bits = encodeBytesForWire(data);
  const byteLen = bits.length / 8;
  let val = 0n;
  for (let i = 0; i < bits.length; i++) {
    val = (val << 1n) | (bits[i] === '1' ? 1n : 0n);
  }
  const result = new Uint8Array(byteLen);
  for (let i = byteLen - 1; i >= 0; i--) {
    result[i] = Number(val & 0xffn);
    val >>= 8n;
  }
  return { dataHex: bytesToHex(result), bitLength: bits.length };
});

handlers.set('huffmanDecode', (inp) => {
  const bitLength = inp['bitLength'] as number;
  if (bitLength === 0) {
    return { stringHex: '' };
  }
  const data = hexToBytes(inp['dataHex'] as string);
  let bitStr = '';
  for (let i = 0; i < data.length; i++) {
    bitStr += data[i]!.toString(2).padStart(8, '0');
  }
  bitStr = bitStr.slice(0, bitLength);
  const decoded = decodeString(bitStr);
  return { stringHex: bytesToHex(decoded) };
});

handlers.set('addressEncode', (inp) => {
  const result = encodeAddress(inp['ip'] as string, inp['port'] as number);
  return { dataHex: bytesToHex(result) };
});

handlers.set('addressDecode', (inp) => {
  const data = hexToBytes(inp['dataHex'] as string);
  const { ip, port } = decodeAddress(data);
  return { ip, port };
});

// ── Main ──

async function main() {
  const chunks: Buffer[] = [];
  for await (const chunk of process.stdin) {
    chunks.push(chunk as Buffer);
  }
  const raw = Buffer.concat(chunks).toString('utf-8').trim();

  let testCases: TestCase[];
  if (raw.startsWith('[')) {
    testCases = JSON.parse(raw) as TestCase[];
  } else {
    testCases = raw
      .split('\n')
      .filter((line) => line.trim())
      .map((line) => JSON.parse(line) as TestCase);
  }

  const results: TestCase[] = [];
  for (const tc of testCases) {
    const category = tc.testInfo.category;
    const handler = handlers.get(category);
    if (!handler) {
      console.error(`No handler for category: ${category}`);
      process.exit(2);
    }
    try {
      const output = handler(tc.input);
      results.push({ ...tc, output });
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      console.error(`Error processing ${tc.testInfo.category}: ${message}`);
      process.exit(2);
    }
  }

  console.log(JSON.stringify(results, null, 2));
}

void main();
