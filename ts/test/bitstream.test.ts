import { describe, it, expect } from 'vitest';
import { BitStream, BitStreamError } from '../src/bitstream.js';

describe('BitStream', () => {
  describe('empty stream', () => {
    it('has zero bitLength', () => {
      const bs = new BitStream();
      expect(bs.bitLength).toBe(0);
    });

    it('toBytes returns empty', () => {
      const bs = new BitStream();
      expect(bs.toBytes()).toEqual(new Uint8Array(0));
    });
  });

  describe('single bit', () => {
    it('writes and reads a 1 bit', () => {
      const bs = new BitStream();
      bs.writeBit(1);
      expect(bs.bitLength).toBe(1);
      expect(bs.toBytes()).toEqual(new Uint8Array([0x80]));

      const reader = BitStream.fromBytes(bs.toBytes(), 1);
      expect(reader.readBit()).toBe(1);
    });

    it('writes and reads a 0 bit', () => {
      const bs = new BitStream();
      bs.writeBit(0);
      expect(bs.bitLength).toBe(1);

      const reader = BitStream.fromBytes(bs.toBytes(), 1);
      expect(reader.readBit()).toBe(0);
    });
  });

  describe('byte alignment', () => {
    it('alignWriteToByte pads to 8-bit boundary', () => {
      const bs = new BitStream();
      bs.writeBit(1);
      bs.writeBit(0);
      bs.writeBit(1);
      bs.alignWriteToByte();
      expect(bs.bitLength).toBe(8);
    });

    it('alignWriteToByte is no-op when already aligned', () => {
      const bs = new BitStream();
      bs.writeU8(0xff);
      bs.alignWriteToByte();
      expect(bs.bitLength).toBe(8);
    });

    it('writeAlignedBytes aligns then writes', () => {
      const bs = new BitStream();
      bs.writeBit(1);
      bs.writeAlignedBytes(new Uint8Array([0xab, 0xcd]));
      expect(bs.bitLength).toBe(24);
      const bytes = bs.toBytes();
      expect(bytes[1]).toBe(0xab);
      expect(bytes[2]).toBe(0xcd);
    });
  });

  describe('buffer growth', () => {
    it('handles writes beyond initial capacity', () => {
      const bs = new BitStream();
      for (let i = 0; i < 100; i++) {
        bs.writeU32BE(i);
      }
      expect(bs.bitLength).toBe(3200);
      const reader = BitStream.fromBytes(bs.toBytes(), 3200);
      for (let i = 0; i < 100; i++) {
        expect(reader.readU32BE()).toBe(i);
      }
    });
  });

  describe('signed integers', () => {
    it('reads negative i32', () => {
      const bs = new BitStream();
      bs.writeI32BE(-1);
      const reader = BitStream.fromBytes(bs.toBytes(), 32);
      expect(reader.readI32BE()).toBe(-1);
    });

    it('reads negative i16', () => {
      const bs = new BitStream();
      bs.writeI16BE(-32768);
      const reader = BitStream.fromBytes(bs.toBytes(), 16);
      expect(reader.readI16BE()).toBe(-32768);
    });
  });

  describe('float roundtrip', () => {
    it('preserves float precision', () => {
      const bs = new BitStream();
      bs.writeFloatBE(3.14);
      const reader = BitStream.fromBytes(bs.toBytes(), 32);
      expect(reader.readFloatBE()).toBeCloseTo(3.14, 5);
    });

    it('preserves double precision', () => {
      const bs = new BitStream();
      bs.writeDoubleBE(3.141592653589793);
      const reader = BitStream.fromBytes(bs.toBytes(), 64);
      expect(reader.readDoubleBE()).toBe(3.141592653589793);
    });
  });

  describe('compressed u32', () => {
    it('handles zero', () => {
      const bs = new BitStream();
      bs.writeCompressedU32(0);
      const reader = BitStream.fromBytes(bs.toBytes(), bs.bitLength);
      expect(reader.readCompressedU32()).toBe(0);
    });

    it('handles max u32', () => {
      const bs = new BitStream();
      bs.writeCompressedU32(0xffffffff);
      const reader = BitStream.fromBytes(bs.toBytes(), bs.bitLength);
      expect(reader.readCompressedU32()).toBe(0xffffffff);
    });

    it('handles small values efficiently', () => {
      const bs = new BitStream();
      bs.writeCompressedU32(0x10000);
      expect(bs.bitLength).toBeLessThan(32);
    });
  });

  describe('vector3 and quaternion', () => {
    it('roundtrips vector3', () => {
      const bs = new BitStream();
      bs.writeVector3(1.5, -2.5, 3.5);
      const reader = BitStream.fromBytes(bs.toBytes(), bs.bitLength);
      const [x, y, z] = reader.readVector3();
      expect(x).toBeCloseTo(1.5);
      expect(y).toBeCloseTo(-2.5);
      expect(z).toBeCloseTo(3.5);
    });

    it('roundtrips quaternion', () => {
      const bs = new BitStream();
      bs.writeQuaternion(0.1, 0.2, 0.3, 0.9);
      const reader = BitStream.fromBytes(bs.toBytes(), bs.bitLength);
      const [x, y, z, w] = reader.readQuaternion();
      expect(x).toBeCloseTo(0.1, 5);
      expect(y).toBeCloseTo(0.2, 5);
      expect(z).toBeCloseTo(0.3, 5);
      expect(w).toBeCloseTo(0.9, 5);
    });
  });

  describe('remaining', () => {
    it('tracks remaining bits correctly', () => {
      const bs = BitStream.fromBytes(new Uint8Array([0xff, 0x00]), 16);
      expect(bs.remaining).toBe(16);
      bs.readU8();
      expect(bs.remaining).toBe(8);
      bs.readU8();
      expect(bs.remaining).toBe(0);
    });
  });

  describe('bounds checking', () => {
    it('throws BitStreamError when reading past end', () => {
      const bs = BitStream.fromBytes(new Uint8Array([0xff]), 4);
      bs.readBits(4);
      expect(() => bs.readBit()).toThrow(BitStreamError);
    });

    it('throws BitStreamError on empty stream read', () => {
      const bs = BitStream.fromBytes(new Uint8Array(0), 0);
      expect(() => bs.readBit()).toThrow(BitStreamError);
    });

    it('error message includes position and length', () => {
      const bs = BitStream.fromBytes(new Uint8Array([0x00]), 8);
      bs.readBits(8);
      try {
        bs.readBit();
        expect.unreachable('should have thrown');
      } catch (e) {
        expect(e).toBeInstanceOf(BitStreamError);
        expect((e as BitStreamError).message).toContain('pos=8');
        expect((e as BitStreamError).message).toContain('length=8');
      }
    });
  });
});
