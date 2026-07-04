import type { Frame, ParsedPacket } from './types.js';
import type { Reliability } from './types.js';
import { OFFLINE_MAGIC, isReliable, isOrdered } from './types.js';

function encodeU24LE(val: number): Uint8Array {
  return new Uint8Array([val & 0xff, (val >>> 8) & 0xff, (val >>> 16) & 0xff]);
}

function decodeU24LE(data: Uint8Array, offset: number): number {
  return (
    ((data[offset] ?? 0) | ((data[offset + 1] ?? 0) << 8) | ((data[offset + 2] ?? 0) << 16)) >>> 0
  );
}

function readU16BE(data: Uint8Array, offset: number): number {
  return (((data[offset] ?? 0) << 8) | (data[offset + 1] ?? 0)) & 0xffff;
}

function readU32BE(data: Uint8Array, offset: number): number {
  return (
    ((((data[offset] ?? 0) << 24) |
      ((data[offset + 1] ?? 0) << 16) |
      ((data[offset + 2] ?? 0) << 8) |
      (data[offset + 3] ?? 0)) >>>
      0) &
    0xffffffff
  );
}

function writeU16BE(val: number): Uint8Array {
  return new Uint8Array([(val >>> 8) & 0xff, val & 0xff]);
}

function writeU32BE(val: number): Uint8Array {
  return new Uint8Array([(val >>> 24) & 0xff, (val >>> 16) & 0xff, (val >>> 8) & 0xff, val & 0xff]);
}

function arraysEqual(a: Uint8Array, b: Uint8Array, aOff: number, len: number): boolean {
  for (let i = 0; i < len; i++) {
    if ((a[aOff + i] ?? 0) !== (b[i] ?? 0)) return false;
  }
  return true;
}

function isOfflineMessage(data: Uint8Array): boolean {
  if (data.length < 1) return false;
  const first = data[0] ?? 0;
  if ([0x00, 0x01, 0x02, 0x05, 0x06, 0x07, 0x08].includes(first)) {
    if (data.length <= 28) return true;
  }
  for (const offset of [1, 5, 9, 10, 25]) {
    const end = offset + 16;
    if (end <= data.length && arraysEqual(data, OFFLINE_MAGIC, offset, 16)) {
      return true;
    }
  }
  return false;
}

function parseAckRanges(data: Uint8Array, offset: number): Array<[number, number]> {
  if (offset + 2 > data.length) return [];
  const count = readU16BE(data, offset);
  let pos = offset + 2;
  const ranges: Array<[number, number]> = [];
  for (let i = 0; i < count; i++) {
    if (pos >= data.length) break;
    const maxEqMin = data[pos] ?? 0;
    pos += 1;
    if (pos + 3 > data.length) break;
    const minVal = decodeU24LE(data, pos);
    pos += 3;
    if (maxEqMin) {
      ranges.push([minVal, minVal]);
    } else {
      if (pos + 3 > data.length) break;
      const maxVal = decodeU24LE(data, pos);
      pos += 3;
      ranges.push([minVal, maxVal]);
    }
  }
  return ranges;
}

function parseFrames(data: Uint8Array, offset: number): Frame[] {
  const frames: Frame[] = [];
  let pos = offset;
  while (pos < data.length - 2) {
    const headerByte = data[pos] ?? 0;
    const reliability: Reliability = (headerByte >>> 5) & 0x07;
    const hasSplit = ((headerByte >>> 4) & 0x01) === 1;
    pos += 1;

    if (pos + 2 > data.length) break;
    const bitLength = readU16BE(data, pos);
    const byteLength = (bitLength + 7) >>> 3;
    pos += 2;

    let reliableMsgNumber: number | null = null;
    if (isReliable(reliability)) {
      if (pos + 3 > data.length) break;
      reliableMsgNumber = decodeU24LE(data, pos);
      pos += 3;
    }

    let orderingIndex: number | null = null;
    let orderingChannel = 0;
    if (isOrdered(reliability)) {
      if (pos + 4 > data.length) break;
      orderingIndex = decodeU24LE(data, pos);
      pos += 3;
      orderingChannel = data[pos] ?? 0;
      pos += 1;
    }

    let splitPacketCount: number | null = null;
    let splitPacketId: number | null = null;
    let splitPacketIndex: number | null = null;
    if (hasSplit) {
      if (pos + 10 > data.length) break;
      splitPacketCount = readU32BE(data, pos);
      pos += 4;
      splitPacketId = readU16BE(data, pos);
      pos += 2;
      splitPacketIndex = readU32BE(data, pos);
      pos += 4;
    }

    const end = pos + byteLength;
    const payload = data.slice(pos, Math.min(end, data.length));
    let actualBitLength = bitLength;
    if (payload.length < byteLength) {
      console.warn(`RakNet decode: frame bitLength exceeds payload (${bitLength} bits > ${payload.length * 8} available), clamping`);
      actualBitLength = payload.length * 8;
    }
    pos = end;

    frames.push({
      reliability,
      bitLength: actualBitLength,
      reliableMsgNumber,
      orderingIndex,
      orderingChannel,
      splitPacketCount,
      splitPacketId,
      splitPacketIndex,
      payload,
    });
  }
  return frames;
}

export function parsePacket(data: Uint8Array): ParsedPacket {
  if (data.length < 4) {
    return { type: 'unknown', data };
  }

  if (isOfflineMessage(data)) {
    return { type: 'offline', messageId: data[0] ?? 0, data };
  }

  const first = data[0] ?? 0;

  if (data.length < 9) {
    return { type: 'unknown', data };
  }

  const timestamp = readU32BE(data, 5);

  const isAck = (first & 0xc0) === 0xc0;
  const isNak = (first & 0xa0) === 0xa0 && !isAck;

  if (isAck || isNak) {
    const ranges = parseAckRanges(data, 9);
    return { type: isAck ? 'ack' : 'nak', timestamp, ranges };
  }

  if (data.length < 12) {
    return { type: 'unknown', data };
  }

  const sequenceNumber = decodeU24LE(data, 9);
  const frames = parseFrames(data, 12);

  return { type: 'data', timestamp, sequenceNumber, frames };
}

export function buildFrame(frame: Frame): Uint8Array {
  const parts: Uint8Array[] = [];
  let headerByte = (frame.reliability << 5) & 0xe0;
  if (frame.splitPacketCount !== null) {
    headerByte |= 0x10;
  }
  parts.push(new Uint8Array([headerByte]));
  parts.push(writeU16BE(frame.bitLength));

  if (isReliable(frame.reliability)) {
    parts.push(encodeU24LE(frame.reliableMsgNumber ?? 0));
  }

  if (isOrdered(frame.reliability)) {
    parts.push(encodeU24LE(frame.orderingIndex ?? 0));
    parts.push(new Uint8Array([frame.orderingChannel]));
  }

  if (frame.splitPacketCount !== null) {
    parts.push(writeU32BE(frame.splitPacketCount));
    parts.push(writeU16BE(frame.splitPacketId ?? 0));
    parts.push(writeU32BE(frame.splitPacketIndex ?? 0));
  }

  parts.push(frame.payload);

  let totalLen = 0;
  for (const p of parts) totalLen += p.length;
  const result = new Uint8Array(totalLen);
  let offset = 0;
  for (const p of parts) {
    result.set(p, offset);
    offset += p.length;
  }
  return result;
}

export function buildDataPacket(
  sequenceNumber: number,
  frames: Frame[],
  timestamp?: number,
): Uint8Array {
  const frameParts: Uint8Array[] = [];
  for (const f of frames) {
    frameParts.push(buildFrame(f));
  }
  let frameLen = 0;
  for (const p of frameParts) frameLen += p.length;

  const header = new Uint8Array(12);
  header[0] = 0x84;
  const ts = timestamp ?? 0;
  header[5] = (ts >>> 24) & 0xff;
  header[6] = (ts >>> 16) & 0xff;
  header[7] = (ts >>> 8) & 0xff;
  header[8] = ts & 0xff;
  const seq = encodeU24LE(sequenceNumber);
  header[9] = seq[0] ?? 0;
  header[10] = seq[1] ?? 0;
  header[11] = seq[2] ?? 0;

  const result = new Uint8Array(12 + frameLen);
  result.set(header, 0);
  let offset = 12;
  for (const p of frameParts) {
    result.set(p, offset);
    offset += p.length;
  }
  return result;
}

export function buildAck(sequenceNumbers: number[], timestamp?: number): Uint8Array {
  const sorted = [...sequenceNumbers].sort((a, b) => a - b);
  const ranges: Array<[number, number]> = [];
  if (sorted.length > 0) {
    let start = sorted[0] ?? 0;
    let end = start;
    for (let i = 1; i < sorted.length; i++) {
      const s = sorted[i] ?? 0;
      if (s === end + 1) {
        end = s;
      } else {
        ranges.push([start, end]);
        start = end = s;
      }
    }
    ranges.push([start, end]);
  }

  const parts: Uint8Array[] = [];
  const header = new Uint8Array(9);
  header[0] = 0xc0;
  const ts = timestamp ?? 0;
  header[5] = (ts >>> 24) & 0xff;
  header[6] = (ts >>> 16) & 0xff;
  header[7] = (ts >>> 8) & 0xff;
  header[8] = ts & 0xff;
  parts.push(header);

  parts.push(writeU16BE(ranges.length));
  for (const [min, max] of ranges) {
    if (min === max) {
      parts.push(new Uint8Array([1]));
      parts.push(encodeU24LE(min));
    } else {
      parts.push(new Uint8Array([0]));
      parts.push(encodeU24LE(min));
      parts.push(encodeU24LE(max));
    }
  }

  let totalLen = 0;
  for (const p of parts) totalLen += p.length;
  const result = new Uint8Array(totalLen);
  let offset = 0;
  for (const p of parts) {
    result.set(p, offset);
    offset += p.length;
  }
  return result;
}
