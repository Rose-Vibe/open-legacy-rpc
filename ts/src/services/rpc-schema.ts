import { z } from 'zod';
import type { ParamType, RpcParam } from '../unity/rpc.js';
import { METHOD_SIGNATURES } from '../unity/rpc.js';
import { registerMethodNames } from '../unity/method-hash.js';

type ParamTsType<P extends ParamType> = P extends 'int'
  ? number
  : P extends 'float'
    ? number
    : P extends 'string'
      ? string
      : P extends 'bytes'
        ? Uint8Array
        : P extends 'Vector3'
          ? [number, number, number]
          : P extends 'Quaternion'
            ? [number, number, number, number]
            : P extends 'NetworkViewID'
              ? number
              : P extends 'NetworkPlayer'
                ? number
                : never;

interface RpcFieldDef<P extends ParamType = ParamType> {
  param: P;
  schema: z.ZodType<ParamTsType<P>>;
}

type RpcFieldDefs = Record<string, RpcFieldDef>;

type InferRpcArgs<F extends RpcFieldDefs> = {
  [K in keyof F]: F[K] extends RpcFieldDef<infer P> ? ParamTsType<P> : never;
};

export interface RpcDefinition<T = unknown> {
  readonly name: string;
  readonly paramTypes: ParamType[];
  readonly fieldNames: string[];
  readonly zodSchema: z.ZodType<T>;
  readonly _type: T;
}

/** Define an RPC with typed fields and Zod validation. Registers the method signature for encode/decode. */
export function defineRpc<F extends RpcFieldDefs>(
  name: string,
  fields: F,
): RpcDefinition<InferRpcArgs<F>> {
  const fieldNames = Object.keys(fields);
  const paramTypes = fieldNames.map((k) => (fields[k] as RpcFieldDef).param);

  registerMethodNames([name]);
  METHOD_SIGNATURES[name] = paramTypes;

  const zodShape: Record<string, z.ZodType> = {};
  for (const k of fieldNames) {
    zodShape[k] = (fields[k] as RpcFieldDef).schema;
  }
  const zodSchema = z.object(zodShape) as unknown as z.ZodType<InferRpcArgs<F>>;

  return {
    name,
    paramTypes,
    fieldNames,
    zodSchema,
    _type: undefined as unknown as InferRpcArgs<F>,
  };
}

export function argsToRpcParams<T>(def: RpcDefinition<T>, args: T): RpcParam[] {
  const obj = args as Record<string, unknown>;
  return def.fieldNames.map((fieldName, i) => {
    const paramType = def.paramTypes[i] as ParamType;
    const value = obj[fieldName];
    return { type: paramType, value: value as RpcParam['value'] };
  });
}

export function rpcParamsToArgs<T>(def: RpcDefinition<T>, params: unknown[]): T {
  const obj: Record<string, unknown> = {};
  for (let i = 0; i < def.fieldNames.length; i++) {
    obj[def.fieldNames[i] as string] = params[i];
  }
  return obj as T;
}
