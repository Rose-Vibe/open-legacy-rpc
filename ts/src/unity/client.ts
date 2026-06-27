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
  RpcMode,
} from './rpc.js';
import type { RpcParam } from './rpc.js';
import type { RpcDefinition } from '../services/rpc-schema.js';
import { argsToRpcParams, rpcParamsToArgs } from '../services/rpc-schema.js';
import { decodeStateSync } from './state-sync.js';
import type { DecodedStateSync } from './state-sync.js';

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
  private rpcCounter = 0;

  constructor(socket: UdpSocket) {
    this.raknet = new RakNetClient(socket);

    this.raknet.onConnect(() => {
      for (const h of this.connectHandlers) h();
    });

    this.raknet.onDisconnect(() => {
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
    options?: { viewId?: number; mode?: RpcMode },
  ): void {
    def.zodSchema.parse(args);
    const viewId = options?.viewId ?? 1;
    const mode = options?.mode ?? RpcMode.Server;
    const params = argsToRpcParams(def, args);
    this.sendRpc(def.name, params, { viewId, mode });
  }

  onStateSync(viewId: number | null, handler: EventHandler<[StateSyncMessage]>): void {
    this.stateSyncHandlers.set(viewId, handler);
  }

  sendRpc(
    methodName: string,
    params: RpcParam[],
    options?: { viewId?: number; mode?: RpcMode },
  ): void {
    const viewId = options?.viewId ?? 1;
    const mode = options?.mode ?? RpcMode.Server;
    const counter = this.rpcCounter++;

    let result: { data: Uint8Array; bitLength: number };
    if (this.rpcSentMethods.has(methodName) && hasMethodIndex(methodName)) {
      result = encodeRpcSubsequent({ methodName, params, viewId, rpcCounter: counter, mode });
    } else {
      result = encodeRpcFirstUse({ methodName, params, viewId, rpcCounter: counter, mode });
      if (hasMethodIndex(methodName)) this.rpcSentMethods.add(methodName);
    }

    this.raknet.send(result.data, Reliability.RELIABLE_ORDERED);
  }

  sendRaw(payload: Uint8Array, reliability: Reliability): void {
    this.raknet.send(payload, reliability);
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
