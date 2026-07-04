import { RakNetClient } from '../raknet/connection.js';
import { Reliability } from '../raknet/types.js';
import type { IncomingMessage } from '../raknet/types.js';
import { UdpSocket } from '../raknet/socket.js';
import {
  ID_DATABASE_QUERY_REPLY,
  ID_DATABASE_ROWID,
  ID_DATABASE_INCORRECT_PASSWORD,
  ID_DATABASE_UNKNOWN_TABLE,
  NUMERIC, STRING, BINARY,
  RUM_UPDATE_OR_ADD_ROW,
  encodeUpdateRow,
  encodeQueryRequest,
  encodeRemoveRow,
  decodeQueryReply,
} from './serialization.js';
import type { Cell } from './serialization.js';

export interface HostInfo {
  ip: string;
  port: number;
  gameName: string;
  connectedPlayers: number;
  playerLimit: number;
  passwordProtected: boolean;
  comment: string;
  guid: string;
  nat: boolean;
  rowId: number;
}

export interface RegisterOptions {
  gameType: string;
  name: string;
  comment?: string;
  playerCount?: number;
  playerLimit?: number;
  passwordProtected?: boolean;
  useNat?: boolean;
  port?: number;
  ip?: string;
}

export class MasterClient {
  private client: RakNetClient;
  private socket: UdpSocket;
  private rowId: number | null = null;
  private pendingResolvers: Array<{
    msgIds: number[];
    resolve: (msg: IncomingMessage) => void;
    reject: (err: Error) => void;
    timer: ReturnType<typeof setTimeout>;
  }> = [];

  constructor() {
    this.socket = new UdpSocket();
    this.client = new RakNetClient(this.socket);
    this.client.onMessage((msg) => {
      this.handleMessage(msg);
    });
  }

  get connected(): boolean {
    return this.client.connected;
  }

  async connect(host = '127.0.0.1', port = 23466, timeout = 5000): Promise<void> {
    await this.client.connect(host, port, { timeout });
  }

  async close(): Promise<void> {
    for (const pending of this.pendingResolvers) {
      clearTimeout(pending.timer);
      pending.reject(new Error('MasterClient closed'));
    }
    this.pendingResolvers = [];
    await this.client.close();
  }

  async registerHost(options: RegisterOptions, timeout = 5000): Promise<number> {
    const ipBytes = new Uint8Array(16);
    const ipStr = new TextEncoder().encode(options.ip ?? '0.0.0.0');
    ipBytes.set(ipStr);

    const cells: Cell[] = [
      { name: 'NAT', type: NUMERIC, value: options.useNat ? 1.0 : 0.0 },
      { name: 'Game name', type: STRING, value: options.name },
      { name: 'Connected players', type: NUMERIC, value: options.playerCount ?? 0 },
      { name: 'Player limit', type: NUMERIC, value: options.playerLimit ?? 4 },
      { name: 'Password protected', type: NUMERIC, value: options.passwordProtected ? 1.0 : 0.0 },
      { name: 'IP address', type: BINARY, value: ipBytes },
      { name: 'Port', type: NUMERIC, value: options.port ?? 7777 },
      { name: 'Comment', type: STRING, value: options.comment ?? '' },
    ];

    const payload = encodeUpdateRow(options.gameType, cells, RUM_UPDATE_OR_ADD_ROW);
    this.client.send(payload, Reliability.RELIABLE_ORDERED);

    const reply = await this.waitForMessage([ID_DATABASE_ROWID, ID_DATABASE_INCORRECT_PASSWORD, ID_DATABASE_UNKNOWN_TABLE], timeout);
    const replyId = reply.payload[0];

    if (replyId === ID_DATABASE_INCORRECT_PASSWORD) {
      throw new Error('Incorrect password');
    }
    if (replyId === ID_DATABASE_UNKNOWN_TABLE) {
      throw new Error('Unknown table');
    }

    const p = reply.payload;
    this.rowId = ((p[1] ?? 0) << 24) | ((p[2] ?? 0) << 16) | ((p[3] ?? 0) << 8) | (p[4] ?? 0);
    return this.rowId;
  }

  async requestHostList(gameType: string, timeout = 5000): Promise<HostInfo[]> {
    const payload = encodeQueryRequest(gameType);
    this.client.send(payload, Reliability.RELIABLE_ORDERED);

    const reply = await this.waitForMessage([ID_DATABASE_QUERY_REPLY, ID_DATABASE_INCORRECT_PASSWORD], timeout);
    const replyId = reply.payload[0];

    if (replyId === ID_DATABASE_INCORRECT_PASSWORD) {
      throw new Error('Incorrect password');
    }

    const decoded = decodeQueryReply(reply.payload);
    return this.parseHosts(decoded);
  }

  unregisterHost(gameType: string, rowId?: number): void {
    const rid = rowId ?? this.rowId;
    if (rid === null) {
      throw new Error('No row_id — must register first or pass rowId');
    }
    const payload = encodeRemoveRow(gameType, rid);
    this.client.send(payload, Reliability.RELIABLE_ORDERED);
  }

  private handleMessage(msg: IncomingMessage): void {
    if (msg.payload.length === 0) return;
    const msgId = msg.payload[0] ?? 0;

    for (let i = this.pendingResolvers.length - 1; i >= 0; i--) {
      const pending = this.pendingResolvers[i];
      if (pending && pending.msgIds.includes(msgId)) {
        this.pendingResolvers.splice(i, 1);
        pending.resolve(msg);
        return;
      }
    }
  }

  private waitForMessage(msgIds: number[], timeout: number): Promise<IncomingMessage> {
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        const idx = this.pendingResolvers.findIndex((p) => p.resolve === wrappedResolve);
        if (idx >= 0) this.pendingResolvers.splice(idx, 1);
        reject(new Error('Timeout waiting for response'));
      }, timeout);

      const wrappedResolve = (msg: IncomingMessage): void => {
        clearTimeout(timer);
        resolve(msg);
      };

      this.pendingResolvers.push({
        msgIds,
        resolve: wrappedResolve,
        reject,
        timer,
      });
    });
  }

  private parseHosts(reply: { columns: Array<{ name: string; type: number }>; rows: Array<{ key: number; cells: Record<string, number | string | Uint8Array | null> }> }): HostInfo[] {
    return reply.rows.map((row) => {
      const cells = row.cells;
      const ipRaw = cells['IP address'];
      let ip = '0.0.0.0';
      if (ipRaw instanceof Uint8Array) {
        const nullIdx = ipRaw.indexOf(0);
        ip = new TextDecoder().decode(ipRaw.subarray(0, nullIdx >= 0 ? nullIdx : ipRaw.length));
      } else if (typeof ipRaw === 'string') {
        ip = ipRaw;
      }

      return {
        ip,
        port: typeof cells['Port'] === 'number' ? cells['Port'] : 0,
        gameName: typeof cells['Game name'] === 'string' ? cells['Game name'] : '',
        connectedPlayers: typeof cells['Connected players'] === 'number' ? cells['Connected players'] : 0,
        playerLimit: typeof cells['Player limit'] === 'number' ? cells['Player limit'] : 0,
        passwordProtected: Boolean(cells['Password protected']),
        comment: typeof cells['Comment'] === 'string' ? cells['Comment'] : '',
        guid: typeof cells['GUID'] === 'string' ? cells['GUID'] : '',
        nat: Boolean(cells['NAT']),
        rowId: row.key,
      };
    });
  }
}
