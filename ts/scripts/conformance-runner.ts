import * as process from 'node:process';
import { BitStream } from '../src/bitstream.js';
import { decodeString, encodeBytesForWire } from '../src/huffman.js';
import { encodeAddress, decodeAddress } from '../src/raknet/address.js';
import { computeMethodId, computeMethodIndex } from '../src/unity/method-hash.js';
import { encodeViewId, encodeViewId16 } from '../src/unity/view-id.js';
import {
  encodeRpcSubsequent,
  encodeRpcFirstUse,
  decodeRpc,
  RPC_MODE_FROM_NAME,
} from '../src/unity/rpc.js';
import type { RpcParam } from '../src/unity/rpc.js';
import {
  encodeStateSync,
  decodeStateSync,
  encodeDeltaStateSync,
  decodeDeltaStateSync,
} from '../src/unity/state-sync.js';
import type { StateSyncField } from '../src/unity/state-sync.js';
import {
  encodeUpdateRow,
  decodeUpdateRow,
  encodeQueryRequest,
  decodeQueryRequest,
  encodeQueryReply,
  decodeQueryReply,
  encodeRemoveRow,
  decodeRemoveRow,
  NUMERIC,
  STRING,
  BINARY,
} from '../src/master/serialization.js';
import type { Cell, Filter, Column, Row } from '../src/master/serialization.js';

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

// ── Unity protocol handlers ──

interface RpcParamInput {
  type: string;
  value: unknown;
}

interface ViewIdInput {
  scope: 'scene' | 'allocated';
  id: number;
}

function inputToRpcParams(inp: Record<string, unknown>): RpcParam[] {
  const rawParams = inp['params'] as RpcParamInput[];
  return rawParams.map((p) => {
    if (p.type === 'bytes') {
      return { type: 'bytes' as const, value: hexToBytes(p.value as string) };
    }
    if (p.type === 'Vector3' || p.type === 'Quaternion') {
      return { type: p.type, value: p.value as number[] };
    }
    return { type: p.type as RpcParam['type'], value: p.value as number | string };
  });
}

function viewIdInt(vid: ViewIdInput): number {
  return vid.scope === 'scene' ? vid.id : 0x100000000 + vid.id;
}

handlers.set('rpcEncode', (inp) => {
  const params = inputToRpcParams(inp);
  const mode = RPC_MODE_FROM_NAME[inp['rpcMode'] as string];
  if (mode === undefined) throw new Error(`Unknown RPC mode: ${inp['rpcMode'] as string}`);
  const vid = inp['viewId'] as ViewIdInput;
  const { data, bitLength } = encodeRpcSubsequent({
    methodName: inp['methodName'] as string,
    params,
    viewId: viewIdInt(vid),
    rpcCounter: inp['rpcCounter'] as number,
    mode,
  });
  return { dataHex: bytesToHex(data), bitLength };
});

handlers.set('rpcDecode', (inp) => {
  const d = decodeRpc(hexToBytes(inp['dataHex'] as string), inp['bitLength'] as number);
  return {
    methodName: d.methodName,
    rpcCounter: d.rpcCounter,
    rpcMode: d.rpcMode,
  };
});

handlers.set('rpcFirstUse', (inp) => {
  const params = inputToRpcParams(inp);
  const mode = RPC_MODE_FROM_NAME[inp['rpcMode'] as string];
  if (mode === undefined) throw new Error(`Unknown RPC mode: ${inp['rpcMode'] as string}`);
  const vid = inp['viewId'] as ViewIdInput;
  const { data, bitLength } = encodeRpcFirstUse({
    methodName: inp['methodName'] as string,
    params,
    viewId: viewIdInt(vid),
    rpcCounter: inp['rpcCounter'] as number,
    mode,
  });
  return { dataHex: bytesToHex(data), bitLength };
});

handlers.set('rpcFirstUseDecode', (inp) => {
  const d = decodeRpc(hexToBytes(inp['dataHex'] as string), inp['bitLength'] as number);
  return {
    methodName: d.methodName,
    rpcMode: d.rpcMode,
  };
});

handlers.set('methodHash', (inp) => {
  const { classGuid, methodHash } = computeMethodId(inp['methodName'] as string);
  return { classGuidHex: bytesToHex(classGuid), methodHashHex: bytesToHex(methodHash) };
});

handlers.set('methodIndex', (inp) => {
  const idx = computeMethodIndex(inp['methodRid'] as number, inp['interfaceMethodCount'] as number);
  return { methodIndex: idx };
});

handlers.set('viewId', (inp) => {
  const scope = inp['scope'] as string;
  const id = inp['id'] as number;
  const vid = scope === 'scene' ? id : 0x100000000 + id;
  return { dataHex: bytesToHex(encodeViewId(vid)) };
});

handlers.set('viewIdParam', (inp) => {
  return { value16: encodeViewId16(inp['scope'] as 'scene' | 'allocated', inp['id'] as number) };
});

handlers.set('stateSync', (inp) => {
  const vid = inp['viewId'] as ViewIdInput;
  const fields = inp['fields'] as StateSyncField[];
  const { data, bitLength } = encodeStateSync({
    viewId: vid,
    timestamp: inp['timestamp'] as number,
    fields,
    isFirst: inp['isFirst'] as boolean,
  });
  return { dataHex: bytesToHex(data), bitLength };
});

handlers.set('stateSyncDecode', (inp) => {
  const d = decodeStateSync(hexToBytes(inp['dataHex'] as string), inp['bitLength'] as number);
  return {
    timestamp: d.timestamp,
    isFirst: d.isFirst,
    viewIdScope: d.viewIdScope,
    viewId: d.viewId,
  };
});

handlers.set('deltaStateSync', (inp) => {
  const vid = inp['viewId'] as ViewIdInput;
  const { data, bitLength } = encodeDeltaStateSync({
    viewId: vid,
    timestamp: inp['timestamp'] as number,
    fieldValues: inp['fieldValues'] as number[],
    prevValues: inp['prevValues'] as number[],
    fieldWidths: inp['fieldWidths'] as number[],
    isFirst: inp['isFirst'] as boolean,
  });
  return { dataHex: bytesToHex(data), bitLength };
});

handlers.set('deltaSyncDecode', (inp) => {
  const d = decodeDeltaStateSync(
    hexToBytes(inp['dataHex'] as string),
    inp['bitLength'] as number,
    inp['fieldCount'] as number,
    inp['fieldWidths'] as number[],
    inp['prevValues'] as number[],
  );
  return {
    timestamp: d.timestamp,
    isFirst: d.isFirst,
    dirtyFlags: d.dirtyFlags,
    fieldValues: d.fieldValues,
  };
});

// ── Master protocol helpers ──

const TYPE_INT: Record<string, number> = { NUMERIC, STRING, BINARY };
const TYPE_STR: Record<number, string> = { [NUMERIC]: 'NUMERIC', [STRING]: 'STRING', [BINARY]: 'BINARY' };
const OP_INT: Record<string, number> = {
  EQUAL: 0, NOT_EQUAL: 1, GREATER_THAN: 2, GREATER_THAN_EQ: 3,
  LESS_THAN: 4, LESS_THAN_EQ: 5, IS_EMPTY: 6, NOT_EMPTY: 7,
};
const OP_STR: Record<number, string> = Object.fromEntries(
  Object.entries(OP_INT).map(([k, v]) => [v, k]),
);

interface CellInput { name: string; type: string; value: number | string | null }
interface FilterInput { name: string; type: string; operation: string; value: number | string | null }
interface ColumnInput { name: string; type: string }
interface RowInput { key: number; cells: Record<string, number | string | null> }

function cellsToInternal(cells: CellInput[]): Cell[] {
  return cells.map((c) => {
    let val: number | string | Uint8Array | null = c.value;
    if (c.type === 'BINARY' && typeof val === 'string') val = hexToBytes(val);
    return { name: c.name, type: TYPE_INT[c.type]!, value: val };
  });
}

function filtersToInternal(filters: FilterInput[]): Filter[] {
  return filters.map((f) => {
    let val: number | string | Uint8Array | null = f.value;
    if (f.type === 'BINARY' && typeof val === 'string') val = hexToBytes(val);
    return { name: f.name, type: TYPE_INT[f.type]!, operation: OP_INT[f.operation]!, value: val };
  });
}

function rowsToInternal(rows: RowInput[], columns: ColumnInput[]): Row[] {
  return rows.map((row) => {
    const cells: Record<string, number | string | Uint8Array | null> = {};
    for (const col of columns) {
      if (col.name in row.cells) {
        let val: number | string | Uint8Array | null = row.cells[col.name] ?? null;
        if (col.type === 'BINARY' && typeof val === 'string') val = hexToBytes(val);
        cells[col.name] = val;
      }
    }
    return { key: row.key, cells };
  });
}

// ── Master protocol handlers ──

handlers.set('updateRow', (inp) => {
  const cells = cellsToInternal(inp['cells'] as CellInput[]);
  const data = encodeUpdateRow(
    inp['tableName'] as string, cells,
    inp['updateMode'] as number,
    (inp['rowId'] as number | null) ?? null,
    (inp['password'] as string | null) ?? null,
  );
  return { dataHex: bytesToHex(data) };
});

handlers.set('updateRowDecode', (inp) => {
  const d = decodeUpdateRow(hexToBytes(inp['dataHex'] as string));
  const cells = d.cells.map((c) => ({
    name: c.name,
    type: TYPE_STR[c.type]!,
    value: c.value instanceof Uint8Array ? bytesToHex(c.value) : c.value,
  }));
  return { tableName: d.table, updateMode: d.updateMode, rowId: d.rowId, cells };
});

handlers.set('queryRequest', (inp) => {
  const filters = filtersToInternal((inp['filters'] as FilterInput[]) ?? []);
  const colSubset = (inp['columnSubset'] as string[]) ?? [];
  const rowIds = (inp['rowIds'] as number[]) ?? [];
  const data = encodeQueryRequest(
    inp['tableName'] as string,
    colSubset.length > 0 ? colSubset : null,
    filters.length > 0 ? filters : null,
    rowIds.length > 0 ? rowIds : null,
    (inp['password'] as string | null) ?? null,
  );
  return { dataHex: bytesToHex(data) };
});

handlers.set('queryRequestDecode', (inp) => {
  const d = decodeQueryRequest(hexToBytes(inp['dataHex'] as string));
  const filters = d.filters.map((f) => ({
    name: f.name,
    type: TYPE_STR[f.type] ?? String(f.type),
    operation: OP_STR[f.operation] ?? String(f.operation),
    value: f.value instanceof Uint8Array ? bytesToHex(f.value) : f.value,
  }));
  return { tableName: d.table, columnSubset: d.columnSubset, filters, rowIds: d.rowIds };
});

handlers.set('queryReply', (inp) => {
  const colInputs = inp['columns'] as ColumnInput[];
  const columns: Column[] = colInputs.map((c) => ({ name: c.name, type: TYPE_INT[c.type]! }));
  const rows = rowsToInternal(inp['rows'] as RowInput[], colInputs);
  const data = encodeQueryReply(columns, rows);
  return { dataHex: bytesToHex(data) };
});

handlers.set('queryReplyDecode', (inp) => {
  const d = decodeQueryReply(hexToBytes(inp['dataHex'] as string));
  const columns = d.columns.map((c) => ({ name: c.name, type: TYPE_STR[c.type]! }));
  const rows = d.rows.map((row) => {
    const cells: Record<string, number | string | null> = {};
    for (const [k, v] of Object.entries(row.cells)) {
      cells[k] = v instanceof Uint8Array ? bytesToHex(v) : v;
    }
    return { key: row.key, cells };
  });
  return { columns, rows };
});

handlers.set('removeRow', (inp) => {
  const data = encodeRemoveRow(
    inp['tableName'] as string,
    inp['rowId'] as number,
    (inp['password'] as string | null) ?? null,
  );
  return { dataHex: bytesToHex(data) };
});

handlers.set('removeRowDecode', (inp) => {
  const d = decodeRemoveRow(hexToBytes(inp['dataHex'] as string));
  return { tableName: d.table, rowId: d.rowId };
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
