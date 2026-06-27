import { describe, it, expect } from 'vitest';
import { ReliabilityLayer } from '../src/raknet/reliability.js';
import { Reliability, createFrame } from '../src/raknet/types.js';
import { buildDataPacket, buildAck, parsePacket } from '../src/raknet/packet.js';

function makeReliability(): ReliabilityLayer {
  return new ReliabilityLayer({ host: '127.0.0.1', port: 7777 });
}

describe('ReliabilityLayer', () => {
  describe('outgoing', () => {
    it('queues and flushes a single message', () => {
      const rl = makeReliability();
      rl.queueOutgoing(new Uint8Array([0x1b, 0x01]), Reliability.UNRELIABLE);
      const packets = rl.getOutgoingPackets();
      expect(packets).toHaveLength(1);
      const parsed = parsePacket(packets[0]!);
      expect(parsed.type).toBe('data');
      if (parsed.type !== 'data') return;
      expect(parsed.frames[0]?.payload).toEqual(new Uint8Array([0x1b, 0x01]));
    });

    it('assigns sequential sequence numbers', () => {
      const rl = makeReliability();
      rl.queueOutgoing(new Uint8Array([0x01]), Reliability.UNRELIABLE);
      rl.queueOutgoing(new Uint8Array([0x02]), Reliability.UNRELIABLE);
      const packets = rl.getOutgoingPackets();
      expect(packets).toHaveLength(2);
      const p0 = parsePacket(packets[0]!);
      const p1 = parsePacket(packets[1]!);
      if (p0.type !== 'data' || p1.type !== 'data') throw new Error('expected data');
      expect(p1.sequenceNumber).toBe(p0.sequenceNumber + 1);
    });

    it('assigns reliable message numbers', () => {
      const rl = makeReliability();
      rl.queueOutgoing(new Uint8Array([0x01]), Reliability.RELIABLE);
      rl.queueOutgoing(new Uint8Array([0x02]), Reliability.RELIABLE);
      const packets = rl.getOutgoingPackets();
      const p0 = parsePacket(packets[0]!);
      const p1 = parsePacket(packets[1]!);
      if (p0.type !== 'data' || p1.type !== 'data') throw new Error('expected data');
      expect(p0.frames[0]?.reliableMsgNumber).toBe(0);
      expect(p1.frames[0]?.reliableMsgNumber).toBe(1);
    });

    it('assigns ordering indices per channel', () => {
      const rl = makeReliability();
      rl.queueOutgoing(new Uint8Array([0x01]), Reliability.RELIABLE_ORDERED, 0);
      rl.queueOutgoing(new Uint8Array([0x02]), Reliability.RELIABLE_ORDERED, 0);
      rl.queueOutgoing(new Uint8Array([0x03]), Reliability.RELIABLE_ORDERED, 1);
      const packets = rl.getOutgoingPackets();
      const frames = packets.map((p) => {
        const parsed = parsePacket(p);
        if (parsed.type !== 'data') throw new Error('expected data');
        return parsed.frames[0]!;
      });
      expect(frames[0]?.orderingIndex).toBe(0);
      expect(frames[1]?.orderingIndex).toBe(1);
      expect(frames[2]?.orderingIndex).toBe(0);
    });

    it('generates ACKs for pending', () => {
      const rl = makeReliability();
      const frame = createFrame(new Uint8Array([0x01]), Reliability.UNRELIABLE);
      const packet = buildDataPacket(10, [frame]);
      rl.processIncoming(packet);
      const outgoing = rl.getOutgoingPackets();
      expect(outgoing.length).toBeGreaterThanOrEqual(1);
      const ack = parsePacket(outgoing[0]!);
      expect(ack.type).toBe('ack');
      if (ack.type !== 'ack') return;
      expect(ack.ranges).toEqual([[10, 10]]);
    });
  });

  describe('incoming', () => {
    it('processes a simple data packet', () => {
      const rl = makeReliability();
      const frame = createFrame(new Uint8Array([0x1b, 0x42]), Reliability.UNRELIABLE);
      const packet = buildDataPacket(0, [frame]);
      const msgs = rl.processIncoming(packet);
      expect(msgs).toHaveLength(1);
      expect(msgs[0]?.messageId).toBe(0x1b);
      expect(msgs[0]?.payload).toEqual(new Uint8Array([0x1b, 0x42]));
    });

    it('deduplicates reliable messages by message number', () => {
      const rl = makeReliability();
      const frame = createFrame(new Uint8Array([0x01]), Reliability.RELIABLE);
      frame.reliableMsgNumber = 0;
      const p1 = buildDataPacket(0, [frame]);
      const p2 = buildDataPacket(1, [frame]);
      const msgs1 = rl.processIncoming(p1);
      const msgs2 = rl.processIncoming(p2);
      expect(msgs1).toHaveLength(1);
      expect(msgs2).toHaveLength(0);
    });
  });

  describe('split packet assembly', () => {
    it('reassembles 3 fragments into one message', () => {
      const rl = makeReliability();
      const chunks = [
        new Uint8Array([0x01, 0x02]),
        new Uint8Array([0x03, 0x04]),
        new Uint8Array([0x05]),
      ];
      let allMsgs: ReturnType<typeof rl.processIncoming> = [];
      for (let i = 0; i < 3; i++) {
        const frame = createFrame(chunks[i]!, Reliability.RELIABLE);
        frame.reliableMsgNumber = i;
        frame.splitPacketCount = 3;
        frame.splitPacketId = 0;
        frame.splitPacketIndex = i;
        const packet = buildDataPacket(i, [frame]);
        const msgs = rl.processIncoming(packet);
        allMsgs = allMsgs.concat(msgs);
      }
      expect(allMsgs).toHaveLength(1);
      expect(allMsgs[0]?.payload).toEqual(new Uint8Array([0x01, 0x02, 0x03, 0x04, 0x05]));
    });

    it('handles out-of-order fragments', () => {
      const rl = makeReliability();
      const chunks = [new Uint8Array([0xaa, 0xbb]), new Uint8Array([0xcc, 0xdd])];
      const order = [1, 0];
      let allMsgs: ReturnType<typeof rl.processIncoming> = [];
      for (let seq = 0; seq < 2; seq++) {
        const i = order[seq]!;
        const frame = createFrame(chunks[i]!, Reliability.RELIABLE);
        frame.reliableMsgNumber = seq;
        frame.splitPacketCount = 2;
        frame.splitPacketId = 0;
        frame.splitPacketIndex = i;
        const packet = buildDataPacket(seq, [frame]);
        allMsgs = allMsgs.concat(rl.processIncoming(packet));
      }
      expect(allMsgs).toHaveLength(1);
      expect(allMsgs[0]?.payload).toEqual(new Uint8Array([0xaa, 0xbb, 0xcc, 0xdd]));
    });
  });

  describe('ordering channel', () => {
    it('delivers out-of-order RELIABLE_ORDERED messages in order', () => {
      const rl = makeReliability();
      const makeFrame = (idx: number, data: number): ReturnType<typeof createFrame> => {
        const f = createFrame(new Uint8Array([data]), Reliability.RELIABLE_ORDERED);
        f.reliableMsgNumber = idx;
        f.orderingIndex = idx;
        f.orderingChannel = 0;
        return f;
      };

      const f0 = makeFrame(0, 0xaa);
      const f1 = makeFrame(1, 0xbb);
      const f2 = makeFrame(2, 0xcc);

      const p2 = buildDataPacket(2, [f2]);
      const m2 = rl.processIncoming(p2);
      expect(m2).toHaveLength(0);

      const p1 = buildDataPacket(1, [f1]);
      const m1 = rl.processIncoming(p1);
      expect(m1).toHaveLength(0);

      const p0 = buildDataPacket(0, [f0]);
      const m0 = rl.processIncoming(p0);
      expect(m0).toHaveLength(3);
      expect(m0[0]?.payload).toEqual(new Uint8Array([0xaa]));
      expect(m0[1]?.payload).toEqual(new Uint8Array([0xbb]));
      expect(m0[2]?.payload).toEqual(new Uint8Array([0xcc]));
    });
  });

  describe('ACK processing', () => {
    it('removes acked entries from unacked reliable', () => {
      const rl = makeReliability();
      rl.queueOutgoing(new Uint8Array([0x01]), Reliability.RELIABLE);
      const packets = rl.getOutgoingPackets();
      expect(packets.length).toBeGreaterThanOrEqual(1);

      const parsed = parsePacket(packets[packets.length - 1]!);
      if (parsed.type !== 'data') throw new Error('expected data');

      const ack = buildAck([parsed.sequenceNumber]);
      rl.processIncoming(ack);

      const retransmits = rl.checkRetransmits(0);
      expect(retransmits).toHaveLength(0);
    });
  });
});
