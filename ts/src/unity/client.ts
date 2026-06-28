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
  encodeBatchIndex,
  decodeBatchIndex,
  MSG_ID_BATCH_INDEX,
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
  private rpcReceivedFirstUse: string[] = [];
  private rpcCounter = 0;
  private serverIndices = new Map<string, number>();
  private ourIndices = new Map<string, number>();
  private ourIndexReverse = new Map<number, string>();
  private nextOurIndex = 4;

  constructor(socket: UdpSocket) {
    this.raknet = new RakNetClient(socket);

    this.raknet.onConnect(() => {
      for (const h of this.connectHandlers) h();
    });

    this.raknet.onDisconnect(() => {
      this.rpcReceivedFirstUse = [];
      this.serverIndices.clear();
      this.ourIndices.clear();
      this.ourIndexReverse.clear();
      this.nextOurIndex = 4;
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
    const serverIdx = this.serverIndices.get(methodName);
    if (serverIdx !== undefined) {
      result = encodeRpcSubsequent({ ...opts, methodIndex: serverIdx });
    } else if (hasMethodIndex(methodName)) {
      result = encodeRpcSubsequent(opts);
    } else {
      result = encodeRpcFirstUse(opts);
    }

    this.raknet.send(result.data, Reliability.RELIABLE_ORDERED, result.bitLength);
  }

  sendRaw(payload: Uint8Array, reliability: Reliability, bitLength?: number): void {
    this.raknet.send(payload, reliability, bitLength);
  }

  private handleMessage(msg: IncomingMessage): void {
    const msgId = msg.payload[0];
    if (msgId === MSG_ID_BATCH_INDEX) {
      this.handleBatchIndex(msg);
      return;
    }
    if (msgId !== 0x1b) return;

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

      if (!this.ourIndices.has(decoded.methodName)) {
        const idx = this.nextOurIndex;
        this.nextOurIndex += 4;
        this.ourIndices.set(decoded.methodName, idx);
        this.ourIndexReverse.set(idx, decoded.methodName);
      }
      const ourIdx = this.ourIndices.get(decoded.methodName)!;
      const batch = encodeBatchIndex(decoded.methodName, ourIdx);
      this.raknet.send(batch.data, Reliability.UNRELIABLE, batch.bitLength);
    } else if (!decoded.firstUse && decoded.methodIndex !== undefined) {
      const resolved = this.ourIndexReverse.get(decoded.methodIndex);
      if (resolved) {
        decoded.methodName = resolved;
      } else if (decoded.methodName.startsWith('unknown_0x') &&
                 this.rpcReceivedFirstUse.length > 0) {
        const pending = this.rpcReceivedFirstUse.shift()!;
        learnMethodIndex(pending, decoded.methodIndex);
        decoded.methodName = pending;
      }
    }

    const handler = this.rpcHandlers.get(decoded.methodName);
    if (handler) {
      handler(...decoded.params);
    }
  }

  private handleBatchIndex(msg: IncomingMessage): void {
    const decoded = decodeBatchIndex(msg.payload);
    if (!decoded || !decoded.methodName) return;
    this.serverIndices.set(decoded.methodName, decoded.methodIndex);
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
