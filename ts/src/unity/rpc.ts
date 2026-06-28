import { BitStream } from '../bitstream.js';
import { encodeStringForWire, decodeString } from '../huffman.js';
import { encodeViewId, rpcViewConstantFromVid } from './view-id.js';
import type { ViewId } from './view-id.js';
import {
  getMethodId,
  lookupMethodByHash,
  registerMethodNames,
  computeMethodIndex,
} from './method-hash.js';

export const enum RpcMode {
  Server = 0,
  Others = 1,
  All = 2,
  Player = 3,
  OthersBuffered = 5,
  AllBuffered = 6,
}

export const RPC_MODE_NAMES: Record<number, string> = {
  0: 'Server',
  1: 'Others',
  2: 'All',
  3: 'Player',
  5: 'OthersBuffered',
  6: 'AllBuffered',
};

export const RPC_MODE_FROM_NAME: Record<string, RpcMode> = {
  Server: RpcMode.Server,
  Others: RpcMode.Others,
  All: RpcMode.All,
  Player: RpcMode.Player,
  OthersBuffered: RpcMode.OthersBuffered,
  AllBuffered: RpcMode.AllBuffered,
};

const MSG_ID_RPC = 0x1b;
export const MSG_ID_BATCH_INDEX = 0x07;
const MAX_BYTES_PARAM_SIZE = 1_048_576;
export const INTERNAL_RPC_CONSTANT = 0x0000;

const INTERNAL_RPCS = new Set(['__RPCNetworkInstantiate']);

export type ParamType =
  | 'int'
  | 'float'
  | 'string'
  | 'Vector3'
  | 'Quaternion'
  | 'bytes'
  | 'NetworkViewID'
  | 'NetworkPlayer';

export interface RpcParam {
  type: ParamType;
  value: number | string | number[] | Uint8Array;
}

export const METHOD_SIGNATURES: Record<string, ParamType[]> = {
  RPC_Int: ['int'],
  RPC_Float: ['float'],
  RPC_String: ['string'],
  RPC_Vector3: ['Vector3'],
  RPC_Quaternion: ['Quaternion'],
  RPC_Bytes: ['bytes'],
  RPC_IntFloatString: ['int', 'float', 'string'],
  RPC_Void: [],
  RPC_Alpha: ['int'],
  RPC_Beta: ['int'],
  RPC_Gamma: ['int'],
  RPC_NetworkViewID: ['NetworkViewID'],
  RPC_NetworkPlayer: ['NetworkPlayer'],
};

const METHOD_INDEX_MAP = new Map<string, number>();
const INDEX_TO_METHOD = new Map<number, string>();
const METHOD_TAG_MAP = new Map<string, number>();

export function registerMethodTag(methodName: string, tag: number): void {
  METHOD_TAG_MAP.set(methodName, tag);
}

export function registerMethodTags(tags: Record<string, number>): void {
  for (const [name, tag] of Object.entries(tags)) {
    METHOD_TAG_MAP.set(name, tag);
  }
}

function registerLoaderAssembly(): void {
  const INTERFACE_METHODS = 7;
  const LOADER_RPC_RIDS: Record<string, number> = {
    RPC_Void: 28,
    RPC_Int: 29,
    RPC_Float: 30,
    RPC_String: 31,
    RPC_Vector3: 32,
    RPC_Quaternion: 33,
    RPC_Bytes: 34,
    RPC_IntFloatString: 35,
    RPC_NetworkPlayer: 36,
    RPC_NetworkViewID: 37,
    RPC_Alpha: 38,
    RPC_Beta: 39,
    RPC_Gamma: 40,
  };
  for (const [name, rid] of Object.entries(LOADER_RPC_RIDS)) {
    const idx = computeMethodIndex(rid, INTERFACE_METHODS);
    METHOD_INDEX_MAP.set(name, idx);
    INDEX_TO_METHOD.set(idx, name);
    METHOD_TAG_MAP.set(name, idx & 0x0F);
  }
  registerMethodNames(Object.keys(METHOD_SIGNATURES));
  registerMethodNames([...INTERNAL_RPCS]);
}

registerLoaderAssembly();

export function getBuiltinMethodNames(): string[] {
  return [...METHOD_INDEX_MAP.keys()];
}

export function hasMethodIndex(methodName: string): boolean {
  return METHOD_INDEX_MAP.has(methodName);
}

/** Register a method index learned from observing first-use / subsequent-use pairs. */
export function learnMethodIndex(methodName: string, index: number): void {
  if (INDEX_TO_METHOD.has(index)) return;
  METHOD_INDEX_MAP.set(methodName, index);
  INDEX_TO_METHOD.set(index, methodName);
  METHOD_TAG_MAP.set(methodName, index & 0x0F);
}

/**
 * Register method indices for game-specific RPC methods.
 *
 * Each entry maps an RPC method name to its 7-bit wire-format index.
 * Use scripts/extract-method-indices.sh on the game's Assembly-CSharp.dll
 * to compute these values, then pass the result here.
 *
 * Example:
 *   registerMethodIndices({
 *     ReceiveStaticTargetedEvent: 0xa8,
 *     ReceiveBroadcastAllEvent: 0xd0,
 *   });
 */
export function registerMethodIndices(indices: Record<string, number>): void {
  for (const [name, idx] of Object.entries(indices)) {
    METHOD_INDEX_MAP.set(name, idx);
    INDEX_TO_METHOD.set(idx, name);
    METHOD_TAG_MAP.set(name, idx & 0x0F);
  }
  registerMethodNames(Object.keys(indices));
}

export interface RpcEncodeOptions {
  methodName: string;
  params: RpcParam[];
  viewId: number;
  rpcCounter: number;
  mode: RpcMode;
  /** Which NetworkView receives this RPC. Accepts a ViewId or a raw 16-bit constant. */
  targetView: ViewId | number;
  relay?: boolean;
  /** Explicit method index for subsequent-use encoding. Overrides global lookup. */
  methodIndex?: number;
}

function resolveTargetView(tv: ViewId | number): number {
  return typeof tv === 'number' ? tv : rpcViewConstantFromVid(tv);
}

/** Encode a subsequent-use RPC (method already registered on receiver). */
export function encodeRpcSubsequent(opts: RpcEncodeOptions): {
  data: Uint8Array;
  bitLength: number;
} {
  const methodIndex = opts.methodIndex ?? METHOD_INDEX_MAP.get(opts.methodName);
  if (methodIndex === undefined) {
    throw new Error(`Unknown method for subsequent encoding: ${opts.methodName}`);
  }

  const sig = METHOD_SIGNATURES[opts.methodName] ?? [];
  const paramBs = new BitStream();
  encodeParams(paramBs, sig, opts.params);
  const paramBits = paramBs.bitLength;

  const relayBits = opts.relay ? 5 : 0;
  const targetBits = opts.mode === RpcMode.Player ? 1 : 0;
  const totalBits = 140 + targetBits + paramBits + relayBits;

  const bs = new BitStream();
  bs.writeU8(MSG_ID_RPC);
  bs.writeBytes(encodeViewId(opts.viewId));
  const counter16 = opts.rpcCounter & 0xffff;
  bs.writeU8((counter16 >> 8) & 0xff);
  bs.writeU8(counter16 & 0xff);
  bs.writeU8(0x0b);
  bs.writeBit(0);
  bs.writeBits(methodIndex, 7);
  bs.writeU16BE(0);
  const remaining = totalBits - 121;
  bs.writeU16BE(remaining);
  const constant = INTERNAL_RPCS.has(opts.methodName) ? INTERNAL_RPC_CONSTANT : resolveTargetView(opts.targetView);
  bs.writeU16BE(constant);
  bs.writeBits(opts.mode, 4);
  if (opts.mode === RpcMode.Player) {
    bs.writeBit(0);
  }
  copyBits(paramBs, bs, paramBits);
  if (opts.relay) {
    bs.writeBits(0, 5);
  }

  return { data: bs.toBytes(), bitLength: totalBits };
}

/** Encode a first-use RPC (includes method name hash for registration). */
export function encodeRpcFirstUse(opts: RpcEncodeOptions): {
  data: Uint8Array;
  bitLength: number;
} {
  const { classGuid, methodHash } = getMethodId(opts.methodName);
  const methodIdBits = (classGuid.length + methodHash.length) * 8;
  const lengthIndicator = methodIdBits / 4;

  const sig = METHOD_SIGNATURES[opts.methodName] ?? [];
  const paramBs = new BitStream();
  encodeParams(paramBs, sig, opts.params);
  const paramBits = paramBs.bitLength;

  const hashExtraBits = methodIdBits - 48;
  const relayBits = opts.relay ? 5 : 0;
  const targetBits = opts.mode === RpcMode.Player ? 1 : 0;
  const paramStart = 160 + hashExtraBits + 52 + 4 + targetBits;
  const totalBits = paramStart + paramBits + relayBits;

  const bs = new BitStream();
  bs.writeU8(MSG_ID_RPC);
  bs.writeBytes(encodeViewId(opts.viewId));
  const counter16 = opts.rpcCounter & 0xffff;
  bs.writeU8((counter16 >> 8) & 0xff);
  bs.writeU8(counter16 & 0xff);
  bs.writeU8(0x0b);
  bs.writeBit(1);
  bs.writeBits(0, 7);
  while (bs.pos < 104) {
    bs.writeBit(0);
  }
  bs.writeU8(lengthIndicator);
  bs.writeBytes(classGuid);
  bs.writeBytes(methodHash);
  const remainingCount = paramBits + 19 + targetBits + relayBits;
  const methodTag = METHOD_TAG_MAP.get(opts.methodName) ?? 0;
  bs.writeBits(methodTag, 4);
  bs.writeBits(0, 16);
  bs.writeU16BE(remainingCount);
  const constant = INTERNAL_RPCS.has(opts.methodName) ? INTERNAL_RPC_CONSTANT : resolveTargetView(opts.targetView);
  bs.writeU16BE(constant);
  bs.writeBits(opts.mode, 4);
  if (opts.mode === RpcMode.Player) {
    bs.writeBit(0);
  }
  copyBits(paramBs, bs, paramBits);
  if (opts.relay) {
    bs.writeBits(0, 5);
  }

  return { data: bs.toBytes(), bitLength: totalBits };
}

export interface DecodedRpc {
  methodName: string;
  rpcCounter: number;
  rpcMode: string;
  firstUse: boolean;
  viewId: number;
  params: unknown[];
  classGuid?: string;
  methodHash?: string;
  /** Raw 7-bit method index from subsequent-use messages (absent on first-use). */
  methodIndex?: number;
}

/** Decode a Unity RPC message from raw payload bytes. */
export function decodeRpc(payload: Uint8Array, bitLength: number): DecodedRpc {
  const bs = new BitStream(payload, bitLength);

  bs.readU8(); // msg_id
  const viewIdHi = bs.readBits(16);
  const viewIdMid = bs.readBits(16);
  const viewIdLo = bs.readBits(16);
  const viewId = viewIdHi * 0x100000000 + viewIdMid * 0x10000 + viewIdLo;
  const counterHigh = bs.readU8();
  const counterLow = bs.readU8();
  const rpcCounter = (counterHigh << 8) | counterLow;
  bs.readBits(8); // 0x0b marker
  const firstUse = bs.readBit() === 1;

  const result: DecodedRpc = {
    methodName: '',
    rpcCounter,
    rpcMode: '',
    firstUse,
    viewId,
    params: [],
  };

  if (firstUse) {
    bs.readBits(7);
    bs.pos = 104;
    const lengthIndicator = bs.readU8();
    const methodIdBits = lengthIndicator * 4;
    const guid = bs.readBytes(6);
    result.classGuid = bytesToHex(guid);
    const hashBytes = (methodIdBits - 48) / 8;
    if (hashBytes > 0) {
      const mhash = bs.readBytes(hashBytes);
      result.methodHash = bytesToHex(mhash);
      result.methodName = lookupMethodByHash(result.methodHash) ?? 'unknown';
    }
    const hashExtraBits = methodIdBits - 48;
    const modeStart = 160 + hashExtraBits + 52;
    bs.pos = modeStart;
  } else {
    bs.pos = 80;
    const methodIndexByte = bs.readBits(8) & 0xfe;
    result.methodIndex = methodIndexByte;
    result.methodName =
      INDEX_TO_METHOD.get(methodIndexByte) ??
      `unknown_0x${methodIndexByte.toString(16).padStart(2, '0')}`;
    bs.pos = 136;
  }

  const modeVal = bs.readBits(4);
  result.rpcMode = RPC_MODE_NAMES[modeVal] ?? String(modeVal);

  if (result.rpcMode === 'Player') {
    bs.readBit();
  }

  const sig = METHOD_SIGNATURES[result.methodName];
  if (sig) {
    result.params = decodeParams(bs, sig);
  }

  return result;
}

/** Check if a 0x1b message is an RPC (byte 9 === 0x0b) vs state sync. */
export function isRpc(payload: Uint8Array): boolean {
  return payload.length >= 10 && payload[9] === 0x0b;
}

function decodeParams(bs: BitStream, sig: ParamType[]): unknown[] {
  const params: unknown[] = [];
  for (const ptype of sig) {
    if (ptype === 'int') {
      params.push(bs.readI32BE());
    } else if (ptype === 'float') {
      params.push(bs.readFloatBE());
    } else if (ptype === 'string') {
      params.push(decodeStringParam(bs));
    } else if (ptype === 'Vector3') {
      params.push([bs.readFloatBE(), bs.readFloatBE(), bs.readFloatBE()]);
    } else if (ptype === 'Quaternion') {
      params.push([bs.readFloatBE(), bs.readFloatBE(), bs.readFloatBE(), bs.readFloatBE()]);
    } else if (ptype === 'bytes') {
      const count = bs.readU32BE();
      if (count > MAX_BYTES_PARAM_SIZE) {
        throw new Error(`bytes param too large: ${count} > ${MAX_BYTES_PARAM_SIZE}`);
      }
      params.push(bs.readBytes(count));
    } else if (ptype === 'NetworkViewID') {
      params.push(bs.readBits(16));
    } else {
      // NetworkPlayer
      params.push(bs.readI32BE());
    }
  }
  return params;
}

function decodeStringParam(bs: BitStream): string {
  const bitCount = bs.readCompressedU32();
  if (bitCount === 0) return '';
  let bits = '';
  for (let i = 0; i < bitCount; i++) {
    bits += bs.readBit() === 1 ? '1' : '0';
  }
  const decoded = decodeString(bits);
  return new TextDecoder().decode(decoded);
}

function encodeParams(bs: BitStream, sig: ParamType[], params: RpcParam[]): void {
  for (let i = 0; i < sig.length; i++) {
    const ptype = sig[i] ?? 'int';
    const param = params[i];
    const val = param?.value;
    if (ptype === 'int') {
      bs.writeI32BE(typeof val === 'number' ? val : 0);
    } else if (ptype === 'float') {
      bs.writeFloatBE(typeof val === 'number' ? val : 0);
    } else if (ptype === 'string') {
      encodeStringParam(bs, typeof val === 'string' ? val : '');
    } else if (ptype === 'Vector3') {
      const v = Array.isArray(val) ? val : [0, 0, 0];
      bs.writeFloatBE(v[0] ?? 0);
      bs.writeFloatBE(v[1] ?? 0);
      bs.writeFloatBE(v[2] ?? 0);
    } else if (ptype === 'Quaternion') {
      const q = Array.isArray(val) ? val : [0, 0, 0, 1];
      bs.writeFloatBE(q[0] ?? 0);
      bs.writeFloatBE(q[1] ?? 0);
      bs.writeFloatBE(q[2] ?? 0);
      bs.writeFloatBE(q[3] ?? 0);
    } else if (ptype === 'bytes') {
      const data = val instanceof Uint8Array ? val : new Uint8Array(0);
      bs.writeU32BE(data.length);
      bs.writeBytes(data);
    } else if (ptype === 'NetworkViewID') {
      bs.writeBits(typeof val === 'number' ? val : 0, 16);
    } else {
      // NetworkPlayer
      bs.writeI32BE(typeof val === 'number' ? val : 0);
    }
  }
}

function encodeStringParam(bs: BitStream, s: string): void {
  if (!s) {
    bs.writeCompressedU32(0);
    return;
  }
  const encodedBits = encodeStringForWire(s);
  bs.writeCompressedU32(encodedBits.length);
  for (let i = 0; i < encodedBits.length; i++) {
    bs.writeBit(encodedBits[i] === '1' ? 1 : 0);
  }
}

function copyBits(src: BitStream, dst: BitStream, count: number): void {
  src.pos = 0;
  for (let i = 0; i < count; i++) {
    dst.writeBit(src.readBit());
  }
}

function bytesToHex(bytes: Uint8Array): string {
  let hex = '';
  for (let i = 0; i < bytes.length; i++) {
    hex += (bytes[i] ?? 0).toString(16).padStart(2, '0');
  }
  return hex;
}

/** Encode an RPC Batch Index message (msg_id 0x07). */
export function encodeBatchIndex(
  methodName: string,
  methodIndex: number,
): { data: Uint8Array; bitLength: number } {
  const { classGuid, methodHash } = getMethodId(methodName);
  const methodIdBytes = classGuid.length + methodHash.length;
  const methodIdBits = methodIdBytes * 8;

  const bs = new BitStream();
  bs.writeU8(MSG_ID_BATCH_INDEX);
  bs.writeU32BE(methodIdBits / 2);
  bs.writeBit(0); // flag
  bs.writeBytes(classGuid);
  bs.writeBytes(methodHash);
  bs.writeBits(methodIndex >> 2, 5);

  const totalBits = 8 + 32 + 1 + methodIdBits + 5;
  // pad to byte boundary
  while (bs.pos % 8 !== 0) {
    bs.writeBit(0);
  }

  return { data: bs.toBytes(), bitLength: totalBits };
}

export interface DecodedBatchIndex {
  methodName: string | null;
  methodIndex: number;
}

/** Decode an RPC Batch Index message (msg_id 0x07). */
export function decodeBatchIndex(payload: Uint8Array): DecodedBatchIndex | null {
  if (payload.length < 6 || payload[0] !== MSG_ID_BATCH_INDEX) return null;

  const bs = new BitStream(payload);
  bs.readU8(); // msg_id
  const halfBits = bs.readU32BE();
  const methodIdBits = halfBits * 2;
  const hashBytes = methodIdBits / 8 - 6;
  if (hashBytes < 0) return null;

  bs.readBit(); // flag (always 0)
  bs.readBytes(6); // classGuid (skip)
  const methodHash = hashBytes > 0 ? bs.readBytes(hashBytes) : new Uint8Array(0);
  const methodIndex = bs.readBits(5) << 2;

  const hashHex = bytesToHex(methodHash);
  const methodName = lookupMethodByHash(hashHex);

  return { methodName, methodIndex };
}
