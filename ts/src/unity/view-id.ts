import type { BitStream } from '../bitstream.js';

export interface ViewId {
  scope: 'scene' | 'allocated';
  id: number;
}

export function viewIdToInt(vid: ViewId): number {
  return vid.scope === 'scene' ? vid.id : 0x100000000 + vid.id;
}

/** Encode a NetworkViewID as 48-bit big-endian bytes. */
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
  const hi = bs.readBits(16);
  const mid = bs.readBits(16);
  const lo = bs.readBits(16);
  return hi * 0x100000000 + mid * 0x10000 + lo;
}

export function encodeViewId16(scope: 'scene' | 'allocated', id: number): number {
  if (scope === 'scene') {
    if (id < 0 || id > 4095) {
      throw new Error(`scene ViewID out of range: ${id} (must be 0-4095)`);
    }
    return id << 2;
  }
  if (id < 0 || id > 255) {
    throw new Error(`allocated ViewID out of range: ${id} (must be 0-255)`);
  }
  return 0x4000 | (id << 6);
}

export function decodeViewId16(val16: number): ViewId {
  if (val16 & 0x4000) {
    return { scope: 'allocated', id: (val16 & 0x3fff) >> 6 };
  }
  return { scope: 'scene', id: val16 >> 2 };
}

/**
 * Encode a 16-bit RPC routing constant from a ViewId.
 *
 * This is the value Unity uses to route incoming RPCs to the correct
 * NetworkView. It uses a different bit layout than encodeViewId16
 * (the RPC parameter format).
 *
 * - Internal:  0x0000
 * - Scene:     sceneViewIndex << 1        (bit 13 = 0)
 * - Allocated: 0x2000 | (allocatedID << 5) (bit 13 = 1)
 */
export function rpcViewConstant(scope: 'scene' | 'allocated', id: number): number {
  if (scope === 'scene') {
    if (id < 0 || id > 4095) {
      throw new Error(`scene ViewID out of range: ${id} (must be 0-4095)`);
    }
    return id << 1;
  }
  if (id < 0 || id > 255) {
    throw new Error(`allocated ViewID out of range: ${id} (must be 0-255)`);
  }
  return 0x2000 | (id << 5);
}

/** Encode a routing constant from a ViewId struct. */
export function rpcViewConstantFromVid(vid: ViewId): number {
  return rpcViewConstant(vid.scope, vid.id);
}

/** Decode a 16-bit RPC routing constant back to a ViewId. */
export function decodeRpcViewConstant(constant: number): ViewId | null {
  if (constant === 0) return null;
  if (constant & 0x2000) {
    return { scope: 'allocated', id: (constant & 0x1FFF) >> 5 };
  }
  return { scope: 'scene', id: constant >> 1 };
}
