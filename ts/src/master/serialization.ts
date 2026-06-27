import { BitStream } from '../bitstream.js';
import { getTree, encodeStringForWire } from '../huffman.js';

// Column types (DS_Table.h ColumnType enum)
export const NUMERIC = 0;
export const STRING = 1;
export const BINARY = 2;
export const POINTER = 3;

// Message IDs
export const ID_DATABASE_QUERY_REQUEST = 75;
export const ID_DATABASE_UPDATE_ROW = 76;
export const ID_DATABASE_REMOVE_ROW = 77;
export const ID_DATABASE_QUERY_REPLY = 78;
export const ID_DATABASE_UNKNOWN_TABLE = 79;
export const ID_DATABASE_INCORRECT_PASSWORD = 80;
export const ID_DATABASE_ROWID = 200;
export const ID_MASTERSERVER_REDIRECT = 201;
export const ID_MASTERSERVER_MSG = 202;

// Update modes
export const RUM_UPDATE_EXISTING_ROW = 0;
export const RUM_UPDATE_OR_ADD_ROW = 1;
export const RUM_ADD_NEW_ROW = 2;

// Filter operations
export const QF_EQUAL = 0;
export const QF_NOT_EQUAL = 1;
export const QF_GREATER_THAN = 2;
export const QF_GREATER_THAN_EQ = 3;
export const QF_LESS_THAN = 4;
export const QF_LESS_THAN_EQ = 5;
export const QF_IS_EMPTY = 6;
export const QF_NOT_EMPTY = 7;

export const VERSION = new Uint8Array([2, 0, 0]);

export interface Cell {
  name: string;
  type: number;
  value: number | string | Uint8Array | null;
}

export interface Filter {
  name: string;
  type: number;
  operation: number;
  value: number | string | Uint8Array | null;
}

export interface Column {
  name: string;
  type: number;
}

export interface Row {
  key: number;
  cells: Record<string, number | string | Uint8Array | null>;
}

export interface UpdateRowMessage {
  version: Uint8Array;
  table: string;
  password: string | null;
  updateMode: number;
  rowId: number | null;
  cells: Cell[];
}

export interface QueryRequestMessage {
  version: Uint8Array;
  table: string;
  password: string | null;
  columnSubset: string[];
  filters: Filter[];
  rowIds: number[];
}

export interface RemoveRowMessage {
  table: string;
  password: string | null;
  rowId: number;
}

export interface QueryReplyMessage {
  columns: Column[];
  rows: Row[];
}

const tree = getTree();

function readHuffmanString(bs: BitStream): string {
  const bitLength = bs.readCompressedU32();
  if (bitLength === 0) return '';
  const endPos = bs.pos + bitLength;
  const chars: string[] = [];
  let node = tree;
  for (let i = 0; i < bitLength; i++) {
    if (bs.remaining <= 0) break;
    const bit = bs.readBit();
    const next = bit ? node.right : node.left;
    if (!next) break;
    node = next;
    if (node.left === null && node.right === null && node.char !== null) {
      chars.push(String.fromCharCode(node.char));
      node = tree;
    }
  }
  bs.pos = endPos;
  return chars.join('');
}

function writeHuffmanString(bs: BitStream, s: string | null): void {
  if (s === null || s.length === 0) {
    bs.writeCompressedU32(0);
    return;
  }
  const paddedBits = encodeStringForWire(s);
  bs.writeCompressedU32(paddedBits.length);
  for (let i = 0; i < paddedBits.length; i++) {
    bs.writeBit(paddedBits[i] === '1' ? 1 : 0);
  }
}

function readCell(bs: BitStream, colType: number): number | string | Uint8Array | null {
  const isEmpty = bs.readBool();
  if (isEmpty) return null;
  if (colType === NUMERIC) return bs.readDoubleBE();
  if (colType === STRING) return readHuffmanString(bs);
  if (colType === BINARY) {
    const length = bs.readU32BE();
    return bs.readAlignedBytes(length);
  }
  if (colType === POINTER) {
    const hi = bs.readBits(32);
    const lo = bs.readBits(32);
    return hi * 0x100000000 + lo;
  }
  return null;
}

function writeCell(bs: BitStream, value: number | string | Uint8Array | null, colType: number): void {
  if (value === null) {
    bs.writeBool(true);
    return;
  }
  bs.writeBool(false);
  if (colType === NUMERIC) {
    bs.writeDoubleBE(value as number);
  } else if (colType === STRING) {
    writeHuffmanString(bs, value as string);
  } else if (colType === BINARY) {
    const data = value as Uint8Array;
    bs.writeU32BE(data.length);
    bs.writeAlignedBytes(data);
  } else if (colType === POINTER) {
    const v = value as number;
    const hi = Math.floor(v / 0x100000000) >>> 0;
    const lo = v >>> 0;
    bs.writeBits(hi, 32);
    bs.writeBits(lo, 32);
  }
}

function readClientHeader(bs: BitStream): { version: Uint8Array; table: string; password: string | null } {
  const version = bs.readBytes(3);
  const table = readHuffmanString(bs);
  const hasPassword = bs.readBool();
  const password = hasPassword ? readHuffmanString(bs) : null;
  return { version, table, password };
}

function writeClientHeader(bs: BitStream, table: string, password?: string | null): void {
  bs.writeBytes(VERSION);
  writeHuffmanString(bs, table);
  if (password) {
    bs.writeBool(true);
    writeHuffmanString(bs, password);
  } else {
    bs.writeBool(false);
  }
}

export function decodeUpdateRow(payload: Uint8Array): UpdateRowMessage {
  const bs = new BitStream(payload);
  const msgId = bs.readU8();
  if (msgId !== ID_DATABASE_UPDATE_ROW) throw new Error('Expected UpdateRow (' + String(ID_DATABASE_UPDATE_ROW) + '), got ' + String(msgId));
  const { version, table, password } = readClientHeader(bs);

  const updateMode = bs.readU8();
  const hasRowId = bs.readBool();
  const rowId = hasRowId ? bs.readU32BE() : null;
  const numUpdates = bs.readU8();

  const cells: Cell[] = [];
  for (let i = 0; i < numUpdates; i++) {
    const name = readHuffmanString(bs);
    const type = bs.readU8();
    const value = readCell(bs, type);
    cells.push({ name, type, value });
  }

  return { version, table, password, updateMode, rowId, cells };
}

export function encodeUpdateRow(
  table: string,
  cells: Cell[],
  updateMode = RUM_UPDATE_OR_ADD_ROW,
  rowId: number | null = null,
  password: string | null = null,
): Uint8Array {
  const bs = new BitStream();
  bs.writeU8(ID_DATABASE_UPDATE_ROW);
  writeClientHeader(bs, table, password);
  bs.writeU8(updateMode);
  if (rowId !== null) {
    bs.writeBool(true);
    bs.writeU32BE(rowId);
  } else {
    bs.writeBool(false);
  }
  bs.writeU8(cells.length);
  for (const cell of cells) {
    writeHuffmanString(bs, cell.name);
    bs.writeU8(cell.type);
    writeCell(bs, cell.value, cell.type);
  }
  return bs.toBytes();
}

export function decodeQueryRequest(payload: Uint8Array): QueryRequestMessage {
  const bs = new BitStream(payload);
  const msgId = bs.readU8();
  if (msgId !== ID_DATABASE_QUERY_REQUEST) throw new Error('Expected QueryRequest (' + String(ID_DATABASE_QUERY_REQUEST) + '), got ' + String(msgId));
  const { version, table, password } = readClientHeader(bs);

  const numColSubset = bs.readU8();
  const columnSubset: string[] = [];
  for (let i = 0; i < numColSubset; i++) {
    columnSubset.push(readHuffmanString(bs));
  }

  const numFilters = bs.readU8();
  const filters: Filter[] = [];
  for (let i = 0; i < numFilters; i++) {
    const name = readHuffmanString(bs);
    const type = bs.readU8();
    const operation = bs.readU8();
    let value: number | string | Uint8Array | null = null;
    if (operation !== QF_IS_EMPTY && operation !== QF_NOT_EMPTY) {
      value = readCell(bs, type);
    }
    filters.push({ name, type, operation, value });
  }

  const numRowIds = bs.readU8();
  const rowIds: number[] = [];
  for (let i = 0; i < numRowIds; i++) {
    rowIds.push(bs.readU32BE());
  }

  return { version, table, password, columnSubset, filters, rowIds };
}

export function encodeQueryRequest(
  table: string,
  columnSubset: string[] | null = null,
  filters: Filter[] | null = null,
  rowIds: number[] | null = null,
  password: string | null = null,
): Uint8Array {
  const bs = new BitStream();
  bs.writeU8(ID_DATABASE_QUERY_REQUEST);
  writeClientHeader(bs, table, password);

  const cols = columnSubset ?? [];
  bs.writeU8(cols.length);
  for (const col of cols) {
    writeHuffmanString(bs, col);
  }

  const filt = filters ?? [];
  bs.writeU8(filt.length);
  for (const f of filt) {
    writeHuffmanString(bs, f.name);
    bs.writeU8(f.type);
    bs.writeU8(f.operation);
    if (f.operation !== QF_IS_EMPTY && f.operation !== QF_NOT_EMPTY) {
      writeCell(bs, f.value, f.type);
    }
  }

  const rids = rowIds ?? [];
  bs.writeU8(rids.length);
  for (const rid of rids) {
    bs.writeU32BE(rid);
  }

  return bs.toBytes();
}

export function decodeRemoveRow(payload: Uint8Array): RemoveRowMessage {
  const bs = new BitStream(payload);
  const msgId = bs.readU8();
  if (msgId !== ID_DATABASE_REMOVE_ROW) throw new Error('Expected RemoveRow (' + String(ID_DATABASE_REMOVE_ROW) + '), got ' + String(msgId));
  const table = readHuffmanString(bs);
  const hasPassword = bs.readBool();
  const password = hasPassword ? readHuffmanString(bs) : null;
  const rowId = bs.readU32BE();
  return { table, password, rowId };
}

export function encodeRemoveRow(
  table: string,
  rowId: number,
  password: string | null = null,
): Uint8Array {
  const bs = new BitStream();
  bs.writeU8(ID_DATABASE_REMOVE_ROW);
  writeHuffmanString(bs, table);
  if (password) {
    bs.writeBool(true);
    writeHuffmanString(bs, password);
  } else {
    bs.writeBool(false);
  }
  bs.writeU32BE(rowId);
  return bs.toBytes();
}

export function decodeQueryReply(payload: Uint8Array): QueryReplyMessage {
  const bs = new BitStream(payload);
  const msgId = bs.readU8();
  if (msgId !== ID_DATABASE_QUERY_REPLY) throw new Error('Expected QueryReply (' + String(ID_DATABASE_QUERY_REPLY) + '), got ' + String(msgId));

  if (bs.remaining < 32) return { columns: [], rows: [] };

  const numColumns = bs.readU32BE();
  const columns: Column[] = [];
  for (let i = 0; i < numColumns; i++) {
    const name = readHuffmanString(bs);
    const type = bs.readU8();
    columns.push({ name, type });
  }

  const numRows = bs.readU32BE();
  const rows: Row[] = [];
  for (let i = 0; i < numRows; i++) {
    const key = bs.readU32BE();
    const numEntries = bs.readU32BE();
    const cells: Record<string, number | string | Uint8Array | null> = {};
    for (let j = 0; j < numEntries; j++) {
      const cellIdx = bs.readU32BE();
      if (cellIdx >= columns.length) {
        throw new Error(
          `cellIdx ${cellIdx} out of range (have ${columns.length} columns)`,
        );
      }
      const col = columns[cellIdx] as Column;
      cells[col.name] = readCell(bs, col.type);
    }
    rows.push({ key, cells });
  }

  return { columns, rows };
}

export function encodeQueryReply(columns: Column[], rows: Row[]): Uint8Array {
  const bs = new BitStream();
  bs.writeU8(ID_DATABASE_QUERY_REPLY);

  if (columns.length === 0) return bs.toBytes();

  bs.writeU32BE(columns.length);
  for (const col of columns) {
    writeHuffmanString(bs, col.name);
    bs.writeU8(col.type);
  }

  bs.writeU32BE(rows.length);
  for (const row of rows) {
    bs.writeU32BE(row.key);
    const entries: Array<[number, number, number | string | Uint8Array | null]> = [];
    for (let idx = 0; idx < columns.length; idx++) {
      const col = columns[idx] as Column;
      if (col.name in row.cells) {
        entries.push([idx, col.type, row.cells[col.name] ?? null]);
      }
    }
    bs.writeU32BE(entries.length);
    for (const [idx, colType, value] of entries) {
      bs.writeU32BE(idx);
      writeCell(bs, value, colType);
    }
  }

  return bs.toBytes();
}

export function encodeRowId(rowId: number): Uint8Array {
  const bs = new BitStream();
  bs.writeU8(ID_DATABASE_ROWID);
  bs.writeU32BE(rowId);
  return bs.toBytes();
}

export function encodeUnknownTable(): Uint8Array {
  return new Uint8Array([ID_DATABASE_UNKNOWN_TABLE]);
}

export function encodeIncorrectPassword(): Uint8Array {
  return new Uint8Array([ID_DATABASE_INCORRECT_PASSWORD]);
}
