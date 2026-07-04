import { describe, it, expect, vi } from 'vitest';
import { BitStream } from '../src/bitstream.js';
import { decodeQueryReply } from '../src/master/serialization.js';
import { parsePacket, buildDataPacket } from '../src/raknet/packet.js';
import { ReliabilityLayer } from '../src/raknet/reliability.js';
import { Reliability } from '../src/raknet/types.js';
import { decodeRpc, decodeBatchIndex } from '../src/unity/rpc.js';

describe('decode safety caps', () => {
  describe('Fix 1: numColumns cap', () => {
    it('throws when numColumns exceeds 1000', () => {
      const bs = new BitStream();
      bs.writeU8(78);
      bs.writeU32BE(1001);
      expect(() => decodeQueryReply(bs.toBytes())).toThrow(/numColumns exceeds cap/);
    });
  });

  describe('Fix 1: numRows cap', () => {
    it('throws when numRows exceeds 100000', () => {
      const bs = new BitStream();
      bs.writeU8(78);
      bs.writeU32BE(0);
      bs.writeU32BE(100_001);
      expect(() => decodeQueryReply(bs.toBytes())).toThrow(/numRows exceeds cap/);
    });
  });

  describe('Fix 2: numEntries cap', () => {
    it('throws when numEntries exceeds numColumns', () => {
      const bs = new BitStream();
      bs.writeU8(78);
      bs.writeU32BE(1);
      bs.writeCompressedU32(0);
      bs.writeU8(0);
      bs.writeU32BE(1);
      bs.writeU32BE(0);
      bs.writeU32BE(2);
      expect(() => decodeQueryReply(bs.toBytes())).toThrow(/numEntries exceeds numColumns/);
    });
  });

  describe('Fix 3: BINARY cell length cap', () => {
    it('throws when BINARY cell length exceeds 16MB', () => {
      const bs = new BitStream();
      bs.writeU8(78);
      bs.writeU32BE(1);
      bs.writeCompressedU32(0);
      bs.writeU8(2); // BINARY
      bs.writeU32BE(1);
      bs.writeU32BE(0);
      bs.writeU32BE(1);
      bs.writeU32BE(0); // cellIdx
      bs.writeBool(false); // not empty
      bs.writeU32BE(16 * 1024 * 1024 + 1);
      expect(() => decodeQueryReply(bs.toBytes())).toThrow(/BINARY cell length exceeds cap/);
    });
  });

  describe('Fix 4: Huffman bitLength clamp', () => {
    it('clamps bitLength to remaining and warns', () => {
      const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
      const bs = new BitStream();
      bs.writeU8(78);
      bs.writeU32BE(1);
      bs.writeCompressedU32(9999);
      bs.writeU8(0);
      try {
        decodeQueryReply(bs.toBytes());
      } catch {
        // may throw later
      }
      expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining('Huffman bitLength exceeds remaining'));
      warnSpy.mockRestore();
    });
  });

  describe('Fix 5: splitPacketCount cap', () => {
    it('drops splits with count > 128 and warns', () => {
      const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
      const rl = new ReliabilityLayer({ host: '127.0.0.1', port: 7777 });

      const frame = {
        reliability: Reliability.RELIABLE as number,
        bitLength: 8,
        reliableMsgNumber: 0,
        orderingIndex: null,
        orderingChannel: 0,
        splitPacketCount: 200,
        splitPacketId: 1,
        splitPacketIndex: 0,
        payload: new Uint8Array([0x42]),
      };

      const packet = buildDataPacket(0, [frame], 0);
      rl.processIncoming(packet);

      expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining('splitPacketCount exceeds cap'));
      warnSpy.mockRestore();
    });

    it('drops splits with index >= count and warns', () => {
      const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
      const rl = new ReliabilityLayer({ host: '127.0.0.1', port: 7777 });

      const frame = {
        reliability: Reliability.RELIABLE as number,
        bitLength: 8,
        reliableMsgNumber: 0,
        orderingIndex: null,
        orderingChannel: 0,
        splitPacketCount: 5,
        splitPacketId: 1,
        splitPacketIndex: 5,
        payload: new Uint8Array([0x42]),
      };

      const packet = buildDataPacket(0, [frame], 0);
      rl.processIncoming(packet);

      expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining('splitPacketIndex >= splitPacketCount'));
      warnSpy.mockRestore();
    });
  });

  describe('Fix 6: frame bitLength clamp', () => {
    it('clamps bitLength when payload is truncated and warns', () => {
      const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});

      const header = new Uint8Array(12);
      header[0] = 0x84;

      const frameHeader = new Uint8Array([
        0x00, // reliability=0, no split
        0x00, 0x80, // bitLength = 128 (16 bytes claimed)
      ]);
      const payload = new Uint8Array([0x01, 0x02, 0x03, 0x04]);

      const packet = new Uint8Array(header.length + frameHeader.length + payload.length);
      packet.set(header);
      packet.set(frameHeader, header.length);
      packet.set(payload, header.length + frameHeader.length);

      const parsed = parsePacket(packet);
      expect(parsed.type).toBe('data');
      if (parsed.type === 'data') {
        expect(parsed.frames[0]!.bitLength).toBe(32);
      }
      expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining('frame bitLength exceeds payload'));
      warnSpy.mockRestore();
    });
  });

  describe('Fix 7: ACK range cap', () => {
    it('skips ACK ranges wider than 10000 and warns', () => {
      const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
      const rl = new ReliabilityLayer({ host: '127.0.0.1', port: 7777 });

      rl.queueOutgoing(new Uint8Array([0x01]), Reliability.RELIABLE);
      rl.getOutgoingPackets();

      // Build ACK with range [0, 20000]
      const ackBuf = new Uint8Array(18);
      ackBuf[0] = 0xc0;
      // bytes 1-4: stats = 0
      // bytes 5-8: timestamp = 0
      ackBuf[9] = 0x00; ackBuf[10] = 0x01; // 1 range
      ackBuf[11] = 0x00; // maxEqMin = false
      // min = 0 (u24le)
      ackBuf[12] = 0x00; ackBuf[13] = 0x00; ackBuf[14] = 0x00;
      // max = 20000 = 0x4E20, LE = [0x20, 0x4E, 0x00]
      ackBuf[15] = 0x20; ackBuf[16] = 0x4E; ackBuf[17] = 0x00;

      rl.processIncoming(ackBuf);

      expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining('ACK range span exceeds cap'));
      warnSpy.mockRestore();
    });
  });

  describe('Fix 8: decodeRpc minimum bitLength', () => {
    it('throws when bitLength < 88', () => {
      const payload = new Uint8Array([0x1b, 0x00, 0x00, 0x00]);
      expect(() => decodeRpc(payload, 32)).toThrow(/too short/);
    });
  });

  describe('decodeBatchIndex hashBytes cap', () => {
    it('rejects when hashBytes > 64 and warns', () => {
      const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
      const bs = new BitStream();
      bs.writeU8(0x07);
      bs.writeU32BE(300); // halfBits=300 => methodIdBits=600 => hashBytes=69 > 64
      const payload = new Uint8Array(100);
      const prefix = bs.toBytes();
      payload.set(prefix);

      const result = decodeBatchIndex(payload);
      expect(result).toBeNull();
      expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining('batchIndex hashBytes exceeds cap'));
      warnSpy.mockRestore();
    });
  });
});
