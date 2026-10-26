import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { describe, it, expect, vi } from 'vitest';
import { computeMethodId, computeMethodIndex, computeMethodTag, registerMethodNames } from '../src/unity/method-hash.js';
import { encodeViewId16, decodeViewId16, encodeViewId, decodeViewIdBits } from '../src/unity/view-id.js';
import { BitStream } from '../src/bitstream.js';
import { decodeQueryReply } from '../src/master/serialization.js';
import {
  encodeRpcSubsequent,
  encodeRpcFirstUse,
  decodeRpc,
  isRpc,
  learnMethodIndex,
  registerMethodIndices,
  registerMethodTag,
  registerMethodTags,
  resetTagMismatchWarnings,
  hasMethodIndex,
  encodeBatchIndex,
  decodeBatchIndex,
  MSG_ID_BATCH_INDEX,
  RpcMode,
} from '../src/unity/rpc.js';
import {
  encodeStateSync,
  decodeStateSync,
  encodeDeltaStateSync,
  decodeDeltaStateSync,
} from '../src/unity/state-sync.js';

function bytesToHex(bytes: Uint8Array): string {
  let hex = '';
  for (let i = 0; i < bytes.length; i++) {
    hex += (bytes[i] ?? 0).toString(16).padStart(2, '0');
  }
  return hex;
}

function hexToBytes(hex: string): Uint8Array {
  const out = new Uint8Array(hex.length / 2);
  for (let i = 0; i < out.length; i++) out[i] = parseInt(hex.slice(i * 2, i * 2 + 2), 16);
  return out;
}

describe('Batch Index (0x07)', () => {
  it('encode/decode round-trips for RPC_Int', () => {
    const idx = 0x60;
    const { data } = encodeBatchIndex('RPC_Int', idx);
    expect(data[0]).toBe(MSG_ID_BATCH_INDEX);
    const decoded = decodeBatchIndex(data);
    expect(decoded).not.toBeNull();
    expect(decoded!.methodName).toBe('RPC_Int');
    expect(decoded!.methodIndex).toBe(idx);
  });

  it('encode/decode round-trips for multiple methods', () => {
    const methods = [
      ['RPC_Int', 4],
      ['RPC_Float', 8],
      ['RPC_String', 12],
      ['RPC_Void', 16],
    ] as const;
    for (const [name, idx] of methods) {
      const { data } = encodeBatchIndex(name, idx);
      const decoded = decodeBatchIndex(data);
      expect(decoded).not.toBeNull();
      expect(decoded!.methodName).toBe(name);
      expect(decoded!.methodIndex).toBe(idx);
    }
  });

  it('returns null for non-0x07 payload', () => {
    expect(decodeBatchIndex(new Uint8Array([0x1b, 0, 0, 0, 0, 0]))).toBeNull();
  });

  it('returns null for too-short payload', () => {
    expect(decodeBatchIndex(new Uint8Array([0x07, 0, 0]))).toBeNull();
  });

  it('method_index 5-bit range works', () => {
    const { data } = encodeBatchIndex('RPC_Int', 124);
    const decoded = decodeBatchIndex(data);
    expect(decoded!.methodIndex).toBe(124);
  });

  // Real msg_id 0x07 frames captured from a live Distance client session
  // (reference-server capture, packet indices 19 and 21). Verifies the
  // header before classGuid is 31 bits with no separate flag bit, not
  // 32 bits + 1 flag bit — an earlier framing bug silently corrupted every
  // client-sent batch-index registration, so `peerIndices` never populated.
  //
  // methodIndex values below were recomputed 2026-07-13 after discovering
  // decodeBatchIndex itself had a second, independent bug: it read 5 bits
  // starting 1 bit too early (landing partly on hash-adjacent bits) instead
  // of the frame's actual index field (the low 7 bits of the final byte).
  // The previous values here (84/56/52) were themselves misparse artifacts;
  // see docs/research/2026-07-13-batch-index-decoder-was-broken.md.
  it('decodes real captured batch-index frames from a Distance client', () => {
    registerMethodNames([
      'ReceiveClientToServerEvent',
      'ReceiveBroadcastAllEvent',
      'ReceiveSerializeEvent',
      'ReceiveServerToClientEvent',
      'ReceiveTargetedEventServerToClient',
      'SubmitServerNetworkTimeSync',
      'ReceiveServerNetworkTimeSync',
    ]);

    const cases = [
      {
        raw: '070000005c190501278a93666161cab4f057560ccf19a944ed9202b554',
        name: 'ReceiveTargetedEventServerToClient',
        classGuid: '0c828093c549',
        methodHash: 'b330b0e55a782bab06678cd4a276c9015a',
        methodIndex: 84,
      },
      {
        raw: '0700000050558b3f44bab06678c9885d3197f524d05595950ae8',
        name: 'SubmitServerNetworkTimeSync',
        classGuid: '2ac59fa25d58',
        methodHash: '333c64c42e98cbfa92682acaca85',
        methodIndex: 104,
      },
      {
        raw: '07000000481905012789db24057528ab06678caad3c15ad4',
        name: 'ReceiveClientToServerEvent',
        classGuid: '0c828093c4ed',
        methodHash: '9202ba94558333c65569e0ad',
        methodIndex: 84,
      },
    ] as const;

    for (const c of cases) {
      const decoded = decodeBatchIndex(hexToBytes(c.raw));
      expect(decoded).not.toBeNull();
      expect(decoded!.methodName).toBe(c.name);
      expect(decoded!.methodIndex).toBe(c.methodIndex);

      const { classGuid, methodHash } = computeMethodId(c.name);
      expect(bytesToHex(classGuid)).toBe(c.classGuid);
      expect(bytesToHex(methodHash)).toBe(c.methodHash);
    }
  });

  it('disambiguates batch-index for methods with the same methodHash but different classGuid', () => {
    registerMethodNames([
      'SubmitServerNetworkTimeSync',
      'ReceiveServerNetworkTimeSync',
    ]);

    const submitId = computeMethodId('SubmitServerNetworkTimeSync');
    const receiveId = computeMethodId('ReceiveServerNetworkTimeSync');
    expect(bytesToHex(submitId.methodHash)).toBe(bytesToHex(receiveId.methodHash));
    expect(bytesToHex(submitId.classGuid)).not.toBe(bytesToHex(receiveId.classGuid));

    const submitBatch = encodeBatchIndex('SubmitServerNetworkTimeSync', 104);
    const receiveBatch = encodeBatchIndex('ReceiveServerNetworkTimeSync', 80);

    const decodedSubmit = decodeBatchIndex(submitBatch.data);
    expect(decodedSubmit).not.toBeNull();
    expect(decodedSubmit!.methodName).toBe('SubmitServerNetworkTimeSync');
    expect(decodedSubmit!.methodIndex).toBe(104);

    const decodedReceive = decodeBatchIndex(receiveBatch.data);
    expect(decodedReceive).not.toBeNull();
    expect(decodedReceive!.methodName).toBe('ReceiveServerNetworkTimeSync');
    expect(decodedReceive!.methodIndex).toBe(80);
  });

  // Real msg_id 0x07 frames from captures/IndexSweep-20260712-235647.pcap
  // and captures/CrossBinary-20260628-004945.pcap, decoded bit-by-bit by
  // hand (not via this repo's own encoder) to derive the true field
  // independent of any of this repo's prior (wrong) assumptions. The
  // sub-128 cases are end-aligned (last byte & 0x7F); the >=128 cases use
  // a 5-bit quotient spread across non-contiguous tail-bit positions (see
  // encodeBatchIndex's doc comment) — this test set only exercises the
  // low end of that range (128-140); see the large-delta test below for
  // higher values. Both verified 2026-07-13; see
  // docs/research/2026-07-13-batch-index-decoder-was-broken.md.
  it('decodes real IndexSweep batch-index frames (sub-128 index)', () => {
    const cases = [
      { raw: '0700000024192764edab62abd08e5c', name: 'RPC_Void', methodIndex: 92 },
      { raw: '0700000020192764edab63a8ad60', name: 'RPC_Int', methodIndex: 96 },
      { raw: '0700000024192764edab62ac9435e4', name: 'RPC_Float', methodIndex: 100 },
      { raw: '0700000028192764edab63565e50a668', name: 'RPC_String', methodIndex: 104 },
      { raw: '0700000030192764edab62abc28b8cabc16c', name: 'RPC_Vector3', methodIndex: 108 },
      { raw: '0700000030192764edab62abb5b58c924170', name: 'RPC_Quaternion', methodIndex: 112 },
      { raw: '0700000028192764edab6350aec6d5f4', name: 'RPC_Bytes', methodIndex: 116 },
      { raw: '070000003c192764edab63a8ad59286bab2f285378', name: 'RPC_IntFloatString', methodIndex: 120 },
      { raw: '070000003c192764edab6262174c65fcec935632fc', name: 'RPC_NetworkPlayer', methodIndex: 124 },
    ] as const;

    for (const c of cases) {
      const decoded = decodeBatchIndex(hexToBytes(c.raw));
      expect(decoded).not.toBeNull();
      expect(decoded!.methodIndex).toBe(c.methodIndex);
    }
  });

  it('decodes real IndexSweep batch-index frames (>=128 extended index)', () => {
    const cases = [
      { raw: '0700000040192764edab6262174c65faaf20a7519d0400', methodIndex: 128 },
      { raw: '0700000028192764edab62a92530ca8440', methodIndex: 132 },
      { raw: '0700000024192764edab635016ca8480', methodIndex: 136 },
      { raw: '0700000028192764edab62ad369a3284c0', methodIndex: 140 },
    ] as const;

    for (const c of cases) {
      const decoded = decodeBatchIndex(hexToBytes(c.raw));
      expect(decoded).not.toBeNull();
      expect(decoded!.methodIndex).toBe(c.methodIndex);
    }
  });

  it('decodes real CrossBinary batch-index frames from both build sides', () => {
    const cases = [
      { raw: '0700000020192764edab63a8ad60', methodIndex: 96 },
      { raw: '0700000020192764edab63a8ad6c', methodIndex: 108 },
      { raw: '0700000024192764edab62ac9435e4', methodIndex: 100 },
      { raw: '0700000024192764edab62ac9435f0', methodIndex: 112 },
      { raw: '0700000028192764edab63565e50a668', methodIndex: 104 },
      { raw: '0700000028192764edab63565e50a674', methodIndex: 116 },
    ] as const;

    for (const c of cases) {
      const decoded = decodeBatchIndex(hexToBytes(c.raw));
      expect(decoded).not.toBeNull();
      expect(decoded!.methodIndex).toBe(c.methodIndex);
    }
  });

  // Real msg_id 0x07 frames from captures/LargeDelta-20260713-031337.pcap,
  // spanning method_index 160-232 — well past the old (wrong) 128-140
  // ceiling. These fit the 5-bit non-contiguous quotient formula (extending
  // the representable range to 252) and were used to verify the Python
  // codec fix in protocol/unity_protocol.py; mirrored here for TS parity.
  // See docs/plans/large-delta-cross-assembly-index-test.md.
  it('decodes real LargeDelta batch-index frames spanning the extended (>140) range', () => {
    const cases = [
      { raw: '0700000030192764edab62abb5b58c92410600', methodIndex: 160 },
      { raw: '0700000028192764edab6350aec6d58640', methodIndex: 164 },
      { raw: '070000003c192764edab63a8ad59286bab2f28530740', methodIndex: 180 },
      { raw: '070000003c192764edab6262174c65fcec93563287c0', methodIndex: 188 },
      { raw: '0700000040192764edab6262174c65faaf20a7519d0940', methodIndex: 212 },
      { raw: '0700000028192764edab62a92530ca8980', methodIndex: 216 },
      { raw: '0700000024192764edab635016ca8a40', methodIndex: 228 },
      { raw: '0700000028192764edab62ad369a328a80', methodIndex: 232 },
    ] as const;

    for (const c of cases) {
      const decoded = decodeBatchIndex(hexToBytes(c.raw));
      expect(decoded).not.toBeNull();
      expect(decoded!.methodIndex).toBe(c.methodIndex);
    }
  });

  it('encode/decode round-trips across the extended (>140) range', () => {
    for (const idx of [144, 160, 200, 252]) {
      const { data } = encodeBatchIndex('RPC_Int', idx);
      const decoded = decodeBatchIndex(data);
      expect(decoded).not.toBeNull();
      expect(decoded!.methodIndex).toBe(idx);
    }
  });

  it('encodeBatchIndex rejects indices past the confirmed tail-encoding range', () => {
    expect(() => encodeBatchIndex('RPC_Int', 256)).toThrow();
    expect(() => encodeBatchIndex('RPC_Int', 97)).toThrow(); // not a multiple of 4
  });
});

describe('ViewID', () => {
  it('encodes scene ViewID as 16-bit', () => {
    expect(encodeViewId16('scene', 1)).toBe(4); // 1 << 2
    expect(encodeViewId16('scene', 0)).toBe(0);
  });

  it('encodes allocated ViewID as 16-bit', () => {
    const val = encodeViewId16('allocated', 1);
    expect(val & 0x4000).toBe(0x4000);
    expect((val & 0x3fff) >> 6).toBe(1);
  });

  it('round-trips 16-bit ViewID', () => {
    const cases: Array<{ scope: 'scene' | 'allocated'; id: number }> = [
      { scope: 'scene', id: 0 },
      { scope: 'scene', id: 1 },
      { scope: 'scene', id: 100 },
      { scope: 'allocated', id: 1 },
      { scope: 'allocated', id: 50 },
    ];
    for (const c of cases) {
      const encoded = encodeViewId16(c.scope, c.id);
      const decoded = decodeViewId16(encoded);
      expect(decoded.scope).toBe(c.scope);
      expect(decoded.id).toBe(c.id);
    }
  });

  it('encodes 48-bit ViewID', () => {
    const result = encodeViewId(1);
    expect(result.length).toBe(6);
    expect(result[5]).toBe(1);
  });
});

describe('Method Hash', () => {
  it('computes class GUID for RPC_Int', () => {
    const { classGuid } = computeMethodId('RPC_Int');
    expect(bytesToHex(classGuid)).toBe('0c93b276d5b1');
  });

  it('computes method hash for RPC_Int', () => {
    const { methodHash } = computeMethodId('RPC_Int');
    expect(bytesToHex(methodHash)).toBe('d456');
  });

  it('computes method index from RID', () => {
    expect(computeMethodIndex(29, 7)).toBe(0x54); // (29-1-7)*4 = 84 = 0x54
    expect(computeMethodIndex(30, 7)).toBe(0x58); // (30-1-7)*4 = 88 = 0x58
  });

  it('class GUID is consistent across methods', () => {
    const { classGuid: g1 } = computeMethodId('RPC_Int');
    const { classGuid: g2 } = computeMethodId('RPC_Float');
    expect(bytesToHex(g1)).toBe(bytesToHex(g2));
  });
});

describe('RPC Encode/Decode', () => {
  it('encodes and decodes a subsequent-use RPC', () => {
    const encoded = encodeRpcSubsequent({
      methodName: 'RPC_Int',
      params: [{ type: 'int', value: 42 }],
      timestampMs: 0,
      mode: RpcMode.Server,
      targetView: 0x2000,
    });

    expect(encoded.bitLength).toBeGreaterThan(0);
    expect(encoded.data[0]).toBe(0x1b);

    const decoded = decodeRpc(encoded.data, encoded.bitLength);
    expect(decoded.methodName).toBe('RPC_Int');
    expect(decoded.timestampMs).toBe(0);
    expect(decoded.rpcMode).toBe('Server');
    expect(decoded.firstUse).toBe(false);
    expect(decoded.params).toEqual([42]);
    expect(decoded.methodIndex).toBeDefined();
  });

  it('subsequent-use decode returns methodIndex', () => {
    const encoded = encodeRpcSubsequent({
      methodName: 'RPC_Void',
      params: [],
      timestampMs: 0,
      mode: RpcMode.Server,
      targetView: 0x2000,
    });
    const decoded = decodeRpc(encoded.data, encoded.bitLength);
    expect(decoded.methodIndex).toBeDefined();
    expect(decoded.methodName).toBe('RPC_Void');
  });

  it('first-use decode has no methodIndex', () => {
    const encoded = encodeRpcFirstUse({
      methodName: 'RPC_Void',
      params: [],
      timestampMs: 0,
      mode: RpcMode.Server,
      targetView: 0x2000,
    });
    const decoded = decodeRpc(encoded.data, encoded.bitLength);
    expect(decoded.methodIndex).toBeUndefined();
    expect(decoded.firstUse).toBe(true);
  });

  it('learnMethodIndex registers unknown index for future decoding', () => {
    const fakeIndex = 0x04;
    learnMethodIndex('TestDynamic', fakeIndex);
    const encoded = encodeRpcSubsequent({
      methodName: 'TestDynamic',
      params: [],
      timestampMs: 0,
      mode: RpcMode.Server,
      targetView: 0x2000,
    });
    const decoded = decodeRpc(encoded.data, encoded.bitLength);
    expect(decoded.methodName).toBe('TestDynamic');
    expect(decoded.methodIndex).toBe(fakeIndex);
  });

  it('encodes and decodes a first-use RPC', () => {
    const encoded = encodeRpcFirstUse({
      methodName: 'RPC_Float',
      params: [{ type: 'float', value: 3.14 }],
      timestampMs: 1,
      mode: RpcMode.All,
      targetView: 0x2000,
    });

    expect(encoded.data[0]).toBe(0x1b);

    const decoded = decodeRpc(encoded.data, encoded.bitLength);
    expect(decoded.methodName).toBe('RPC_Float');
    expect(decoded.rpcMode).toBe('All');
    expect(decoded.firstUse).toBe(true);
    expect(decoded.params[0]).toBeCloseTo(3.14, 5);
  });

  it('isRpc returns true for RPC packets', () => {
    const encoded = encodeRpcSubsequent({
      methodName: 'RPC_Void',
      params: [],
      timestampMs: 0,
      mode: RpcMode.Server,
      targetView: 0x2000,
    });
    expect(isRpc(encoded.data)).toBe(true);
  });

  it('correctly encodes RPC counter', () => {
    const encoded = encodeRpcSubsequent({
      methodName: 'RPC_Int',
      params: [{ type: 'int', value: 0 }],
      timestampMs: 5,
      mode: RpcMode.Server,
      targetView: 0x2000,
    });
    const decoded = decodeRpc(encoded.data, encoded.bitLength);
    expect(decoded.timestampMs).toBe(5);
  });

  it('round-trips int param', () => {
    const encoded = encodeRpcSubsequent({
      methodName: 'RPC_Int',
      params: [{ type: 'int', value: -42 }],
      timestampMs: 0,
      mode: RpcMode.Server,
      targetView: 0x2000,
    });
    const decoded = decodeRpc(encoded.data, encoded.bitLength);
    expect(decoded.params).toEqual([-42]);
  });

  it('round-trips float param', () => {
    const encoded = encodeRpcSubsequent({
      methodName: 'RPC_Float',
      params: [{ type: 'float', value: -1.5 }],
      timestampMs: 0,
      mode: RpcMode.Server,
      targetView: 0x2000,
    });
    const decoded = decodeRpc(encoded.data, encoded.bitLength);
    expect(decoded.params[0]).toBeCloseTo(-1.5);
  });

  it('round-trips string param', () => {
    const encoded = encodeRpcSubsequent({
      methodName: 'RPC_String',
      params: [{ type: 'string', value: 'hello world' }],
      timestampMs: 0,
      mode: RpcMode.Server,
      targetView: 0x2000,
    });
    const decoded = decodeRpc(encoded.data, encoded.bitLength);
    expect(decoded.params).toEqual(['hello world']);
  });

  it('round-trips empty string param', () => {
    const encoded = encodeRpcSubsequent({
      methodName: 'RPC_String',
      params: [{ type: 'string', value: '' }],
      timestampMs: 0,
      mode: RpcMode.Server,
      targetView: 0x2000,
    });
    const decoded = decodeRpc(encoded.data, encoded.bitLength);
    expect(decoded.params).toEqual(['']);
  });

  it('round-trips Vector3 param', () => {
    const encoded = encodeRpcSubsequent({
      methodName: 'RPC_Vector3',
      params: [{ type: 'Vector3', value: [1.5, -2.5, 3.0] }],
      timestampMs: 0,
      mode: RpcMode.Server,
      targetView: 0x2000,
    });
    const decoded = decodeRpc(encoded.data, encoded.bitLength);
    const v = decoded.params[0] as number[];
    expect(v[0]).toBeCloseTo(1.5);
    expect(v[1]).toBeCloseTo(-2.5);
    expect(v[2]).toBeCloseTo(3.0);
  });

  it('round-trips Quaternion param', () => {
    const encoded = encodeRpcSubsequent({
      methodName: 'RPC_Quaternion',
      params: [{ type: 'Quaternion', value: [0.1, 0.2, 0.3, 0.9] }],
      timestampMs: 0,
      mode: RpcMode.Server,
      targetView: 0x2000,
    });
    const decoded = decodeRpc(encoded.data, encoded.bitLength);
    const q = decoded.params[0] as number[];
    expect(q[0]).toBeCloseTo(0.1, 5);
    expect(q[1]).toBeCloseTo(0.2, 5);
    expect(q[2]).toBeCloseTo(0.3, 5);
    expect(q[3]).toBeCloseTo(0.9, 5);
  });

  it('round-trips bytes param', () => {
    const encoded = encodeRpcSubsequent({
      methodName: 'RPC_Bytes',
      params: [{ type: 'bytes', value: new Uint8Array([0xde, 0xad, 0xbe, 0xef]) }],
      timestampMs: 0,
      mode: RpcMode.Server,
      targetView: 0x2000,
    });
    const decoded = decodeRpc(encoded.data, encoded.bitLength);
    expect(decoded.params[0]).toEqual(new Uint8Array([0xde, 0xad, 0xbe, 0xef]));
  });

  it('round-trips empty bytes param', () => {
    const encoded = encodeRpcSubsequent({
      methodName: 'RPC_Bytes',
      params: [{ type: 'bytes', value: new Uint8Array(0) }],
      timestampMs: 0,
      mode: RpcMode.Server,
      targetView: 0x2000,
    });
    const decoded = decodeRpc(encoded.data, encoded.bitLength);
    expect(decoded.params[0]).toEqual(new Uint8Array(0));
  });

  it('round-trips NetworkViewID param', () => {
    const encoded = encodeRpcSubsequent({
      methodName: 'RPC_NetworkViewID',
      params: [{ type: 'NetworkViewID', value: 42 }],
      timestampMs: 0,
      mode: RpcMode.Server,
      targetView: 0x2000,
    });
    const decoded = decodeRpc(encoded.data, encoded.bitLength);
    expect(decoded.params).toEqual([42]);
  });

  it('round-trips NetworkPlayer param', () => {
    const encoded = encodeRpcSubsequent({
      methodName: 'RPC_NetworkPlayer',
      params: [{ type: 'NetworkPlayer', value: 7 }],
      timestampMs: 0,
      mode: RpcMode.Server,
      targetView: 0x2000,
    });
    const decoded = decodeRpc(encoded.data, encoded.bitLength);
    expect(decoded.params).toEqual([7]);
  });

  it('round-trips multi-param RPC (int, float, string)', () => {
    const encoded = encodeRpcSubsequent({
      methodName: 'RPC_IntFloatString',
      params: [
        { type: 'int', value: 100 },
        { type: 'float', value: 2.5 },
        { type: 'string', value: 'test' },
      ],
      timestampMs: 0,
      mode: RpcMode.Server,
      targetView: 0x2000,
    });
    const decoded = decodeRpc(encoded.data, encoded.bitLength);
    expect(decoded.params[0]).toBe(100);
    expect(decoded.params[1]).toBeCloseTo(2.5);
    expect(decoded.params[2]).toBe('test');
  });

  it('round-trips void RPC (no params)', () => {
    const encoded = encodeRpcSubsequent({
      methodName: 'RPC_Void',
      params: [],
      timestampMs: 0,
      mode: RpcMode.Server,
      targetView: 0x2000,
    });
    const decoded = decodeRpc(encoded.data, encoded.bitLength);
    expect(decoded.params).toEqual([]);
  });

  it('first-use param decoding works', () => {
    const encoded = encodeRpcFirstUse({
      methodName: 'RPC_IntFloatString',
      params: [
        { type: 'int', value: -1 },
        { type: 'float', value: 0.5 },
        { type: 'string', value: 'abc' },
      ],
      timestampMs: 0,
      mode: RpcMode.All,
      targetView: 0x2000,
    });
    const decoded = decodeRpc(encoded.data, encoded.bitLength);
    expect(decoded.methodName).toBe('RPC_IntFloatString');
    expect(decoded.firstUse).toBe(true);
    expect(decoded.params[0]).toBe(-1);
    expect(decoded.params[1]).toBeCloseTo(0.5);
    expect(decoded.params[2]).toBe('abc');
  });

  it('Player mode skips target bit before params', () => {
    const encoded = encodeRpcSubsequent({
      methodName: 'RPC_Int',
      params: [{ type: 'int', value: 99 }],
      timestampMs: 0,
      mode: RpcMode.Player,
      targetView: 0x2000,
    });
    const decoded = decodeRpc(encoded.data, encoded.bitLength);
    expect(decoded.rpcMode).toBe('Player');
    expect(decoded.params).toEqual([99]);
  });

  it('round-trips u64 timestamp > 65535', () => {
    const ts = 200000;
    const encoded = encodeRpcSubsequent({
      methodName: 'RPC_Void',
      params: [],
      timestampMs: ts,
      mode: RpcMode.Server,
      targetView: 0x2000,
    });
    const decoded = decodeRpc(encoded.data, encoded.bitLength);
    expect(decoded.timestampMs).toBe(ts);
  });

  it('unknown method returns empty params without throwing', () => {
    const encoded = encodeRpcSubsequent({
      methodName: 'RPC_Void',
      params: [],
      timestampMs: 0,
      mode: RpcMode.Server,
      targetView: 0x2000,
    });
    // Corrupt the method index byte (byte 10, which contains the 1-bit first_use flag + 7-bit index)
    // Set to a method index that doesn't exist (0xfe = index 0xfe)
    encoded.data[10] = 0x7f; // first_use=0, index bits = 0xfe
    const decoded = decodeRpc(encoded.data, encoded.bitLength);
    expect(decoded.methodName).toMatch(/^unknown_0x/);
    expect(decoded.params).toEqual([]);
  });
});

// Reads the 4-bit method_tag out of a first-use RPC payload without going
// through decodeRpc (which doesn't expose it — tag is dispatch-time only).
function extractFirstUseTag(data: Uint8Array, bitLength: number): number {
  const bs = new BitStream(data, bitLength);
  bs.pos = 104;
  const lengthIndicator = bs.readU8();
  const methodIdBits = lengthIndicator * 4;
  const hashExtraBits = methodIdBits - 48;
  bs.pos = 160 + hashExtraBits;
  return bs.readBits(4);
}

// Shared with tests/test_unity_protocol.py (Python) so the two encoders
// can't silently drift apart — see
// docs/research/fixtures/method-tag-conformance.json.
const FIXTURE_PATH = join(
  dirname(fileURLToPath(import.meta.url)),
  '..', '..', 'docs', 'research', 'fixtures', 'method-tag-conformance.json',
);
interface MethodTagFixture {
  entries: { name: string; tag: number }[];
}
const METHOD_TAG_FIXTURE = JSON.parse(
  readFileSync(FIXTURE_PATH, 'utf8'),
) as MethodTagFixture;

describe('method_tag registration', () => {
  it('built-in Loader assembly tags match the ground-truth capture', () => {
    expect(METHOD_TAG_FIXTURE.entries.length).toBe(25);
    for (const { name, tag } of METHOD_TAG_FIXTURE.entries) {
      const encoded = encodeRpcFirstUse({
        methodName: name,
        params: [],
        timestampMs: 0,
        mode: RpcMode.Server,
        targetView: 0x2000,
      });
      expect(extractFirstUseTag(encoded.data, encoded.bitLength)).toBe(tag);
    }
  });

  it('registerMethodTag sets only the tag, not the method index', () => {
    expect(hasMethodIndex('RPC_TagOnly')).toBe(false);
    registerMethodTag('RPC_TagOnly', 12);
    expect(hasMethodIndex('RPC_TagOnly')).toBe(false);

    const encoded = encodeRpcFirstUse({
      methodName: 'RPC_TagOnly',
      params: [],
      timestampMs: 0,
      mode: RpcMode.Server,
      targetView: 0x2000,
    });
    expect(extractFirstUseTag(encoded.data, encoded.bitLength)).toBe(12);
  });

  it('registerMethodTags sets tags for multiple methods at once', () => {
    registerMethodTags({ RPC_BulkA: 4, RPC_BulkB: 12 });

    const a = encodeRpcFirstUse({
      methodName: 'RPC_BulkA', params: [], timestampMs: 0,
      mode: RpcMode.Server, targetView: 0x2000,
    });
    const b = encodeRpcFirstUse({
      methodName: 'RPC_BulkB', params: [], timestampMs: 0,
      mode: RpcMode.Server, targetView: 0x2000,
    });
    expect(extractFirstUseTag(a.data, a.bitLength)).toBe(4);
    expect(extractFirstUseTag(b.data, b.bitLength)).toBe(12);
  });

  it('registerMethodIndices/learnMethodIndex do not derive a tag', () => {
    registerMethodIndices({ RPC_IndexOnly: 0xf0 });
    expect(hasMethodIndex('RPC_IndexOnly')).toBe(true);

    resetTagMismatchWarnings();
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    try {
      const encoded = encodeRpcFirstUse({
        methodName: 'RPC_IndexOnly', params: [], timestampMs: 0,
        mode: RpcMode.Server, targetView: 0x2000,
      });
      expect(extractFirstUseTag(encoded.data, encoded.bitLength))
        .toBe(computeMethodTag('RPC_IndexOnly'));
      expect(warnSpy).not.toHaveBeenCalled();
    } finally {
      warnSpy.mockRestore();
    }
  });

  it('an override that diverges from computeMethodTag wins on the wire and warns once', () => {
    resetTagMismatchWarnings();
    const computed = computeMethodTag('RPC_MismatchTag');
    registerMethodTag('RPC_MismatchTag', computed ^ 0x4);
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    try {
      const encoded = encodeRpcFirstUse({
        methodName: 'RPC_MismatchTag', params: [], timestampMs: 0,
        mode: RpcMode.Server, targetView: 0x2000,
      });
      expect(extractFirstUseTag(encoded.data, encoded.bitLength)).toBe(computed ^ 0x4);
      expect(warnSpy).toHaveBeenCalledTimes(1);

      // Second encode: same divergent override, warning is one-time.
      encodeRpcFirstUse({
        methodName: 'RPC_MismatchTag', params: [], timestampMs: 0,
        mode: RpcMode.Server, targetView: 0x2000,
      });
      expect(warnSpy).toHaveBeenCalledTimes(1);
    } finally {
      warnSpy.mockRestore();
    }
  });

  it('an override matching computeMethodTag is a no-op on the wire and never warns', () => {
    resetTagMismatchWarnings();
    const computed = computeMethodTag('RPC_MatchingTag');
    registerMethodTag('RPC_MatchingTag', computed);
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    try {
      const encoded = encodeRpcFirstUse({
        methodName: 'RPC_MatchingTag', params: [], timestampMs: 0,
        mode: RpcMode.Server, targetView: 0x2000,
      });
      expect(extractFirstUseTag(encoded.data, encoded.bitLength)).toBe(computed);
      expect(warnSpy).not.toHaveBeenCalled();
    } finally {
      warnSpy.mockRestore();
    }
  });
});

describe('State Sync', () => {
  it('encodes and decodes a state sync message', () => {
    const encoded = encodeStateSync({
      viewId: { scope: 'scene', id: 1 },
      timestampMs: 100,
      fields: [{ type: 'float', value: 1.5 }],
      isFirst: false,
    });

    expect(encoded.data[0]).toBe(0x1b);
    expect(encoded.bitLength).toBe(96 + 32);

    const decoded = decodeStateSync(encoded.data, encoded.bitLength);
    expect(decoded.timestampMs).toBe(100);
    expect(decoded.isFirst).toBe(false);
    expect(decoded.viewIdScope).toBe('scene');
    expect(decoded.viewId).toBe(1);
  });

  it('encodes first state sync with 0x80 flag', () => {
    const encoded = encodeStateSync({
      viewId: { scope: 'scene', id: 1 },
      timestampMs: 0,
      fields: [{ type: 'int', value: 42 }],
      isFirst: true,
    });

    const decoded = decodeStateSync(encoded.data, encoded.bitLength);
    expect(decoded.isFirst).toBe(true);
  });
});

describe('Delta State Sync', () => {
  it('encodes and decodes delta sync', () => {
    const encoded = encodeDeltaStateSync({
      viewId: { scope: 'scene', id: 1 },
      timestampMs: 200,
      fieldValues: [100, 200],
      prevValues: [100, 100],
      fieldWidths: [32, 32],
      isFirst: false,
    });

    const decoded = decodeDeltaStateSync(encoded.data, encoded.bitLength, 2, [32, 32], [100, 100]);

    expect(decoded.timestampMs).toBe(200);
    expect(decoded.dirtyFlags).toEqual([0, 1]);
    expect(decoded.fieldValues).toEqual([100, 200]);
  });

  it('no dirty fields produces minimal output', () => {
    const encoded = encodeDeltaStateSync({
      viewId: { scope: 'scene', id: 1 },
      timestampMs: 0,
      fieldValues: [42, 43],
      prevValues: [42, 43],
      fieldWidths: [32, 32],
      isFirst: false,
    });

    expect(encoded.bitLength).toBe(96 + 2); // header + 2 dirty bits (both 0)
  });
});

describe('RPC u64 timestamp', () => {
  it('round-trips various timestamp values including > 65535', () => {
    const encode = (ts: number): ReturnType<typeof encodeRpcSubsequent> =>
      encodeRpcSubsequent({
        methodName: 'RPC_Int',
        params: [{ type: 'int', value: 1 }],
        timestampMs: ts,
        mode: RpcMode.Server,
        targetView: 0x2000,
      });

    const cases = [0, 127, 128, 32767, 32768, 65535, 65536, 100000, 200000, 955000];
    for (const ts of cases) {
      const r = encode(ts);
      expect(decodeRpc(r.data, r.bitLength).timestampMs).toBe(ts);
    }
  });

  it('timestamp values 0-500 all encode/decode correctly', () => {
    for (let i = 0; i <= 500; i++) {
      const result = encodeRpcSubsequent({
        methodName: 'RPC_Void',
        params: [],
        timestampMs: i,
        mode: RpcMode.Server,
        targetView: 0x2000,
      });
      const decoded = decodeRpc(result.data, result.bitLength);
      expect(decoded.timestampMs).toBe(i);
      expect(decoded.methodName).toBe('RPC_Void');
    }
  });

  it('first-use encoding also wraps counter correctly', () => {
    const r200 = encodeRpcFirstUse({
      methodName: 'RPC_String',
      params: [{ type: 'string', value: 'test' }],
      timestampMs: 200,
      mode: RpcMode.All,
      targetView: 0x2000,
    });
    const decoded = decodeRpc(r200.data, r200.bitLength);
    expect(decoded.timestampMs).toBe(200);
    expect(decoded.params[0]).toBe('test');
  });
});

describe('Float edge values', () => {
  it('encodes/decodes NaN in RPC float param', () => {
    const result = encodeRpcSubsequent({
      methodName: 'RPC_Float',
      params: [{ type: 'float', value: NaN }],
      timestampMs: 0,
      mode: RpcMode.Server,
      targetView: 0x2000,
    });
    const decoded = decodeRpc(result.data, result.bitLength);
    expect(decoded.params[0]).toBeNaN();
  });

  it('encodes/decodes Infinity in RPC float param', () => {
    const result = encodeRpcSubsequent({
      methodName: 'RPC_Float',
      params: [{ type: 'float', value: Infinity }],
      timestampMs: 0,
      mode: RpcMode.Server,
      targetView: 0x2000,
    });
    const decoded = decodeRpc(result.data, result.bitLength);
    expect(decoded.params[0]).toBe(Infinity);
  });

  it('encodes/decodes -Infinity in RPC float param', () => {
    const result = encodeRpcSubsequent({
      methodName: 'RPC_Float',
      params: [{ type: 'float', value: -Infinity }],
      timestampMs: 0,
      mode: RpcMode.Server,
      targetView: 0x2000,
    });
    const decoded = decodeRpc(result.data, result.bitLength);
    expect(decoded.params[0]).toBe(-Infinity);
  });

  it('encodes/decodes -0 in RPC float param', () => {
    const result = encodeRpcSubsequent({
      methodName: 'RPC_Float',
      params: [{ type: 'float', value: -0 }],
      timestampMs: 0,
      mode: RpcMode.Server,
      targetView: 0x2000,
    });
    const decoded = decodeRpc(result.data, result.bitLength);
    expect(Object.is(decoded.params[0], -0)).toBe(true);
  });

  it('encodes/decodes NaN in Vector3', () => {
    const result = encodeRpcSubsequent({
      methodName: 'RPC_Vector3',
      params: [{ type: 'Vector3', value: [NaN, 0, Infinity] }],
      timestampMs: 0,
      mode: RpcMode.Server,
      targetView: 0x2000,
    });
    const decoded = decodeRpc(result.data, result.bitLength);
    const vec = decoded.params[0] as number[];
    expect(vec[0]).toBeNaN();
    expect(vec[1]).toBe(0);
    expect(vec[2]).toBe(Infinity);
  });

  it('encodes/decodes denormalized float in RPC', () => {
    // Smallest positive float32 subnormal: ~1.4e-45
    const denorm = 1.401298464324817e-45;
    const result = encodeRpcSubsequent({
      methodName: 'RPC_Float',
      params: [{ type: 'float', value: denorm }],
      timestampMs: 0,
      mode: RpcMode.Server,
      targetView: 0x2000,
    });
    const decoded = decodeRpc(result.data, result.bitLength);
    expect(decoded.params[0]).toBeCloseTo(denorm, 50);
  });

  it('float edge values produce known IEEE 754 bytes (cross-language)', () => {
    // Must match Python test_float_edge_cross_language_bytes
    const cases: [number, string][] = [
      [NaN, '7fc00000'],
      [Infinity, '7f800000'],
      [-Infinity, 'ff800000'],
      [-0, '80000000'],
      [1.401298464324817e-45, '00000001'], // smallest subnormal
    ];
    for (const [val, expectedHex] of cases) {
      const buf = new ArrayBuffer(4);
      new DataView(buf).setFloat32(0, val);
      const hex = [...new Uint8Array(buf)].map(b => b.toString(16).padStart(2, '0')).join('');
      expect(hex).toBe(expectedHex);
    }
  });

  it('encodes float edge values in state sync without crashing', () => {
    const encoded = encodeStateSync({
      viewId: { scope: 'scene', id: 1 },
      timestampMs: 100,
      fields: [
        { type: 'float', value: NaN },
        { type: 'float', value: Infinity },
        { type: 'float', value: -0 },
      ],
      isFirst: true,
    });
    // decodeStateSync only decodes the header (no field schema),
    // so just verify encoding didn't crash and header is correct
    const decoded = decodeStateSync(encoded.data, encoded.bitLength);
    expect(decoded.viewId).toBe(1);
    expect(decoded.timestampMs).toBe(100);
    expect(decoded.isFirst).toBe(true);
  });
});

describe('Encoding edge cases', () => {
  it('encodes/decodes zero Vector3 (0,0,0)', () => {
    const result = encodeRpcSubsequent({
      methodName: 'RPC_Vector3',
      params: [{ type: 'Vector3', value: [0, 0, 0] }],
      timestampMs: 0,
      mode: RpcMode.Server,
      targetView: 0x2000,
    });
    const decoded = decodeRpc(result.data, result.bitLength);
    expect(decoded.params[0]).toEqual([0, 0, 0]);
  });

  it('encodes/decodes zero Quaternion (0,0,0,0)', () => {
    const result = encodeRpcSubsequent({
      methodName: 'RPC_Quaternion',
      params: [{ type: 'Quaternion', value: [0, 0, 0, 0] }],
      timestampMs: 0,
      mode: RpcMode.Server,
      targetView: 0x2000,
    });
    const decoded = decodeRpc(result.data, result.bitLength);
    expect(decoded.params[0]).toEqual([0, 0, 0, 0]);
  });

  it('encodes/decodes INT32_MIN and INT32_MAX in RPC', () => {
    const result = encodeRpcSubsequent({
      methodName: 'RPC_Int',
      params: [{ type: 'int', value: -2147483648 }],
      timestampMs: 0,
      mode: RpcMode.Server,
      targetView: 0x2000,
    });
    const decoded = decodeRpc(result.data, result.bitLength);
    expect(decoded.params[0]).toBe(-2147483648);

    const result2 = encodeRpcSubsequent({
      methodName: 'RPC_Int',
      params: [{ type: 'int', value: 2147483647 }],
      timestampMs: 1,
      mode: RpcMode.Server,
      targetView: 0x2000,
    });
    const decoded2 = decodeRpc(result2.data, result2.bitLength);
    expect(decoded2.params[0]).toBe(2147483647);
  });

  it('encodes/decodes empty byte array', () => {
    const result = encodeRpcSubsequent({
      methodName: 'RPC_Bytes',
      params: [{ type: 'bytes', value: new Uint8Array(0) }],
      timestampMs: 0,
      mode: RpcMode.Server,
      targetView: 0x2000,
    });
    const decoded = decodeRpc(result.data, result.bitLength);
    expect(decoded.params[0]).toEqual(new Uint8Array(0));
  });

  it('ViewID boundary: scene 0', () => {
    const encoded = encodeViewId16('scene', 0);
    const decoded = decodeViewId16(encoded);
    expect(decoded.scope).toBe('scene');
    expect(decoded.id).toBe(0);
  });

  it('ViewID boundary: max scene (4095)', () => {
    // scene encoding: id << 2, must not set bit 14 (0x4000)
    const encoded = encodeViewId16('scene', 4095);
    const decoded = decodeViewId16(encoded);
    expect(decoded.scope).toBe('scene');
    expect(decoded.id).toBe(4095);
  });

  it('ViewID boundary: allocated 0', () => {
    const encoded = encodeViewId16('allocated', 0);
    const decoded = decodeViewId16(encoded);
    expect(decoded.scope).toBe('allocated');
    expect(decoded.id).toBe(0);
  });

  it('ViewID boundary: allocated 255 (max)', () => {
    // allocated encoding: 0x4000 | (id << 6), id fits in 8 bits
    const encoded = encodeViewId16('allocated', 255);
    const decoded = decodeViewId16(encoded);
    expect(decoded.scope).toBe('allocated');
    expect(decoded.id).toBe(255);
  });

  it('encodeViewId16 throws on scene id > 4095', () => {
    expect(() => encodeViewId16('scene', 4096)).toThrow('out of range');
    expect(() => encodeViewId16('scene', -1)).toThrow('out of range');
  });

  it('encodeViewId16 throws on allocated id > 255', () => {
    expect(() => encodeViewId16('allocated', 256)).toThrow('out of range');
    expect(() => encodeViewId16('allocated', -1)).toThrow('out of range');
  });

  it('handles unknown method hash gracefully', () => {
    // Encode a first-use RPC, then tamper with the method hash bytes
    const result = encodeRpcFirstUse({
      methodName: 'RPC_Int',
      params: [{ type: 'int', value: 42 }],
      timestampMs: 0,
      mode: RpcMode.Server,
      targetView: 0x2000,
    });
    // Corrupt the method hash bytes (bytes after the length indicator)
    const data = new Uint8Array(result.data);
    for (let i = 14; i < 20; i++) {
      data[i] = 0xff;
    }
    const decoded = decodeRpc(data, result.bitLength);
    // Should decode without crashing; method name is 'unknown' or similar
    expect(decoded.timestampMs).toBe(0);
  });
});

describe('RPC modes and relay', () => {
  it('Others mode encodes mode=1 in wire format', () => {
    const encoded = encodeRpcSubsequent({
      methodName: 'RPC_Int',
      params: [{ type: 'int', value: 42 }],
      timestampMs: 0,
      mode: RpcMode.Others,
      targetView: 0x2000,
    });
    const decoded = decodeRpc(encoded.data, encoded.bitLength);
    expect(decoded.rpcMode).toBe('Others');
    expect(decoded.params).toEqual([42]);
  });

  it('All mode encodes mode=2 in wire format', () => {
    const encoded = encodeRpcSubsequent({
      methodName: 'RPC_Int',
      params: [{ type: 'int', value: 42 }],
      timestampMs: 0,
      mode: RpcMode.All,
      targetView: 0x2000,
    });
    const decoded = decodeRpc(encoded.data, encoded.bitLength);
    expect(decoded.rpcMode).toBe('All');
    expect(decoded.params).toEqual([42]);
  });

  it('relay=true adds exactly 5 bits to subsequent RPC', () => {
    const normal = encodeRpcSubsequent({
      methodName: 'RPC_Int',
      params: [{ type: 'int', value: 42 }],
      timestampMs: 0, mode: RpcMode.Others,
      targetView: 0x2000,
    });
    const relay = encodeRpcSubsequent({
      methodName: 'RPC_Int',
      params: [{ type: 'int', value: 42 }],
      timestampMs: 0, mode: RpcMode.Others, relay: true,
      targetView: 0x2000,
    });
    expect(relay.bitLength - normal.bitLength).toBe(5);
  });

  it('relay=true adds exactly 5 bits to first-use RPC', () => {
    const normal = encodeRpcFirstUse({
      methodName: 'RPC_Int',
      params: [{ type: 'int', value: 42 }],
      timestampMs: 0, mode: RpcMode.Others,
      targetView: 0x2000,
    });
    const relay = encodeRpcFirstUse({
      methodName: 'RPC_Int',
      params: [{ type: 'int', value: 42 }],
      timestampMs: 0, mode: RpcMode.Others, relay: true,
      targetView: 0x2000,
    });
    expect(relay.bitLength - normal.bitLength).toBe(5);
  });

  it('relay RPC still decodes correctly', () => {
    const relay = encodeRpcSubsequent({
      methodName: 'RPC_Int',
      params: [{ type: 'int', value: 42 }],
      timestampMs: 0, mode: RpcMode.Others, relay: true,
      targetView: 0x2000,
    });
    const decoded = decodeRpc(relay.data, relay.bitLength);
    expect(decoded.methodName).toBe('RPC_Int');
    expect(decoded.timestampMs).toBe(0);
    expect(decoded.rpcMode).toBe('Others');
  });

  it('targetView encodes in wire format', () => {
    const encoded = encodeRpcSubsequent({
      methodName: 'RPC_Int',
      params: [{ type: 'int', value: 42 }],
      timestampMs: 0, mode: RpcMode.Server,
      targetView: 0x2640,
    });
    const bits = [...encoded.data].map(b => b.toString(2).padStart(8, '0')).join('');
    const constVal = parseInt(bits.slice(120, 136), 2);
    expect(constVal).toBe(0x2640);
  });
});

describe('Malformed packet resilience', () => {
  it('decodeRpc throws BitStreamError on truncated payload', () => {
    expect(() => decodeRpc(new Uint8Array([0x1b, 0x00]), 16)).toThrow();
  });

  it('decodeRpc throws BitStreamError on empty payload', () => {
    expect(() => decodeRpc(new Uint8Array(1), 8)).toThrow();
  });

  it('decodeStateSync handles 12-byte payload without crash', () => {
    // 12 bytes = 96 bits, enough for the full header
    const result = decodeStateSync(new Uint8Array(12), 96);
    expect(result).toBeDefined();
    expect(result.viewId).toBeDefined();
  });

  it('isRpc returns false for short payloads', () => {
    expect(isRpc(new Uint8Array([]))).toBe(false);
    expect(isRpc(new Uint8Array([0x1b]))).toBe(false);
    expect(isRpc(new Uint8Array([0x1b, 0, 0, 0, 0, 0, 0, 0, 0]))).toBe(false);
  });
});

describe('decodeViewIdBits 48-bit', () => {
  it('correctly decodes a 48-bit view ID without overflow', () => {
    const bs = new BitStream();
    bs.writeU16BE(0x0001);
    bs.writeU16BE(0x0000);
    bs.writeU16BE(0x0000);
    bs.pos = 0;
    const val = decodeViewIdBits(bs);
    expect(val).toBe(0x100000000);
  });
});

describe('bytes param size limit', () => {
  it('throws when bytes param count exceeds 1MB', () => {
    // Build an RPC_Bytes with a tiny payload, then tamper with the count
    const { data, bitLength } = encodeRpcSubsequent({
      methodName: 'RPC_Bytes',
      params: [{ type: 'bytes', value: new Uint8Array(0) }],
      timestampMs: 0,
      mode: RpcMode.Server,
      targetView: 0x2000,
    });
    // The count field is 4 bytes (u32 big-endian) right after the mode bits
    // Find the 4 zero bytes that represent count=0 and replace with a huge value
    const tampered = new Uint8Array(data.length + 4);
    tampered.set(data);
    // Decode the untampered version to confirm it works
    expect(() => decodeRpc(data, bitLength)).not.toThrow();

    // Manually construct a BitStream with a huge count in the params area
    // Navigate to where params start for a subsequent RPC_Bytes
    // Subsequent RPC format: 140 bits + params; params for bytes = u32(count) + data
    // The count is at bit offset 140
    const countOffset = 140;
    const tamperedBs = new BitStream();
    // Copy bits up to count
    const srcBs = new BitStream(data, bitLength);
    for (let i = 0; i < countOffset; i++) {
      tamperedBs.writeBit(srcBs.readBit());
    }
    // Write a huge count
    tamperedBs.writeU32BE(2_000_000);
    const tamperedData = tamperedBs.toBytes();
    expect(() => decodeRpc(tamperedData, tamperedBs.bitLength)).toThrow('bytes param too large');
  });
});

describe('decodeQueryReply cellIdx bounds', () => {
  it('throws on cellIdx >= columns.length', () => {
    // Build a reply with 1 column but cellIdx=5
    const bs = new BitStream();
    bs.writeU8(78); // ID_DATABASE_QUERY_REPLY
    bs.writeU32BE(1); // numColumns
    // column: name + type
    bs.writeCompressedU32(0); // empty string (0 bits)
    bs.writeU8(0); // NUMERIC
    bs.writeU32BE(1); // numRows
    bs.writeU32BE(0); // row key
    bs.writeU32BE(1); // numEntries
    bs.writeU32BE(5); // cellIdx = 5 (out of range!)
    const data = bs.toBytes();
    expect(() => decodeQueryReply(data)).toThrow('out of range');
  });
});
