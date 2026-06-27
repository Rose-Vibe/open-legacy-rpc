import { describe, it, expect } from 'vitest';
import { parsePacket, buildDataPacket, buildAck, buildFrame } from '../src/raknet/packet.js';
import { Reliability, createFrame } from '../src/raknet/types.js';

describe('Packet framing', () => {
  describe('data packet round-trip', () => {
    it('builds and parses an UNRELIABLE frame', () => {
      const payload = new Uint8Array([0x1b, 0xaa, 0xbb]);
      const frame = createFrame(payload, Reliability.UNRELIABLE);
      const packet = buildDataPacket(42, [frame], 1000);
      const parsed = parsePacket(packet);
      expect(parsed.type).toBe('data');
      if (parsed.type !== 'data') return;
      expect(parsed.sequenceNumber).toBe(42);
      expect(parsed.timestamp).toBe(1000);
      expect(parsed.frames).toHaveLength(1);
      const f = parsed.frames[0];
      expect(f?.reliability).toBe(Reliability.UNRELIABLE);
      expect(f?.payload).toEqual(payload);
      expect(f?.bitLength).toBe(24);
      expect(f?.reliableMsgNumber).toBeNull();
      expect(f?.orderingIndex).toBeNull();
    });

    it('builds and parses a RELIABLE_ORDERED frame', () => {
      const payload = new Uint8Array([0x09, 0x01]);
      const frame = createFrame(payload, Reliability.RELIABLE_ORDERED);
      frame.reliableMsgNumber = 5;
      frame.orderingIndex = 3;
      frame.orderingChannel = 0;
      const packet = buildDataPacket(0, [frame]);
      const parsed = parsePacket(packet);
      expect(parsed.type).toBe('data');
      if (parsed.type !== 'data') return;
      const f = parsed.frames[0];
      expect(f?.reliability).toBe(Reliability.RELIABLE_ORDERED);
      expect(f?.reliableMsgNumber).toBe(5);
      expect(f?.orderingIndex).toBe(3);
      expect(f?.orderingChannel).toBe(0);
      expect(f?.payload).toEqual(payload);
    });

    it('builds and parses a split frame', () => {
      const payload = new Uint8Array([0xde, 0xad]);
      const frame = createFrame(payload, Reliability.RELIABLE);
      frame.reliableMsgNumber = 10;
      frame.splitPacketCount = 3;
      frame.splitPacketId = 7;
      frame.splitPacketIndex = 1;
      const packet = buildDataPacket(100, [frame]);
      const parsed = parsePacket(packet);
      expect(parsed.type).toBe('data');
      if (parsed.type !== 'data') return;
      const f = parsed.frames[0];
      expect(f?.splitPacketCount).toBe(3);
      expect(f?.splitPacketId).toBe(7);
      expect(f?.splitPacketIndex).toBe(1);
    });

    it('handles multiple frames in one datagram', () => {
      const f1 = createFrame(new Uint8Array([0x01]), Reliability.UNRELIABLE);
      const f2 = createFrame(new Uint8Array([0x02]), Reliability.RELIABLE);
      f2.reliableMsgNumber = 0;
      const packet = buildDataPacket(0, [f1, f2]);
      const parsed = parsePacket(packet);
      expect(parsed.type).toBe('data');
      if (parsed.type !== 'data') return;
      expect(parsed.frames).toHaveLength(2);
      expect(parsed.frames[0]?.payload).toEqual(new Uint8Array([0x01]));
      expect(parsed.frames[1]?.payload).toEqual(new Uint8Array([0x02]));
    });
  });

  describe('ACK round-trip', () => {
    it('builds and parses a single ACK', () => {
      const ack = buildAck([42], 500);
      const parsed = parsePacket(ack);
      expect(parsed.type).toBe('ack');
      if (parsed.type !== 'ack') return;
      expect(parsed.timestamp).toBe(500);
      expect(parsed.ranges).toEqual([[42, 42]]);
    });

    it('builds and parses consecutive ACKs as a range', () => {
      const ack = buildAck([10, 11, 12, 13]);
      const parsed = parsePacket(ack);
      expect(parsed.type).toBe('ack');
      if (parsed.type !== 'ack') return;
      expect(parsed.ranges).toEqual([[10, 13]]);
    });

    it('builds and parses non-consecutive ACKs as separate ranges', () => {
      const ack = buildAck([1, 2, 5, 6, 7, 100]);
      const parsed = parsePacket(ack);
      expect(parsed.type).toBe('ack');
      if (parsed.type !== 'ack') return;
      expect(parsed.ranges).toEqual([
        [1, 2],
        [5, 7],
        [100, 100],
      ]);
    });
  });

  describe('frame serialization', () => {
    it('buildFrame output matches what parsePacket extracts', () => {
      const frame = createFrame(
        new Uint8Array([0xab, 0xcd, 0xef]),
        Reliability.UNRELIABLE_SEQUENCED,
      );
      frame.orderingIndex = 99;
      frame.orderingChannel = 2;
      const built = buildFrame(frame);
      expect(built.length).toBeGreaterThan(3);

      const packet = buildDataPacket(0, [frame]);
      const parsed = parsePacket(packet);
      if (parsed.type !== 'data') throw new Error('expected data');
      const f = parsed.frames[0];
      expect(f?.orderingIndex).toBe(99);
      expect(f?.orderingChannel).toBe(2);
    });
  });
});
