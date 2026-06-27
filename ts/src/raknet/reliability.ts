import type { Frame, ParsedPacket, IncomingMessage, AddressInfo } from './types.js';
import { Reliability, isReliable, isOrdered, createFrame } from './types.js';
import { parsePacket, buildDataPacket, buildAck } from './packet.js';

interface SplitState {
  count: number;
  fragments: Map<number, Uint8Array>;
  reliability: Reliability;
  reliableMsgNumber: number | null;
  orderingIndex: number | null;
  orderingChannel: number;
}

interface UnackedEntry {
  frame: Frame;
  sendTime: number;
  datagramSeq: number;
}

export class ReliabilityLayer {
  private sendSeq = 0;
  private recvSeqMax = -1;
  private reliableSendNum = 0;
  private orderingIndexOut: Map<number, number> = new Map();
  private orderingIndexIn: Map<number, number> = new Map();
  private orderingQueues: Map<number, Map<number, Frame>> = new Map();
  private splitAssembler: Map<number, SplitState> = new Map();
  private splitIdCounter = 0;
  private pendingAcks: number[] = [];
  private unackedReliable: Map<number, UnackedEntry> = new Map();
  private outgoingQueue: Frame[] = [];
  private seenReliable: Set<number> = new Set();
  private seenReliableMin = 0;
  private readonly remoteAddress: AddressInfo;
  private readonly connectTime: number;

  constructor(remoteAddress: AddressInfo) {
    this.remoteAddress = remoteAddress;
    this.connectTime = Date.now();
  }

  getTimestamp(): number {
    return (Date.now() - this.connectTime) & 0xffffffff;
  }

  queueOutgoing(payload: Uint8Array, reliability: Reliability, orderingChannel = 0): void {
    const frame = createFrame(payload, reliability);

    if (isReliable(reliability)) {
      frame.reliableMsgNumber = this.reliableSendNum++;
    }

    if (isOrdered(reliability)) {
      const ch = orderingChannel;
      const idx = this.orderingIndexOut.get(ch) ?? 0;
      frame.orderingIndex = idx;
      frame.orderingChannel = ch;
      this.orderingIndexOut.set(ch, idx + 1);
    }

    this.outgoingQueue.push(frame);
  }

  getOutgoingPackets(): Uint8Array[] {
    const packets: Uint8Array[] = [];

    if (this.pendingAcks.length > 0) {
      packets.push(buildAck(this.pendingAcks, this.getTimestamp()));
      this.pendingAcks = [];
    }

    for (const frame of this.outgoingQueue) {
      const seq = this.sendSeq;
      this.sendSeq = (this.sendSeq + 1) & 0xffffff;
      const packet = buildDataPacket(seq, [frame], this.getTimestamp());
      packets.push(packet);

      if (isReliable(frame.reliability)) {
        this.unackedReliable.set(seq, {
          frame,
          sendTime: Date.now(),
          datagramSeq: seq,
        });
      }
    }
    this.outgoingQueue = [];

    return packets;
  }

  processIncoming(data: Uint8Array): IncomingMessage[] {
    const parsed = parsePacket(data);
    return this.processPacket(parsed);
  }

  processPacket(parsed: ParsedPacket): IncomingMessage[] {
    switch (parsed.type) {
      case 'ack':
        this.handleAck(parsed.ranges);
        return [];
      case 'nak':
        return [];
      case 'data':
        this.pendingAcks.push(parsed.sequenceNumber);
        if (parsed.sequenceNumber > this.recvSeqMax) {
          this.recvSeqMax = parsed.sequenceNumber;
        }
        return this.processFrames(parsed.frames);
      case 'offline':
        return [
          {
            messageId: parsed.messageId,
            payload: parsed.data,
            reliability: Reliability.UNRELIABLE,
            bitLength: parsed.data.length * 8,
            senderAddress: this.remoteAddress,
          },
        ];
      case 'unknown':
        return [];
    }
  }

  checkRetransmits(timeoutMs = 1000): Frame[] {
    const now = Date.now();
    const retransmits: Frame[] = [];
    const keys = [...this.unackedReliable.keys()];
    for (const oldSeq of keys) {
      const entry = this.unackedReliable.get(oldSeq);
      if (!entry) continue;
      if (now - entry.sendTime > timeoutMs) {
        const newSeq = this.sendSeq;
        this.sendSeq = (this.sendSeq + 1) & 0xffffff;
        this.unackedReliable.delete(oldSeq);
        this.unackedReliable.set(newSeq, {
          frame: entry.frame,
          sendTime: now,
          datagramSeq: newSeq,
        });
        retransmits.push(entry.frame);
      }
    }
    return retransmits;
  }

  getRetransmitPackets(timeoutMs = 1000): Uint8Array[] {
    const now = Date.now();
    const packets: Uint8Array[] = [];
    const keys = [...this.unackedReliable.keys()];
    for (const oldSeq of keys) {
      const entry = this.unackedReliable.get(oldSeq);
      if (!entry) continue;
      if (now - entry.sendTime > timeoutMs) {
        const newSeq = this.sendSeq;
        this.sendSeq = (this.sendSeq + 1) & 0xffffff;
        const packet = buildDataPacket(newSeq, [entry.frame], this.getTimestamp());
        this.unackedReliable.delete(oldSeq);
        this.unackedReliable.set(newSeq, {
          frame: entry.frame,
          sendTime: now,
          datagramSeq: newSeq,
        });
        packets.push(packet);
      }
    }
    return packets;
  }

  private handleAck(ranges: Array<[number, number]>): void {
    for (const [min, max] of ranges) {
      for (let seq = min; seq <= max; seq++) {
        this.unackedReliable.delete(seq);
      }
    }
  }

  private processFrames(frames: Frame[]): IncomingMessage[] {
    const messages: IncomingMessage[] = [];
    for (const frame of frames) {
      if (isReliable(frame.reliability) && frame.reliableMsgNumber !== null) {
        if (
          frame.reliableMsgNumber < this.seenReliableMin ||
          this.seenReliable.has(frame.reliableMsgNumber)
        ) {
          continue;
        }
        this.seenReliable.add(frame.reliableMsgNumber);
        if (this.seenReliable.size > 10_000) {
          this.pruneSeenReliable();
        }
      }

      let resolved: Frame | null = null;
      if (frame.splitPacketCount !== null) {
        resolved = this.assembleSplit(frame);
      } else {
        resolved = frame;
      }

      if (!resolved) continue;

      if (resolved.reliability === Reliability.RELIABLE_ORDERED) {
        const ordered = this.processOrdered(resolved);
        for (const f of ordered) {
          messages.push(this.frameToMessage(f));
        }
      } else {
        messages.push(this.frameToMessage(resolved));
      }
    }
    return messages;
  }

  private assembleSplit(frame: Frame): Frame | null {
    const id = frame.splitPacketId ?? 0;
    const idx = frame.splitPacketIndex ?? 0;
    const count = frame.splitPacketCount ?? 0;

    let state = this.splitAssembler.get(id);
    if (!state) {
      if (this.splitAssembler.size >= 64) {
        const oldestId = this.splitAssembler.keys().next().value;
        if (oldestId !== undefined) this.splitAssembler.delete(oldestId);
      }
      state = {
        count,
        fragments: new Map(),
        reliability: frame.reliability,
        reliableMsgNumber: frame.reliableMsgNumber,
        orderingIndex: frame.orderingIndex,
        orderingChannel: frame.orderingChannel,
      };
      this.splitAssembler.set(id, state);
    }

    state.fragments.set(idx, frame.payload);

    if (state.fragments.size === state.count) {
      const parts: Uint8Array[] = [];
      let totalLen = 0;
      for (let i = 0; i < state.count; i++) {
        const part = state.fragments.get(i);
        if (!part) return null;
        parts.push(part);
        totalLen += part.length;
      }
      const fullPayload = new Uint8Array(totalLen);
      let offset = 0;
      for (const part of parts) {
        fullPayload.set(part, offset);
        offset += part.length;
      }
      this.splitAssembler.delete(id);

      return {
        reliability: state.reliability,
        bitLength: fullPayload.length * 8,
        reliableMsgNumber: state.reliableMsgNumber,
        orderingIndex: state.orderingIndex,
        orderingChannel: state.orderingChannel,
        splitPacketCount: null,
        splitPacketId: null,
        splitPacketIndex: null,
        payload: fullPayload,
      };
    }
    return null;
  }

  private processOrdered(frame: Frame): Frame[] {
    const ch = frame.orderingChannel;
    const idx = frame.orderingIndex ?? 0;
    const expectedIdx = this.orderingIndexIn.get(ch) ?? 0;

    if (idx === expectedIdx) {
      const result: Frame[] = [frame];
      let nextIdx = expectedIdx + 1;

      const queue = this.orderingQueues.get(ch);
      if (queue) {
        while (queue.has(nextIdx)) {
          const queued = queue.get(nextIdx);
          if (queued) {
            result.push(queued);
            queue.delete(nextIdx);
          }
          nextIdx++;
        }
      }

      this.orderingIndexIn.set(ch, nextIdx);
      return result;
    }

    if (idx > expectedIdx) {
      let queue = this.orderingQueues.get(ch);
      if (!queue) {
        queue = new Map();
        this.orderingQueues.set(ch, queue);
      }
      queue.set(idx, frame);
      if (queue.size > 512) {
        const oldest = Math.min(...queue.keys());
        queue.delete(oldest);
      }
    }

    return [];
  }

  private frameToMessage(frame: Frame): IncomingMessage {
    return {
      messageId: frame.payload[0] ?? 0,
      payload: frame.payload,
      reliability: frame.reliability,
      bitLength: frame.bitLength,
      senderAddress: this.remoteAddress,
    };
  }

  private pruneSeenReliable(): void {
    let newMin = this.seenReliableMin;
    const sorted = [...this.seenReliable].sort((a, b) => a - b);
    const pruneCount = Math.floor(sorted.length / 2);
    for (let i = 0; i < pruneCount; i++) {
      this.seenReliable.delete(sorted[i] as number);
    }
    if (pruneCount > 0) {
      newMin = (sorted[pruneCount - 1] as number) + 1;
    }
    this.seenReliableMin = newMin;
  }

  get nextSplitId(): number {
    return this.splitIdCounter++;
  }

  splitMessage(
    payload: Uint8Array,
    reliability: Reliability,
    orderingChannel = 0,
    maxPayloadSize = 1200,
  ): Frame[] {
    const splitId = this.nextSplitId;
    const count = Math.ceil(payload.length / maxPayloadSize);

    let orderingIndex: number | null = null;
    if (isOrdered(reliability)) {
      orderingIndex = this.orderingIndexOut.get(orderingChannel) ?? 0;
      this.orderingIndexOut.set(orderingChannel, orderingIndex + 1);
    }

    const frames: Frame[] = [];
    for (let i = 0; i < count; i++) {
      const start = i * maxPayloadSize;
      const end = Math.min(start + maxPayloadSize, payload.length);
      const chunk = payload.slice(start, end);
      const frame = createFrame(chunk, reliability);
      frame.splitPacketCount = count;
      frame.splitPacketId = splitId;
      frame.splitPacketIndex = i;
      if (isReliable(reliability)) {
        frame.reliableMsgNumber = this.reliableSendNum++;
      }
      if (orderingIndex !== null) {
        frame.orderingIndex = orderingIndex;
        frame.orderingChannel = orderingChannel;
      }
      frames.push(frame);
    }
    return frames;
  }
}
