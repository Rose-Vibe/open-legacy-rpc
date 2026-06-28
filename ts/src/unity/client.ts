import { RakNetClient } from '../raknet/connection.js';
import { Reliability } from '../raknet/types.js';
import type { IncomingMessage } from '../raknet/types.js';
import type { UdpSocket } from '../raknet/socket.js';
import {
  encodeRpcSubsequent,
  encodeRpcFirstUse,
  decodeRpc,
  isRpc,
  getBuiltinMethodNames,
  hasMethodIndex,
  learnMethodIndex,
  RpcMode,
} from './rpc.js';
import type { RpcParam } from './rpc.js';
import type { RpcDefinition } from '../services/rpc-schema.js';
import { argsToRpcParams, rpcParamsToArgs } from '../services/rpc-schema.js';
import { decodeStateSync } from './state-sync.js';
import type { DecodedStateSync } from './state-sync.js';
import type { ViewId } from './view-id.js';

type EventHandler<T extends unknown[]> = (...args: T) => void;

export interface ConnectOptions {
  password?: string;
  timeout?: number;
}

export interface StateSyncMessage extends DecodedStateSync {
  payload: Uint8Array;
  bitLength: number;
}

export class UnityClient {
  private raknet: RakNetClient;
  private rpcHandlers = new Map<string, EventHandler<unknown[]>>();
  private stateSyncHandlers = new Map<number | null, EventHandler<[StateSyncMessage]>>();
  private connectHandlers: Array<EventHandler<[]>> = [];
  private disconnectHandlers: Array<EventHandler<[string]>> = [];
  private rpcSentMethods = new Set<string>(getBuiltinMethodNames());
  private rpcReceivedFirstUse: string[] = [];
  private rpcCounter = 0;

  constructor(socket: UdpSocket) {
    this.raknet = new RakNetClient(socket);

    this.raknet.onConnect(() => {
      for (const h of this.connectHandlers) h();
    });

    this.raknet.onDisconnect(() => {
      this.rpcReceivedFirstUse = [];
      for (const h of this.disconnectHandlers) h('disconnected');
    });

    this.raknet.onMessage((msg) => {
      this.handleMessage(msg);
    });
  }

  get connected(): boolean {
    return this.raknet.connected;
  }

  get playerIndex(): number {
    return this.raknet.playerIndex;
  }

  get viewIdBase(): number {
    return this.raknet.viewIdBase;
  }

  async connect(host: string, port: number, options?: ConnectOptions): Promise<void> {
    const connectOpts: { password?: string; timeout?: number } = {};
    if (options?.password !== undefined) connectOpts.password = options.password;
    if (options?.timeout !== undefined) connectOpts.timeout = options.timeout;
    await this.raknet.connect(host, port, connectOpts);
  }

  disconnect(): void {
    this.raknet.disconnect();
  }

  async close(): Promise<void> {
    await this.raknet.close();
  }

  onConnect(handler: EventHandler<[]>): void {
    this.connectHandlers.push(handler);
  }

  onDisconnect(handler: EventHandler<[string]>): void {
    this.disconnectHandlers.push(handler);
  }

  onRpc(methodName: string, handler: EventHandler<unknown[]>): void {
    this.rpcHandlers.set(methodName, handler);
  }

  /** Register a typed RPC handler. RPCs failing Zod validation are silently dropped. */
  onTypedRpc<T>(
    def: RpcDefinition<T>,
    handler: (args: T) => void,
  ): void {
    this.rpcHandlers.set(def.name, (...params: unknown[]) => {
      const args = rpcParamsToArgs(def, params);
      const result = def.zodSchema.safeParse(args);
      if (!result.success) return;
      handler(result.data);
    });
  }

  sendTypedRpc<T>(
    def: RpcDefinition<T>,
    args: T,
    options: { viewId?: number; mode?: RpcMode; targetView: ViewId | number },
  ): void {
    def.zodSchema.parse(args);
    const params = argsToRpcParams(def, args);
    this.sendRpc(def.name, params, options);
  }

  /** Register a state sync handler. Pass viewId=null for a catch-all handler. */
  onStateSync(viewId: number | null, handler: EventHandler<[StateSyncMessage]>): void {
    this.stateSyncHandlers.set(viewId, handler);
  }

  sendRpc(
    methodName: string,
    params: RpcParam[],
    options: { viewId?: number; mode?: RpcMode; targetView: ViewId | number; relay?: boolean },
  ): void {
    const viewId = options.viewId ?? 1;
    const mode = options.mode ?? RpcMode.Server;
    const { targetView } = options;
    const relay = options.relay;
    const counter = this.rpcCounter++;

    const opts = { methodName, params, viewId, rpcCounter: counter, mode, targetView, ...(relay && { relay }) };
    let result: { data: Uint8Array; bitLength: number };
    if (this.rpcSentMethods.has(methodName) && hasMethodIndex(methodName)) {
      result = encodeRpcSubsequent(opts);
    } else {
      result = encodeRpcFirstUse(opts);
      if (hasMethodIndex(methodName)) this.rpcSentMethods.add(methodName);
    }

    this.raknet.send(result.data, Reliability.RELIABLE_ORDERED, result.bitLength);
  }

  sendRaw(payload: Uint8Array, reliability: Reliability, bitLength?: number): void {
    this.raknet.send(payload, reliability, bitLength);
  }

  private handleMessage(msg: IncomingMessage): void {
    if (msg.payload[0] !== 0x1b) return;

    if (msg.reliability === Reliability.UNRELIABLE_SEQUENCED) {
      this.handleStateSync(msg);
    } else if (msg.reliability === Reliability.RELIABLE_ORDERED) {
      if (isRpc(msg.payload)) {
        this.handleRpc(msg);
      } else {
        this.handleStateSync(msg);
      }
    }
  }

  private handleRpc(msg: IncomingMessage): void {
    let decoded;
    try {
      decoded = decodeRpc(msg.payload, msg.bitLength);
    } catch (e) {
      console.warn('Failed to decode RPC:', e);
      return;
    }

    if (decoded.firstUse && decoded.methodName !== 'unknown') {
      this.rpcReceivedFirstUse.push(decoded.methodName);
    } else if (!decoded.firstUse && decoded.methodIndex !== undefined &&
               decoded.methodName.startsWith('unknown_0x') &&
               this.rpcReceivedFirstUse.length > 0) {
      const pending = this.rpcReceivedFirstUse.shift()!;
      learnMethodIndex(pending, decoded.methodIndex);
      decoded.methodName = pending;
    }

    const handler = this.rpcHandlers.get(decoded.methodName);
    if (handler) {
      handler(...decoded.params);
    }
  }

  private handleStateSync(msg: IncomingMessage): void {
    let decoded;
    try {
      decoded = decodeStateSync(msg.payload, msg.bitLength);
    } catch (e) {
      console.warn('Failed to decode state sync:', e);
      return;
    }
    const syncMsg: StateSyncMessage = {
      ...decoded,
      payload: msg.payload,
      bitLength: msg.bitLength,
    };
    const handler =
      this.stateSyncHandlers.get(decoded.viewId) ?? this.stateSyncHandlers.get(null);
    if (handler) handler(syncMsg);
  }
}
