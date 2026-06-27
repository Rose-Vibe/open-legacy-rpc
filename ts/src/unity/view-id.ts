import type { BitStream } from '../bitstream.js';

export interface ViewId {
  scope: 'scene' | 'allocated';
  id: number;
}

export function viewIdToInt(vid: ViewId): number {
  return vid.scope === 'scene' ? vid.id : 0x100000000 + vid.id;
}

export function encodeViewId(viewId: number): Uint8Array {
  const hi = Math.floor(viewId / 0x100000000) & 0xffff;
  const lo = viewId & 0xffffffff;
  const buf = new Uint8Array(6);
  buf[0] = (hi >>> 8) & 0xff;
  buf[1] = hi & 0xff;
  buf[2] = (lo >>> 24) & 0xff;
  buf[3] = (lo >>> 16) & 0xff;
  buf[4] = (lo >>> 8) & 0xff;
  buf[5] = lo & 0xff;
  return buf;
}

export function encodeViewIdFromVid(vid: ViewId): Uint8Array {
  return encodeViewId(viewIdToInt(vid));
}

export function decodeViewIdBits(bs: BitStream): number {
  return bs.readBits(48);
}

export function encodeViewId16(scope: 'scene' | 'allocated', id: number): number {
  if (scope === 'scene') {
    return id << 2;
  }
  return 0x4000 | (id << 6);
}

export function decodeViewId16(val16: number): ViewId {
  if (val16 & 0x4000) {
    return { scope: 'allocated', id: (val16 & 0x3fff) >> 6 };
  }
  return { scope: 'scene', id: val16 >> 2 };
}
