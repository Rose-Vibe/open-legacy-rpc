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
  METHOD_SIGNATURES,
  RpcMode,
} from './rpc.js';
import type { RpcParam } from './rpc.js';
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
      this.rpcSentMethods.set(session.id, new Set(Object.keys(METHOD_SIGNATURES)));
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

  onStateSync(handler: EventHandler<[ClientSession, StateSyncMessage]>): void {
    this.stateSyncHandlers.push(handler);
  }

  sendRpc(
    target: ClientSession,
    methodName: string,
    params: RpcParam[],
    options?: { viewId?: number; mode?: RpcMode },
  ): void {
    const viewId = options?.viewId ?? 1;
    const mode = options?.mode ?? RpcMode.Server;
    this.sendRpcTo(target, methodName, params, viewId, mode);
  }

  broadcastRpc(
    methodName: string,
    params: RpcParam[],
    options?: { exclude?: ClientSession; viewId?: number; mode?: RpcMode },
  ): void {
    const viewId = options?.viewId ?? 1;
    const mode = options?.mode ?? RpcMode.All;
    for (const session of this.raknet.clients.values()) {
      if (options?.exclude && session.id === options.exclude.id) continue;
      this.sendRpcTo(session, methodName, params, viewId, mode);
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
  ): void {
    let sent = this.rpcSentMethods.get(session.id);
    if (!sent) {
      sent = new Set(Object.keys(METHOD_SIGNATURES));
      this.rpcSentMethods.set(session.id, sent);
    }

    const counter = this.rpcCounters.get(session.id) ?? 0;
    this.rpcCounters.set(session.id, counter + 1);

    let result: { data: Uint8Array; bitLength: number };
    if (sent.has(methodName)) {
      result = encodeRpcSubsequent({ methodName, params, viewId, rpcCounter: counter, mode });
    } else {
      result = encodeRpcFirstUse({ methodName, params, viewId, rpcCounter: counter, mode });
      sent.add(methodName);
    }

    this.raknet.sendTo(session, result.data, Reliability.RELIABLE_ORDERED);
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
    try {
      const decoded = decodeRpc(msg.payload, msg.bitLength);
      const handler = this.rpcHandlers.get(decoded.methodName);
      if (handler) {
        handler(session);
      }
    } catch {
      // Silently drop malformed RPCs
    }
  }

  private handleStateSync(session: ClientSession, msg: IncomingMessage): void {
    try {
      const decoded = decodeStateSync(msg.payload, msg.bitLength);
      const syncMsg: StateSyncMessage = {
        ...decoded,
        payload: msg.payload,
        bitLength: msg.bitLength,
      };
      for (const h of this.stateSyncHandlers) h(session, syncMsg);
    } catch {
      // Silently drop malformed state sync
    }
  }
}
