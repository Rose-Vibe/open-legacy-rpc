import { describe, it, expect } from 'vitest';
import { computeMethodId, computeMethodIndex } from '../src/unity/method-hash.js';
import { encodeViewId16, decodeViewId16, encodeViewId, decodeViewIdBits } from '../src/unity/view-id.js';
import { BitStream } from '../src/bitstream.js';
import { decodeQueryReply, encodeQueryReply } from '../src/master/serialization.js';
import {
  encodeRpcSubsequent,
  encodeRpcFirstUse,
  decodeRpc,
  isRpc,
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
      viewId: 1,
      rpcCounter: 0,
      mode: RpcMode.Server,
    });

    expect(encoded.bitLength).toBeGreaterThan(0);
    expect(encoded.data[0]).toBe(0x1b);

    const decoded = decodeRpc(encoded.data, encoded.bitLength);
    expect(decoded.methodName).toBe('RPC_Int');
    expect(decoded.rpcCounter).toBe(0);
    expect(decoded.rpcMode).toBe('Server');
    expect(decoded.firstUse).toBe(false);
    expect(decoded.viewId).toBe(1);
    expect(decoded.params).toEqual([42]);
  });

  it('encodes and decodes a first-use RPC', () => {
    const encoded = encodeRpcFirstUse({
      methodName: 'RPC_Float',
      params: [{ type: 'float', value: 3.14 }],
      viewId: 1,
      rpcCounter: 1,
      mode: RpcMode.All,
    });

    expect(encoded.data[0]).toBe(0x1b);

    const decoded = decodeRpc(encoded.data, encoded.bitLength);
    expect(decoded.methodName).toBe('RPC_Float');
    expect(decoded.rpcMode).toBe('All');
    expect(decoded.firstUse).toBe(true);
    expect(decoded.viewId).toBe(1);
    expect(decoded.params[0]).toBeCloseTo(3.14, 5);
  });

  it('isRpc returns true for RPC packets', () => {
    const encoded = encodeRpcSubsequent({
      methodName: 'RPC_Void',
      params: [],
      viewId: 1,
      rpcCounter: 0,
      mode: RpcMode.Server,
    });
    expect(isRpc(encoded.data)).toBe(true);
  });

  it('correctly encodes RPC counter', () => {
    const encoded = encodeRpcSubsequent({
      methodName: 'RPC_Int',
      params: [{ type: 'int', value: 0 }],
      viewId: 1,
      rpcCounter: 5,
      mode: RpcMode.Server,
    });
    const decoded = decodeRpc(encoded.data, encoded.bitLength);
    expect(decoded.rpcCounter).toBe(5);
  });

  it('round-trips int param', () => {
    const encoded = encodeRpcSubsequent({
      methodName: 'RPC_Int',
      params: [{ type: 'int', value: -42 }],
      viewId: 1,
      rpcCounter: 0,
      mode: RpcMode.Server,
    });
    const decoded = decodeRpc(encoded.data, encoded.bitLength);
    expect(decoded.params).toEqual([-42]);
  });

  it('round-trips float param', () => {
    const encoded = encodeRpcSubsequent({
      methodName: 'RPC_Float',
      params: [{ type: 'float', value: -1.5 }],
      viewId: 1,
      rpcCounter: 0,
      mode: RpcMode.Server,
    });
    const decoded = decodeRpc(encoded.data, encoded.bitLength);
    expect(decoded.params[0]).toBeCloseTo(-1.5);
  });

  it('round-trips string param', () => {
    const encoded = encodeRpcSubsequent({
      methodName: 'RPC_String',
      params: [{ type: 'string', value: 'hello world' }],
      viewId: 1,
      rpcCounter: 0,
      mode: RpcMode.Server,
    });
    const decoded = decodeRpc(encoded.data, encoded.bitLength);
    expect(decoded.params).toEqual(['hello world']);
  });

  it('round-trips empty string param', () => {
    const encoded = encodeRpcSubsequent({
      methodName: 'RPC_String',
      params: [{ type: 'string', value: '' }],
      viewId: 1,
      rpcCounter: 0,
      mode: RpcMode.Server,
    });
    const decoded = decodeRpc(encoded.data, encoded.bitLength);
    expect(decoded.params).toEqual(['']);
  });

  it('round-trips Vector3 param', () => {
    const encoded = encodeRpcSubsequent({
      methodName: 'RPC_Vector3',
      params: [{ type: 'Vector3', value: [1.5, -2.5, 3.0] }],
      viewId: 1,
      rpcCounter: 0,
      mode: RpcMode.Server,
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
      viewId: 1,
      rpcCounter: 0,
      mode: RpcMode.Server,
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
      viewId: 1,
      rpcCounter: 0,
      mode: RpcMode.Server,
    });
    const decoded = decodeRpc(encoded.data, encoded.bitLength);
    expect(decoded.params[0]).toEqual(new Uint8Array([0xde, 0xad, 0xbe, 0xef]));
  });

  it('round-trips empty bytes param', () => {
    const encoded = encodeRpcSubsequent({
      methodName: 'RPC_Bytes',
      params: [{ type: 'bytes', value: new Uint8Array(0) }],
      viewId: 1,
      rpcCounter: 0,
      mode: RpcMode.Server,
    });
    const decoded = decodeRpc(encoded.data, encoded.bitLength);
    expect(decoded.params[0]).toEqual(new Uint8Array(0));
  });

  it('round-trips NetworkViewID param', () => {
    const encoded = encodeRpcSubsequent({
      methodName: 'RPC_NetworkViewID',
      params: [{ type: 'NetworkViewID', value: 42 }],
      viewId: 1,
      rpcCounter: 0,
      mode: RpcMode.Server,
    });
    const decoded = decodeRpc(encoded.data, encoded.bitLength);
    expect(decoded.params).toEqual([42]);
  });

  it('round-trips NetworkPlayer param', () => {
    const encoded = encodeRpcSubsequent({
      methodName: 'RPC_NetworkPlayer',
      params: [{ type: 'NetworkPlayer', value: 7 }],
      viewId: 1,
      rpcCounter: 0,
      mode: RpcMode.Server,
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
      viewId: 1,
      rpcCounter: 0,
      mode: RpcMode.Server,
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
      viewId: 1,
      rpcCounter: 0,
      mode: RpcMode.Server,
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
      viewId: 5,
      rpcCounter: 0,
      mode: RpcMode.All,
    });
    const decoded = decodeRpc(encoded.data, encoded.bitLength);
    expect(decoded.methodName).toBe('RPC_IntFloatString');
    expect(decoded.firstUse).toBe(true);
    expect(decoded.viewId).toBe(5);
    expect(decoded.params[0]).toBe(-1);
    expect(decoded.params[1]).toBeCloseTo(0.5);
    expect(decoded.params[2]).toBe('abc');
  });

  it('Player mode skips target bit before params', () => {
    const encoded = encodeRpcSubsequent({
      methodName: 'RPC_Int',
      params: [{ type: 'int', value: 99 }],
      viewId: 1,
      rpcCounter: 0,
      mode: RpcMode.Player,
    });
    const decoded = decodeRpc(encoded.data, encoded.bitLength);
    expect(decoded.rpcMode).toBe('Player');
    expect(decoded.params).toEqual([99]);
  });

  it('captures viewId from header', () => {
    const encoded = encodeRpcSubsequent({
      methodName: 'RPC_Void',
      params: [],
      viewId: 12345,
      rpcCounter: 0,
      mode: RpcMode.Server,
    });
    const decoded = decodeRpc(encoded.data, encoded.bitLength);
    expect(decoded.viewId).toBe(12345);
  });

  it('unknown method returns empty params without throwing', () => {
    const encoded = encodeRpcSubsequent({
      methodName: 'RPC_Void',
      params: [],
      viewId: 1,
      rpcCounter: 0,
      mode: RpcMode.Server,
    });
    // Corrupt the method index byte (byte 10, which contains the 1-bit first_use flag + 7-bit index)
    // Set to a method index that doesn't exist (0xfe = index 0xfe)
    encoded.data[10] = 0x7f; // first_use=0, index bits = 0xfe
    const decoded = decodeRpc(encoded.data, encoded.bitLength);
    expect(decoded.methodName).toMatch(/^unknown_0x/);
    expect(decoded.params).toEqual([]);
  });
});

describe('State Sync', () => {
  it('encodes and decodes a state sync message', () => {
    const encoded = encodeStateSync({
      viewId: { scope: 'scene', id: 1 },
      timestamp: 100,
      fields: [{ type: 'float', value: 1.5 }],
      isFirst: false,
    });

    expect(encoded.data[0]).toBe(0x1b);
    expect(encoded.bitLength).toBe(96 + 32);

    const decoded = decodeStateSync(encoded.data, encoded.bitLength);
    expect(decoded.timestamp).toBe(100);
    expect(decoded.isFirst).toBe(false);
    expect(decoded.viewIdScope).toBe('scene');
    expect(decoded.viewId).toBe(1);
  });

  it('encodes first state sync with 0x80 flag', () => {
    const encoded = encodeStateSync({
      viewId: { scope: 'scene', id: 1 },
      timestamp: 0,
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
      timestamp: 200,
      fieldValues: [100, 200],
      prevValues: [100, 100],
      fieldWidths: [32, 32],
      isFirst: false,
    });

    const decoded = decodeDeltaStateSync(encoded.data, encoded.bitLength, 2, [32, 32], [100, 100]);

    expect(decoded.timestamp).toBe(200);
    expect(decoded.dirtyFlags).toEqual([0, 1]);
    expect(decoded.fieldValues).toEqual([100, 200]);
  });

  it('no dirty fields produces minimal output', () => {
    const encoded = encodeDeltaStateSync({
      viewId: { scope: 'scene', id: 1 },
      timestamp: 0,
      fieldValues: [42, 43],
      prevValues: [42, 43],
      fieldWidths: [32, 32],
      isFirst: false,
    });

    expect(encoded.bitLength).toBe(96 + 2); // header + 2 dirty bits (both 0)
  });
});

describe('RPC counter overflow', () => {
  it('counter wraps at 128 (single byte, *2)', () => {
    const encode = (counter: number) =>
      encodeRpcSubsequent({
        methodName: 'RPC_Int',
        params: [{ type: 'int', value: 1 }],
        viewId: 1,
        rpcCounter: counter,
        mode: RpcMode.Server,
      });

    const r0 = encode(0);
    const r127 = encode(127);
    const r128 = encode(128);

    const d0 = decodeRpc(r0.data, r0.bitLength);
    const d127 = decodeRpc(r127.data, r127.bitLength);
    const d128 = decodeRpc(r128.data, r128.bitLength);

    expect(d0.rpcCounter).toBe(0);
    expect(d127.rpcCounter).toBe(127);
    expect(d128.rpcCounter).toBe(0); // wraps intentionally
  });

  it('counter values 0-500 all encode/decode correctly (multiple wraps)', () => {
    for (let i = 0; i <= 500; i++) {
      const result = encodeRpcSubsequent({
        methodName: 'RPC_Void',
        params: [],
        viewId: 1,
        rpcCounter: i,
        mode: RpcMode.Server,
      });
      const decoded = decodeRpc(result.data, result.bitLength);
      expect(decoded.rpcCounter).toBe(i % 128);
      expect(decoded.methodName).toBe('RPC_Void');
    }
  });

  it('first-use encoding also wraps counter correctly', () => {
    const r200 = encodeRpcFirstUse({
      methodName: 'RPC_String',
      params: [{ type: 'string', value: 'test' }],
      viewId: 1,
      rpcCounter: 200,
      mode: RpcMode.All,
    });
    const decoded = decodeRpc(r200.data, r200.bitLength);
    expect(decoded.rpcCounter).toBe(200 % 128);
    expect(decoded.params[0]).toBe('test');
  });
});

describe('Float edge values', () => {
  it('encodes/decodes NaN in RPC float param', () => {
    const result = encodeRpcSubsequent({
      methodName: 'RPC_Float',
      params: [{ type: 'float', value: NaN }],
      viewId: 1,
      rpcCounter: 0,
      mode: RpcMode.Server,
    });
    const decoded = decodeRpc(result.data, result.bitLength);
    expect(decoded.params[0]).toBeNaN();
  });

  it('encodes/decodes Infinity in RPC float param', () => {
    const result = encodeRpcSubsequent({
      methodName: 'RPC_Float',
      params: [{ type: 'float', value: Infinity }],
      viewId: 1,
      rpcCounter: 0,
      mode: RpcMode.Server,
    });
    const decoded = decodeRpc(result.data, result.bitLength);
    expect(decoded.params[0]).toBe(Infinity);
  });

  it('encodes/decodes -Infinity in RPC float param', () => {
    const result = encodeRpcSubsequent({
      methodName: 'RPC_Float',
      params: [{ type: 'float', value: -Infinity }],
      viewId: 1,
      rpcCounter: 0,
      mode: RpcMode.Server,
    });
    const decoded = decodeRpc(result.data, result.bitLength);
    expect(decoded.params[0]).toBe(-Infinity);
  });

  it('encodes/decodes -0 in RPC float param', () => {
    const result = encodeRpcSubsequent({
      methodName: 'RPC_Float',
      params: [{ type: 'float', value: -0 }],
      viewId: 1,
      rpcCounter: 0,
      mode: RpcMode.Server,
    });
    const decoded = decodeRpc(result.data, result.bitLength);
    expect(Object.is(decoded.params[0], -0)).toBe(true);
  });

  it('encodes/decodes NaN in Vector3', () => {
    const result = encodeRpcSubsequent({
      methodName: 'RPC_Vector3',
      params: [{ type: 'Vector3', value: [NaN, 0, Infinity] }],
      viewId: 1,
      rpcCounter: 0,
      mode: RpcMode.Server,
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
      viewId: 1,
      rpcCounter: 0,
      mode: RpcMode.Server,
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
      timestamp: 100,
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
    expect(decoded.timestamp).toBe(100);
    expect(decoded.isFirst).toBe(true);
  });
});

describe('Encoding edge cases', () => {
  it('encodes/decodes zero Vector3 (0,0,0)', () => {
    const result = encodeRpcSubsequent({
      methodName: 'RPC_Vector3',
      params: [{ type: 'Vector3', value: [0, 0, 0] }],
      viewId: 1,
      rpcCounter: 0,
      mode: RpcMode.Server,
    });
    const decoded = decodeRpc(result.data, result.bitLength);
    expect(decoded.params[0]).toEqual([0, 0, 0]);
  });

  it('encodes/decodes zero Quaternion (0,0,0,0)', () => {
    const result = encodeRpcSubsequent({
      methodName: 'RPC_Quaternion',
      params: [{ type: 'Quaternion', value: [0, 0, 0, 0] }],
      viewId: 1,
      rpcCounter: 0,
      mode: RpcMode.Server,
    });
    const decoded = decodeRpc(result.data, result.bitLength);
    expect(decoded.params[0]).toEqual([0, 0, 0, 0]);
  });

  it('encodes/decodes INT32_MIN and INT32_MAX in RPC', () => {
    const result = encodeRpcSubsequent({
      methodName: 'RPC_Int',
      params: [{ type: 'int', value: -2147483648 }],
      viewId: 1,
      rpcCounter: 0,
      mode: RpcMode.Server,
    });
    const decoded = decodeRpc(result.data, result.bitLength);
    expect(decoded.params[0]).toBe(-2147483648);

    const result2 = encodeRpcSubsequent({
      methodName: 'RPC_Int',
      params: [{ type: 'int', value: 2147483647 }],
      viewId: 1,
      rpcCounter: 1,
      mode: RpcMode.Server,
    });
    const decoded2 = decodeRpc(result2.data, result2.bitLength);
    expect(decoded2.params[0]).toBe(2147483647);
  });

  it('encodes/decodes empty byte array', () => {
    const result = encodeRpcSubsequent({
      methodName: 'RPC_Bytes',
      params: [{ type: 'bytes', value: new Uint8Array(0) }],
      viewId: 1,
      rpcCounter: 0,
      mode: RpcMode.Server,
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
      viewId: 1,
      rpcCounter: 0,
      mode: RpcMode.Server,
    });
    // Corrupt the method hash bytes (bytes after the length indicator)
    const data = new Uint8Array(result.data);
    for (let i = 14; i < 20; i++) {
      data[i] = 0xff;
    }
    const decoded = decodeRpc(data, result.bitLength);
    // Should decode without crashing; method name is 'unknown' or similar
    expect(decoded.rpcCounter).toBe(0);
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
      viewId: 1,
      rpcCounter: 0,
      mode: RpcMode.Server,
    });
    // The count field is 4 bytes (u32 big-endian) right after the mode bits
    // Find the 4 zero bytes that represent count=0 and replace with a huge value
    const tampered = new Uint8Array(data.length + 4);
    tampered.set(data);
    // Decode the untampered version to confirm it works
    expect(() => decodeRpc(data, bitLength)).not.toThrow();

    // Manually construct a BitStream with a huge count in the params area
    const bs = new BitStream(data, bitLength);
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
