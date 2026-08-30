import { RakNetServer } from '../raknet/connection.js';
import type { ClientSession } from '../raknet/connection.js';
import { Reliability } from '../raknet/types.js';
import type { IncomingMessage } from '../raknet/types.js';
import { UdpSocket } from '../raknet/socket.js';
import {
  ID_DATABASE_UPDATE_ROW,
  ID_DATABASE_QUERY_REQUEST,
  ID_DATABASE_REMOVE_ROW,
  ID_DATABASE_QUERY_REPLY,
  ID_MASTERSERVER_MSG,
  NUMERIC, BINARY,
  RUM_UPDATE_EXISTING_ROW, RUM_UPDATE_OR_ADD_ROW, RUM_ADD_NEW_ROW,
  VERSION,
  decodeUpdateRow,
  decodeQueryRequest,
  decodeRemoveRow,
  encodeQueryReply,
  encodeRowId,
  encodeUnknownTable,
  encodeIncorrectPassword,
} from './serialization.js';
import type { Column } from './serialization.js';
import { BitStream } from '../bitstream.js';
import { encodeStringForWire } from '../huffman.js';

const INTERNAL_COLUMNS: Column[] = [
  { name: '__SystemAddress', type: BINARY },
  { name: '__SystemGuid', type: BINARY },
  { name: '__lastPingResponseTime', type: NUMERIC },
  { name: '__nextPingSendTime', type: NUMERIC },
  // Stores the IP the registrant supplied in the payload (may be a LAN IP).
  // Never returned to query clients — used to serve the right IP per requester.
  { name: '__givenIp', type: BINARY },
];

const PING_INTERVAL = 15000;
const _PING_TIMEOUT = 75000;

type EventHandler<T extends unknown[]> = (...args: T) => void;

export class Table {
  name: string;
  password: string | null;
  columns: Column[];
  rows: Map<number, Record<string, number | string | Uint8Array | null>>;
  private nextRowId = 0;
  addrToRow: Map<string, number> = new Map();

  constructor(name: string, password: string | null = null) {
    this.name = name;
    this.password = password;
    this.columns = [...INTERNAL_COLUMNS];
    this.rows = new Map();
  }

  addColumn(name: string, colType: number): void {
    for (const col of this.columns) {
      if (col.name === name) return;
    }
    this.columns.push({ name, type: colType });
  }

  allocateRow(): number {
    const rowId = this.nextRowId;
    this.nextRowId++;
    this.rows.set(rowId, {});
    return rowId;
  }

  updateRow(rowId: number, cells: Record<string, number | string | Uint8Array | null>): void {
    const row = this.rows.get(rowId);
    if (!row) return;
    for (const [name, value] of Object.entries(cells)) {
      row[name] = value;
    }
  }

  removeRow(rowId: number): void {
    if (!this.rows.has(rowId)) return;
    for (const [addr, rid] of this.addrToRow.entries()) {
      if (rid === rowId) {
        this.addrToRow.delete(addr);
      }
    }
    this.rows.delete(rowId);
  }

  removeByAddr(addrKey: string): void {
    const rowId = this.addrToRow.get(addrKey);
    if (rowId !== undefined) {
      this.addrToRow.delete(addrKey);
      this.rows.delete(rowId);
    }
  }

  getOrCreateRowForAddr(addrKey: string): number {
    const existing = this.addrToRow.get(addrKey);
    if (existing !== undefined) return existing;
    const rowId = this.allocateRow();
    this.addrToRow.set(addrKey, rowId);
    return rowId;
  }

  query(
    columnSubset?: string[] | null,
    filters?: Array<{ name: string; operation: number; value: number | string | Uint8Array | null }> | null,
    rowIds?: number[] | null,
    requesterIp?: string,
  ): Array<{ key: number; cells: Record<string, number | string | Uint8Array | null> }> {
    const result: Array<{ key: number; cells: Record<string, number | string | Uint8Array | null> }> = [];
    const rowIdSet = rowIds ? new Set(rowIds) : null;

    for (const [rowId, cells] of this.rows) {
      if (rowIdSet && !rowIdSet.has(rowId)) continue;
      if (filters && !this.matchesFilters(cells, filters)) continue;

      let filteredCells: Record<string, number | string | Uint8Array | null>;
      if (columnSubset && columnSubset.length > 0) {
        const subset = new Set(columnSubset);
        filteredCells = {};
        for (const [k, v] of Object.entries(cells)) {
          if (subset.has(k)) filteredCells[k] = v;
        }
      } else {
        filteredCells = { ...cells };
      }

      // Serve the registrant's given IP to requesters coming from the same
      // public IP (LAN peers), and the actual connection IP to everyone else.
      if ('IP address' in filteredCells && requesterIp !== undefined) {
        const publicIpBytes = cells['IP address'];
        const publicIp = publicIpBytes instanceof Uint8Array
          ? new TextDecoder().decode(publicIpBytes).replace(/\0.*/, '')
          : null;
        if (publicIp === requesterIp) {
          const givenIp = cells['__givenIp'];
          if (givenIp instanceof Uint8Array) filteredCells['IP address'] = givenIp;
        }
      }
      // __givenIp is always internal — never expose it to query clients.
      delete filteredCells['__givenIp'];

      result.push({ key: rowId, cells: filteredCells });
    }
    return result;
  }

  private matchesFilters(
    cells: Record<string, number | string | Uint8Array | null>,
    filters: Array<{ name: string; operation: number; value: number | string | Uint8Array | null }>,
  ): boolean {
    for (const f of filters) {
      const val = cells[f.name] ?? null;
      const fval = f.value;
      if (f.operation === 6) {
        if (val !== null) return false;
      } else if (f.operation === 7) {
        if (val === null) return false;
      } else if (val === null) {
        return false;
      } else if (f.operation === 0) {
        if (val !== fval) return false;
      } else if (f.operation === 1) {
        if (val === fval) return false;
      } else if (typeof val === 'number' && typeof fval === 'number') {
        if (f.operation === 2 && !(val > fval)) return false;
        if (f.operation === 3 && !(val >= fval)) return false;
        if (f.operation === 4 && !(val < fval)) return false;
        if (f.operation === 5 && !(val <= fval)) return false;
      }
    }
    return true;
  }
}

export interface MasterServerOptions {
  port?: number;
  maxConnections?: number;
}

export class MasterServer {
  readonly port: number;
  private raknet: RakNetServer;
  private socket: UdpSocket;
  private tables: Map<string, Table> = new Map();
  private peerTables: Map<string, Set<string>> = new Map();
  private lastPingCheck = 0;
  private registrationHandlers: Array<EventHandler<[string, number]>> = [];

  constructor(options: MasterServerOptions = {}) {
    this.port = options.port ?? 23466;
    this.socket = new UdpSocket();
    this.raknet = new RakNetServer(this.socket, {
      port: this.port,
      viewIdStride: 0,
    });
    this.raknet.onMessage((session, msg) => {
      this.handleMessage(session, msg);
    });
    this.raknet.onDisconnect((session) => {
      this.handleDisconnect(session);
    });
  }

  async start(): Promise<void> {
    await this.raknet.start();
  }

  async stop(): Promise<void> {
    await this.raknet.stop();
  }

  onRegistration(handler: EventHandler<[string, number]>): void {
    this.registrationHandlers.push(handler);
  }

  getTables(): Map<string, Table> {
    return new Map(this.tables);
  }

  private handleMessage(session: ClientSession, msg: IncomingMessage): void {
    if (msg.payload.length === 0) return;
    const msgId = msg.payload[0];
    if (msgId === ID_DATABASE_UPDATE_ROW) {
      this.onUpdateRow(session, msg.payload);
    } else if (msgId === ID_DATABASE_QUERY_REQUEST) {
      this.onQueryRequest(session, msg.payload);
    } else if (msgId === ID_DATABASE_REMOVE_ROW) {
      this.onRemoveRow(session, msg.payload);
    }
  }

  private checkVersion(session: ClientSession, version: Uint8Array): boolean {
    if (version[0] === VERSION[0] && version[1] === VERSION[1] && version[2] === VERSION[2]) {
      return true;
    }
    const bs = new BitStream();
    bs.writeU8(ID_MASTERSERVER_MSG);
    const msg = 'Version mismatch: client=[' + String(version[0]) + ',' + String(version[1]) + ',' + String(version[2]) + '] server=[' + String(VERSION[0]) + ',' + String(VERSION[1]) + ',' + String(VERSION[2]) + ']';
    writeHuffmanStringToBs(bs, msg);
    this.send(session, bs.toBytes());
    return false;
  }

  private onUpdateRow(session: ClientSession, payload: Uint8Array): void {
    let msg;
    try {
      msg = decodeUpdateRow(payload);
    } catch {
      return;
    }

    if (!this.checkVersion(session, msg.version)) return;

    const tableName = msg.table;
    const table = this.getOrCreateTable(tableName);

    if (table.password && msg.password !== table.password) {
      this.send(session, encodeIncorrectPassword());
      return;
    }

    const addrKey = session.address.host + ':' + String(session.address.port);
    const updateMode = msg.updateMode;
    let rowId: number;

    if (updateMode === RUM_UPDATE_OR_ADD_ROW) {
      rowId = table.getOrCreateRowForAddr(addrKey);
    } else if (updateMode === RUM_ADD_NEW_ROW) {
      const oldRow = table.addrToRow.get(addrKey);
      if (oldRow !== undefined) {
        table.rows.delete(oldRow);
      }
      rowId = table.allocateRow();
      table.addrToRow.set(addrKey, rowId);
    } else if (updateMode === RUM_UPDATE_EXISTING_ROW) {
      if (msg.rowId !== null && table.rows.has(msg.rowId)) {
        rowId = msg.rowId;
      } else if (table.addrToRow.has(addrKey)) {
        rowId = table.addrToRow.get(addrKey) as number;
      } else {
        return;
      }
    } else {
      return;
    }

    for (const cell of msg.cells) {
      table.addColumn(cell.name, cell.type);
    }

    const cells: Record<string, number | string | Uint8Array | null> = {};
    for (const cell of msg.cells) {
      cells[cell.name] = cell.value;
    }

    // Save the registrant's given IP before we overwrite it with the actual
    // source address, so query() can serve it back to same-IP requesters.
    const givenIpRaw = cells['IP address'];
    const givenIpBytes = givenIpRaw instanceof Uint8Array ? givenIpRaw : new Uint8Array(16);
    cells['__givenIp'] = givenIpBytes;

    const ipStr = session.address.host;
    const ipBytes = new TextEncoder().encode(ipStr);
    const ipPadded = new Uint8Array(16);
    ipPadded.set(ipBytes.subarray(0, Math.min(ipBytes.length, 16)));
    cells['IP address'] = ipPadded;
    table.addColumn('IP address', BINARY);

    cells['Port'] = session.address.port;
    table.addColumn('Port', NUMERIC);

    const now = Date.now();
    cells['__SystemAddress'] = encodeSystemAddress(session.address.host, session.address.port);
    cells['__SystemGuid'] = new Uint8Array(16);
    cells['__lastPingResponseTime'] = now;
    cells['__nextPingSendTime'] = now + PING_INTERVAL;

    table.updateRow(rowId, cells);

    const sessionKey = session.address.host + ':' + String(session.address.port);
    if (!this.peerTables.has(sessionKey)) {
      this.peerTables.set(sessionKey, new Set());
    }
    this.peerTables.get(sessionKey)?.add(tableName);

    this.send(session, encodeRowId(rowId));

    for (const h of this.registrationHandlers) {
      h(tableName, rowId);
    }
  }

  private onQueryRequest(session: ClientSession, payload: Uint8Array): void {
    let msg;
    try {
      msg = decodeQueryRequest(payload);
    } catch {
      return;
    }

    if (!this.checkVersion(session, msg.version)) return;

    const table = this.tables.get(msg.table);

    if (!table || table.rows.size === 0) {
      this.send(session, new Uint8Array([ID_DATABASE_QUERY_REPLY]));
      return;
    }

    if (table.password && msg.password !== table.password) {
      this.send(session, encodeIncorrectPassword());
      return;
    }

    const rows = table.query(
      msg.columnSubset.length > 0 ? msg.columnSubset : null,
      msg.filters.length > 0 ? msg.filters : null,
      msg.rowIds.length > 0 ? msg.rowIds : null,
      session.address.host,
    );

    const reply = encodeQueryReply(table.columns, rows);
    this.send(session, reply);
  }

  private onRemoveRow(session: ClientSession, payload: Uint8Array): void {
    let msg;
    try {
      msg = decodeRemoveRow(payload);
    } catch {
      return;
    }

    const table = this.tables.get(msg.table);
    if (!table) {
      this.send(session, encodeUnknownTable());
      return;
    }

    if (table.password && msg.password !== table.password) {
      this.send(session, encodeIncorrectPassword());
      return;
    }

    table.removeRow(msg.rowId);
  }

  private handleDisconnect(session: ClientSession): void {
    const key = session.address.host + ':' + String(session.address.port);
    const tableNames = this.peerTables.get(key);
    if (!tableNames) return;
    this.peerTables.delete(key);

    for (const tname of tableNames) {
      const table = this.tables.get(tname);
      if (table) {
        table.removeByAddr(key);
        if (table.rows.size === 0) {
          this.tables.delete(tname);
        }
      }
    }
  }

  private getOrCreateTable(name: string): Table {
    let table = this.tables.get(name);
    if (!table) {
      table = new Table(name);
      this.tables.set(name, table);
    }
    return table;
  }

  private send(session: ClientSession, payload: Uint8Array): void {
    this.raknet.sendTo(session, payload, Reliability.RELIABLE_ORDERED);
  }
}

function writeHuffmanStringToBs(bs: BitStream, s: string): void {
  const bits = encodeStringForWire(s);
  bs.writeCompressedU32(bits.length);
  for (let i = 0; i < bits.length; i++) {
    bs.writeBit(bits[i] === '1' ? 1 : 0);
  }
}

function encodeSystemAddress(host: string, port: number): Uint8Array {
  const parts = host.split('.').map(Number);
  const result = new Uint8Array(6);
  result[0] = parts[0] ?? 0;
  result[1] = parts[1] ?? 0;
  result[2] = parts[2] ?? 0;
  result[3] = parts[3] ?? 0;
  result[4] = (port >> 8) & 0xff;
  result[5] = port & 0xff;
  return result;
}
