import { describe, it, expect } from 'vitest';
import { z } from 'zod';
import { defineRpc, argsToRpcParams, rpcParamsToArgs } from '../src/services/rpc-schema.js';
import { METHOD_SIGNATURES } from '../src/unity/rpc.js';
import type { RpcParam } from '../src/unity/rpc.js';

describe('defineRpc', () => {
  it('creates a definition with correct field names and param types', () => {
    const def = defineRpc('TestRpc', {
      name: { param: 'string', schema: z.string() },
      count: { param: 'int', schema: z.number().int() },
    });

    expect(def.name).toBe('TestRpc');
    expect(def.fieldNames).toEqual(['name', 'count']);
    expect(def.paramTypes).toEqual(['string', 'int']);
  });

  it('registers the method signature in METHOD_SIGNATURES', () => {
    defineRpc('RegisteredRpc', {
      value: { param: 'float', schema: z.number() },
    });

    expect(METHOD_SIGNATURES['RegisteredRpc']).toEqual(['float']);
  });

  it('supports all 8 param types', () => {
    const def = defineRpc('AllTypes', {
      i: { param: 'int', schema: z.number() },
      f: { param: 'float', schema: z.number() },
      s: { param: 'string', schema: z.string() },
      b: { param: 'bytes', schema: z.instanceof(Uint8Array) },
      v: { param: 'Vector3', schema: z.tuple([z.number(), z.number(), z.number()]) },
      q: { param: 'Quaternion', schema: z.tuple([z.number(), z.number(), z.number(), z.number()]) },
      vid: { param: 'NetworkViewID', schema: z.number() },
      pid: { param: 'NetworkPlayer', schema: z.number() },
    });

    expect(def.paramTypes).toEqual([
      'int', 'float', 'string', 'bytes',
      'Vector3', 'Quaternion', 'NetworkViewID', 'NetworkPlayer',
    ]);
  });

  it('validates args with zod on parse', () => {
    const def = defineRpc('ValidatedRpc', {
      name: { param: 'string', schema: z.string().max(10) },
    });

    expect(() => def.zodSchema.parse({ name: 'short' })).not.toThrow();
    expect(() => def.zodSchema.parse({ name: 'this is way too long' })).toThrow();
  });

  it('safeParse returns success false for invalid data', () => {
    const def = defineRpc('SafeRpc', {
      count: { param: 'int', schema: z.number().int().min(0) },
    });

    const good = def.zodSchema.safeParse({ count: 5 });
    expect(good.success).toBe(true);

    const bad = def.zodSchema.safeParse({ count: -1 });
    expect(bad.success).toBe(false);
  });
});

describe('argsToRpcParams', () => {
  it('converts named args to ordered RpcParam array', () => {
    const def = defineRpc('ConvertRpc', {
      name: { param: 'string', schema: z.string() },
      value: { param: 'int', schema: z.number() },
    });

    const params = argsToRpcParams(def, { name: 'test', value: 42 });
    expect(params).toEqual([
      { type: 'string', value: 'test' },
      { type: 'int', value: 42 },
    ]);
  });

  it('preserves field order', () => {
    const def = defineRpc('OrderRpc', {
      z_last: { param: 'int', schema: z.number() },
      a_first: { param: 'float', schema: z.number() },
    });

    const params = argsToRpcParams(def, { z_last: 1, a_first: 2.5 });
    expect(params[0]).toEqual({ type: 'int', value: 1 });
    expect(params[1]).toEqual({ type: 'float', value: 2.5 });
  });

  it('handles bytes param type', () => {
    const def = defineRpc('BytesRpc', {
      data: { param: 'bytes', schema: z.instanceof(Uint8Array) },
    });

    const data = new Uint8Array([1, 2, 3]);
    const params = argsToRpcParams(def, { data });
    expect(params[0]?.type).toBe('bytes');
    expect(params[0]?.value).toEqual(data);
  });

  it('handles Vector3 param type', () => {
    const def = defineRpc('Vec3Rpc', {
      pos: { param: 'Vector3', schema: z.tuple([z.number(), z.number(), z.number()]) },
    });

    const params = argsToRpcParams(def, { pos: [1.0, 2.0, 3.0] as [number, number, number] });
    expect(params[0]?.type).toBe('Vector3');
    expect(params[0]?.value).toEqual([1.0, 2.0, 3.0]);
  });
});

describe('rpcParamsToArgs', () => {
  it('converts positional params to named args', () => {
    const def = defineRpc('FromParamsRpc', {
      name: { param: 'string', schema: z.string() },
      value: { param: 'int', schema: z.number() },
    });

    const args = rpcParamsToArgs(def, ['hello', 42]);
    expect(args).toEqual({ name: 'hello', value: 42 });
  });

  it('handles missing params as undefined', () => {
    const def = defineRpc('MissingRpc', {
      a: { param: 'int', schema: z.number() },
      b: { param: 'int', schema: z.number() },
    });

    const args = rpcParamsToArgs(def, [1]);
    expect(args).toEqual({ a: 1, b: undefined });
  });
});

describe('defineRpc edge cases', () => {
  it('duplicate defineRpc overwrites cleanly', () => {
    const def1 = defineRpc('DuplicateRpc', {
      a: { param: 'int', schema: z.number() },
    });
    expect(def1.paramTypes).toEqual(['int']);
    expect(METHOD_SIGNATURES['DuplicateRpc']).toEqual(['int']);

    const def2 = defineRpc('DuplicateRpc', {
      x: { param: 'string', schema: z.string() },
      y: { param: 'float', schema: z.number() },
    });
    expect(def2.paramTypes).toEqual(['string', 'float']);
    expect(METHOD_SIGNATURES['DuplicateRpc']).toEqual(['string', 'float']);
  });

  it('defineRpc with no fields creates void RPC', () => {
    const def = defineRpc('VoidSchemaRpc', {});
    expect(def.fieldNames).toEqual([]);
    expect(def.paramTypes).toEqual([]);

    const params = argsToRpcParams(def, {});
    expect(params).toEqual([]);
  });
});

describe('round-trip', () => {
  it('args → params → args preserves values', () => {
    const def = defineRpc('RoundTripRpc', {
      name: { param: 'string', schema: z.string() },
      hp: { param: 'int', schema: z.number() },
      speed: { param: 'float', schema: z.number() },
    });

    const original = { name: 'player1', hp: 100, speed: 5.5 };
    const params = argsToRpcParams(def, original);
    const values = params.map((p: RpcParam) => p.value);
    const restored = rpcParamsToArgs(def, values);
    expect(restored).toEqual(original);
  });
});
