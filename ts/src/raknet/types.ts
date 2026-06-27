export const enum Reliability {
  UNRELIABLE = 0,
  UNRELIABLE_SEQUENCED = 1,
  RELIABLE = 2,
  RELIABLE_ORDERED = 3,
  RELIABLE_SEQUENCED = 4,
}

export const enum MessageId {
  CONNECTED_PING = 0x00,
  UNCONNECTED_PING = 0x01,
  CONNECTED_PONG = 0x03,
  CONNECTION_REQUEST = 0x04,
  OPEN_CONNECTION_REQUEST = 0x09,
  OPEN_CONNECTION_REPLY = 0x0a,
  CONNECTION_REQUEST_ACCEPTED = 0x0e,
  NEW_INCOMING_CONNECTION = 0x11,
  DISCONNECTION_NOTIFICATION_LEGACY = 0x13,
  DISCONNECTION_NOTIFICATION = 0x15,
  CONNECTION_LOST = 0x16,
  UNITY_MESSAGE = 0x1b,
  UNITY_PLAYER_ASSIGNMENT = 0x81,
  UNITY_PLAYER_READY = 0x83,
}

export const OFFLINE_MAGIC = new Uint8Array([
  0x00, 0xff, 0xff, 0x00, 0xfe, 0xfe, 0xfe, 0xfe, 0xfd, 0xfd, 0xfd, 0xfd, 0x12, 0x34, 0x56, 0x78,
]);

export const MTU_SIZE = 1464;

export interface AddressInfo {
  readonly host: string;
  readonly port: number;
}

export interface Frame {
  reliability: Reliability;
  bitLength: number;
  reliableMsgNumber: number | null;
  orderingIndex: number | null;
  orderingChannel: number;
  splitPacketCount: number | null;
  splitPacketId: number | null;
  splitPacketIndex: number | null;
  payload: Uint8Array;
}

export interface IncomingMessage {
  messageId: number;
  payload: Uint8Array;
  reliability: Reliability;
  bitLength: number;
  senderAddress: AddressInfo;
}

export type ParsedPacket =
  | { type: 'ack'; timestamp: number; ranges: Array<[number, number]> }
  | { type: 'nak'; timestamp: number; ranges: Array<[number, number]> }
  | {
      type: 'data';
      timestamp: number;
      sequenceNumber: number;
      frames: Frame[];
    }
  | { type: 'offline'; messageId: number; data: Uint8Array }
  | { type: 'unknown'; data: Uint8Array };

export function isReliable(r: Reliability): boolean {
  return r >= Reliability.RELIABLE;
}

export function isOrdered(r: Reliability): boolean {
  return (
    r === Reliability.UNRELIABLE_SEQUENCED ||
    r === Reliability.RELIABLE_ORDERED ||
    r === Reliability.RELIABLE_SEQUENCED
  );
}

export function createFrame(payload: Uint8Array, reliability: Reliability, bitLength?: number): Frame {
  return {
    reliability,
    bitLength: bitLength ?? payload.length * 8,
    reliableMsgNumber: null,
    orderingIndex: null,
    orderingChannel: 0,
    splitPacketCount: null,
    splitPacketId: null,
    splitPacketIndex: null,
    payload,
  };
}
