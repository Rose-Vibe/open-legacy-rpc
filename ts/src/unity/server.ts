import type { ClientSession } from '../raknet/connection.js';
import { RakNetServer } from '../raknet/connection.js';
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
import { encodeStateSync, decodeStateSync, encodeDeltaStateSync } from './state-sync.js';
import type { StateSyncField, DecodedStateSync } from './state-sync.js';
import type { ViewId } from './view-id.js';

type EventHandler<T extends unknown[]> = (...args: T) => void;

export interface UnityServerOptions {
  port: number;
  password?: string;
  viewIdStride?: number;
}

export interface StateSyncMessage extends DecodedStateSync {
  payload: Uint8Array;
  bitLength: number;
}

export class UnityServer {
  private raknet: RakNetServer;
  private rpcHandlers = new Map<string, EventHandler<[ClientSession, ...unknown[]]>>();
  private stateSyncHandlers: Array<EventHandler<[ClientSession, StateSyncMessage]>> = [];
  private connectHandlers: Array<EventHandler<[ClientSession]>> = [];
  private disconnectHandlers: Array<EventHandler<[ClientSession]>> = [];
  private rpcSentMethods = new Map<string, Set<string>>();
  private rpcCounters = new Map<string, number>();
  private syncTimestamp = 0;
  private deltaState = new Map<string, number[]>();

  constructor(socket: UdpSocket, options: UnityServerOptions) {
    const rakOpts: { port: number; password?: string; viewIdStride?: number } = {
      port: options.port,
    };
    if (options.password !== undefined) rakOpts.password = options.password;
    if (options.viewIdStride !== undefined) rakOpts.viewIdStride = options.viewIdStride;
    this.raknet = new RakNetServer(socket, rakOpts);

    this.raknet.onConnect((session) => {
      this.rpcSentMethods.set(session.id, new Set(getBuiltinMethodNames()));
      this.rpcCounters.set(session.id, 0);
      for (const h of this.connectHandlers) h(session);
    });

    this.raknet.onDisconnect((session) => {
      this.rpcSentMethods.delete(session.id);
      this.rpcCounters.delete(session.id);
      for (const key of this.deltaState.keys()) {
        if (key.startsWith(session.id + ':')) {
          this.deltaState.delete(key);
        }
      }
      for (const h of this.disconnectHandlers) h(session);
    });

    this.raknet.onMessage((session, msg) => {
      this.handleMessage(session, msg);
    });
  }

  async start(): Promise<void> {
    await this.raknet.start();
  }

  async stop(): Promise<void> {
    await this.raknet.stop();
  }

  get clients(): ReadonlyMap<string, ClientSession> {
    return this.raknet.clients;
  }

  onConnect(handler: EventHandler<[ClientSession]>): void {
    this.connectHandlers.push(handler);
  }

  onDisconnect(handler: EventHandler<[ClientSession]>): void {
    this.disconnectHandlers.push(handler);
  }

  onRpc(methodName: string, handler: EventHandler<[ClientSession, ...unknown[]]>): void {
    this.rpcHandlers.set(methodName, handler);
  }

  /** Register a typed RPC handler. RPCs failing Zod validation are silently dropped. */
  onTypedRpc<T>(
    def: RpcDefinition<T>,
    handler: (session: ClientSession, args: T) => void,
  ): void {
    this.rpcHandlers.set(def.name, (session: ClientSession, ...params: unknown[]) => {
      const args = rpcParamsToArgs(def, params);
      const result = def.zodSchema.safeParse(args);
      if (!result.success) return;
      handler(session, result.data);
    });
  }

  /** Send a typed RPC to a client. Throws if args fail Zod validation. */
  sendTypedRpc<T>(
    target: ClientSession,
    def: RpcDefinition<T>,
    args: T,
    options?: { viewId?: number; mode?: RpcMode },
  ): void {
    def.zodSchema.parse(args);
    const params = argsToRpcParams(def, args);
    this.sendRpc(target, def.name, params, options);
  }

  broadcastTypedRpc<T>(
    def: RpcDefinition<T>,
    args: T,
    options?: { exclude?: ClientSession; viewId?: number; mode?: RpcMode },
  ): void {
    def.zodSchema.parse(args);
    const params = argsToRpcParams(def, args);
    this.broadcastRpc(def.name, params, options);
  }

  onStateSync(handler: EventHandler<[ClientSession, StateSyncMessage]>): void {
    this.stateSyncHandlers.push(handler);
  }

  sendRpc(
    target: ClientSession,
    methodName: string,
    params: RpcParam[],
    options?: { viewId?: number; mode?: RpcMode; userRpcConstant?: number },
  ): void {
    const viewId = options?.viewId ?? 1;
    const mode = options?.mode ?? RpcMode.Server;
    this.sendRpcTo(target, methodName, params, viewId, mode, options?.userRpcConstant);
  }

  broadcastRpc(
    methodName: string,
    params: RpcParam[],
    options?: { exclude?: ClientSession; viewId?: number; mode?: RpcMode; userRpcConstant?: number },
  ): void {
    const viewId = options?.viewId ?? 1;
    const mode = options?.mode ?? RpcMode.All;
    for (const session of this.raknet.clients.values()) {
      if (options?.exclude && session.id === options.exclude.id) continue;
      this.sendRpcTo(session, methodName, params, viewId, mode, options?.userRpcConstant);
    }
  }

  sendStateSync(
    target: ClientSession,
    viewId: ViewId,
    fields: StateSyncField[],
    options?: { isFirst?: boolean },
  ): void {
    this.syncTimestamp = (this.syncTimestamp + 83) & 0xffff;
    const { data } = encodeStateSync({
      viewId,
      timestamp: this.syncTimestamp,
      fields,
      isFirst: options?.isFirst ?? false,
    });
    this.raknet.sendTo(target, data, Reliability.UNRELIABLE_SEQUENCED);
  }

  sendDeltaStateSync(
    target: ClientSession,
    viewId: ViewId,
    fieldValues: number[],
    fieldWidths: number[],
    _options?: { viewIdScope?: 'scene' | 'allocated' },
  ): void {
    this.syncTimestamp = (this.syncTimestamp + 83) & 0xffff;
    const key = `${target.id}:${String(viewId.id)}`;
    const prev = this.deltaState.get(key) ?? new Array<number>(fieldValues.length).fill(0);
    const isFirst = !this.deltaState.has(key);

    const { data } = encodeDeltaStateSync({
      viewId,
      timestamp: this.syncTimestamp,
      fieldValues,
      prevValues: prev,
      fieldWidths,
      isFirst,
    });

    this.deltaState.set(key, [...fieldValues]);
    this.raknet.sendTo(target, data, Reliability.RELIABLE_ORDERED);
  }

  sendRaw(target: ClientSession, payload: Uint8Array, reliability: Reliability): void {
    this.raknet.sendTo(target, payload, reliability);
  }

  private sendRpcTo(
    session: ClientSession,
    methodName: string,
    params: RpcParam[],
    viewId: number,
    mode: RpcMode,
    userRpcConstant?: number,
  ): void {
    let sent = this.rpcSentMethods.get(session.id);
    if (!sent) {
      sent = new Set(getBuiltinMethodNames());
      this.rpcSentMethods.set(session.id, sent);
    }

    const counter = this.rpcCounters.get(session.id) ?? 0;
    this.rpcCounters.set(session.id, counter + 1);

    let result: { data: Uint8Array; bitLength: number };
    if (sent.has(methodName) && hasMethodIndex(methodName)) {
      result = encodeRpcSubsequent({ methodName, params, viewId, rpcCounter: counter, mode, userRpcConstant });
    } else {
      result = encodeRpcFirstUse({ methodName, params, viewId, rpcCounter: counter, mode, userRpcConstant });
      if (hasMethodIndex(methodName)) sent.add(methodName);
    }

    this.raknet.sendTo(session, result.data, Reliability.RELIABLE_ORDERED, result.bitLength);
  }

  private handleMessage(session: ClientSession, msg: IncomingMessage): void {
    if (msg.payload[0] !== 0x1b) return;

    if (msg.reliability === Reliability.UNRELIABLE_SEQUENCED) {
      this.handleStateSync(session, msg);
    } else if (msg.reliability === Reliability.RELIABLE_ORDERED && isRpc(msg.payload)) {
      this.handleRpc(session, msg);
    }
  }

  private handleRpc(session: ClientSession, msg: IncomingMessage): void {
    let decoded;
    try {
      decoded = decodeRpc(msg.payload, msg.bitLength);
    } catch {
      return;
    }
    (session as ClientSession & { lastRpcViewId?: number }).lastRpcViewId = decoded.viewId;
    const handler = this.rpcHandlers.get(decoded.methodName);
    if (handler) {
      handler(session, ...decoded.params);
    }
  }

  private handleStateSync(session: ClientSession, msg: IncomingMessage): void {
    let decoded;
    try {
      decoded = decodeStateSync(msg.payload, msg.bitLength);
    } catch {
      return;
    }
    const syncMsg: StateSyncMessage = {
      ...decoded,
      payload: msg.payload,
      bitLength: msg.bitLength,
    };
    for (const h of this.stateSyncHandlers) h(session, syncMsg);
  }
}
