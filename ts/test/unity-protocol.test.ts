import { describe, it, expect } from 'vitest';
import { computeMethodId, computeMethodIndex } from '../src/unity/method-hash.js';
import { encodeViewId16, decodeViewId16, encodeViewId } from '../src/unity/view-id.js';
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
