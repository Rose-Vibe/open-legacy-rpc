# M13 Section 2: RakNet Transport

## Goal

Implement RakNet 3.731's transport layer: packet framing, reliability,
ordering, split packet assembly, ACK/NAK, and retransmission. This is
the most complex section — the Python equivalent is ~670 lines across
`raknet.py` and `raknet_transport.py`.

## Modules

### `src/raknet/types.ts` — Shared Types

```ts
enum Reliability {
  UNRELIABLE = 0,
  UNRELIABLE_SEQUENCED = 1,
  RELIABLE = 2,
  RELIABLE_ORDERED = 3,
  RELIABLE_SEQUENCED = 4,
}

enum MessageId {
  CONNECTED_PING = 0x00,
  CONNECTED_PONG = 0x03,
  CONNECTION_REQUEST = 0x09,
  // ... all RakNet message IDs
  ID_UNITY_RPC_OR_SYNC = 0x1b,
}

interface IncomingMessage {
  messageId: number;
  payload: Uint8Array;
  reliability: Reliability;
  bitLength: number;
  senderAddress: AddressInfo;
}
```

### `src/raknet/packet.ts` — Packet Framing

Parse and construct RakNet packet headers:
- ACK packets (0xc0)
- NAK packets (0xa0)
- Data packets (0x80–0x8f): sequence number + message frames
- Each frame: reliability header, ordering channel, split info, payload

**Key functions:**
- `parsePacket(data: Uint8Array): ParsedPacket`
- `buildDataPacket(sequenceNumber: number, frames: Frame[]): Uint8Array`
- `buildAck(sequenceNumbers: number[]): Uint8Array`
- `parseFrame(bs: BitStream): Frame`
- `buildFrame(frame: Frame): BitStream`

Port from: `protocol/raknet.py` (259 lines)

### `src/raknet/reliability.ts` — Reliability Layer

Manages per-connection reliability state:
- Outgoing: sequence number counter, message number counter, split ID counter
- Incoming: ACK tracking, duplicate detection, ordering channel queues
- Split packet assembly (collect fragments, reassemble when complete)
- Retransmission queue (reliable messages resent if not ACKed)

**Key class:**
```ts
class ReliabilityLayer {
  queueOutgoing(payload: Uint8Array, reliability: Reliability): void;
  processIncoming(packet: ParsedPacket): IncomingMessage[];
  getOutgoingPackets(): Uint8Array[];  // flush queued frames into packets
  checkRetransmits(): Uint8Array[];    // resend unACKed reliable messages
  processAck(ack: AckPacket): void;
}
```

Port from: `protocol/raknet_transport.py` (412 lines)

### `src/raknet/socket.ts` — UDP Socket Wrapper

Thin wrapper around `node:dgram`:
- `bind(port: number)` — server mode
- `sendTo(data: Uint8Array, address: string, port: number)` — send packet
- `onMessage(handler)` — receive callback
- `close()` — cleanup

## Design Notes

### Byte Ordering
RakNet uses a mix of big-endian and little-endian depending on the field.
Sequence numbers are little-endian (24-bit). Message numbers are 24-bit LE.
Payload data is big-endian. The BitStream handles this — the transport layer
passes byte arrays to/from BitStream for header parsing.

### Split Packets
Messages > ~1200 bytes are split into fragments. Each fragment has a split
ID, split index, and split count. The reliability layer reassembles them
in order. Maximum split count is ~100 fragments (128KB theoretical max).

### Buffer Management
Use `Uint8Array` throughout. Avoid `Buffer` for portability (works in
both Node.js and edge runtimes). Use `DataView` for multi-byte reads/writes
when not going through BitStream.

## Exit Criteria

- [ ] Packet parsing handles all frame types (ACK, NAK, data)
- [ ] Reliability layer correctly:
  - Tracks outgoing sequence numbers
  - Generates ACKs for received packets
  - Reassembles split packets
  - Retransmits unACKed reliable messages
  - Orders RELIABLE_ORDERED messages by ordering index
  - Deduplicates messages by message number
- [ ] Unit tests for:
  - Packet round-trip (build → parse → identical)
  - Split packet assembly (3 fragments → 1 message)
  - ACK generation and processing
  - Ordering channel (out-of-order → reordered delivery)
  - Retransmission timing
- [ ] `pnpm typecheck` and `pnpm lint` pass
