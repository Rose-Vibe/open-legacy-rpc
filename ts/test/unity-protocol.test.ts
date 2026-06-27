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
