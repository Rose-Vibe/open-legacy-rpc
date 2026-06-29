import { BitStream } from '../bitstream.js';
import { encodeViewId16, decodeViewId16 } from './view-id.js';
import type { ViewId } from './view-id.js';

const MSG_ID_RPC = 0x1b;

export interface StateSyncField {
  type: 'int' | 'float' | 'bool' | 'short' | 'char' | 'Vector3' | 'Quaternion';
  value: number | boolean | number[];
}

export interface StateSyncOptions {
  viewId: ViewId;
  timestampMs: number;
  fields: StateSyncField[];
  isFirst: boolean;
}

export interface StateSyncResult {
  data: Uint8Array;
  bitLength: number;
}

export function encodeStateSync(opts: StateSyncOptions): StateSyncResult {
  const dataBs = buildDataBs(opts.fields);

  const bs = new BitStream();
  bs.writeU8(MSG_ID_RPC);
  bs.writeU32BE((opts.timestampMs / 0x100000000) >>> 0);
  bs.writeU32BE(opts.timestampMs >>> 0);
  bs.writeU8(opts.isFirst ? 0x80 : 0x7f);
  bs.writeU16BE(encodeViewId16(opts.viewId.scope, opts.viewId.id));

  const dataBits = dataBs.bitLength;
  dataBs.pos = 0;
  for (let i = 0; i < dataBits; i++) {
    bs.writeBit(dataBs.readBit());
  }

  return { data: bs.toBytes(), bitLength: 96 + dataBits };
}

export interface DecodedStateSync {
  timestampMs: number;
  isFirst: boolean;
  viewIdScope: 'scene' | 'allocated';
  viewId: number;
}

export function decodeStateSync(payload: Uint8Array, bitLength: number): DecodedStateSync {
  const bs = new BitStream(payload, bitLength);
  bs.readU8(); // msg_id
  const tsHi = bs.readU32BE();
  const tsLo = bs.readU32BE();
  const timestampMs = tsHi * 0x100000000 + tsLo;
  const flags = bs.readU8();
  const isFirst = flags === 0x80;
  const vid16 = bs.readU16BE();
  const vid = decodeViewId16(vid16);

  return {
    timestampMs,
    isFirst,
    viewIdScope: vid.scope,
    viewId: vid.id,
  };
}

export interface DeltaSyncOptions {
  viewId: ViewId;
  timestampMs: number;
  fieldValues: number[];
  prevValues: number[];
  fieldWidths: number[];
  isFirst: boolean;
}

export function encodeDeltaStateSync(opts: DeltaSyncOptions): StateSyncResult {
  const bs = new BitStream();
  bs.writeU8(MSG_ID_RPC);
  bs.writeU32BE((opts.timestampMs / 0x100000000) >>> 0);
  bs.writeU32BE(opts.timestampMs >>> 0);
  bs.writeU8(opts.isFirst ? 0x80 : 0x7f);
  bs.writeU16BE(encodeViewId16(opts.viewId.scope, opts.viewId.id));

  let dataBits = 0;
  for (let i = 0; i < opts.fieldValues.length; i++) {
    const cur = opts.fieldValues[i] ?? 0;
    const prev = opts.prevValues[i] ?? 0;
    const width = opts.fieldWidths[i] ?? 32;
    const dirty = cur !== prev;
    bs.writeBit(dirty ? 1 : 0);
    dataBits += 1;
    if (dirty) {
      const mask = width >= 32 ? 0xffffffff : (1 << width) - 1;
      bs.writeBits(cur & mask, width);
      dataBits += width;
    }
  }

  return { data: bs.toBytes(), bitLength: 96 + dataBits };
}

export interface DecodedDeltaSync {
  timestampMs: number;
  isFirst: boolean;
  dirtyFlags: number[];
  fieldValues: number[];
}

export function decodeDeltaStateSync(
  payload: Uint8Array,
  bitLength: number,
  fieldCount: number,
  fieldWidths: number[],
  prevValues: number[],
): DecodedDeltaSync {
  const bs = new BitStream(payload, bitLength);
  bs.readU8(); // msg_id
  const tsHi = bs.readU32BE();
  const tsLo = bs.readU32BE();
  const timestampMs = tsHi * 0x100000000 + tsLo;
  const flags = bs.readU8();
  const isFirst = flags === 0x80;
  bs.readU16BE(); // viewId16

  const values = [...prevValues];
  const dirtyFlags: number[] = [];
  for (let i = 0; i < fieldCount; i++) {
    const dirty = bs.readBit();
    dirtyFlags.push(dirty);
    if (dirty) {
      values[i] = bs.readBits(fieldWidths[i] ?? 32);
    }
  }

  return { timestampMs, isFirst, dirtyFlags, fieldValues: values };
}

function buildDataBs(fields: StateSyncField[]): BitStream {
  const bs = new BitStream();
  for (const f of fields) {
    if (f.type === 'int') {
      let v = f.value as number;
      if (v < 0) v += 0x100000000;
      bs.writeBits(v & 0xffffffff, 32);
    } else if (f.type === 'float') {
      bs.writeFloatBE(f.value as number);
    } else if (f.type === 'bool') {
      bs.writeBit(f.value ? 1 : 0);
    } else if (f.type === 'short') {
      bs.writeBits((f.value as number) & 0xffff, 16);
    } else if (f.type === 'char') {
      bs.writeBits((f.value as number) & 0xff, 8);
    } else if (f.type === 'Vector3') {
      const v = f.value as number[];
      bs.writeFloatBE(v[0] ?? 0);
      bs.writeFloatBE(v[1] ?? 0);
      bs.writeFloatBE(v[2] ?? 0);
    } else {
      // Quaternion
      const q = f.value as number[];
      bs.writeFloatBE(q[0] ?? 0);
      bs.writeFloatBE(q[1] ?? 0);
      bs.writeFloatBE(q[2] ?? 0);
      bs.writeFloatBE(q[3] ?? 0);
    }
  }
  return bs;
}
