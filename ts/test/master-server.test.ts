import { describe, it, expect } from 'vitest';
import { Table } from '../src/master/server.js';
import { BINARY, STRING } from '../src/master/serialization.js';

function encIp(ip: string): Uint8Array {
  const bytes = new TextEncoder().encode(ip);
  const padded = new Uint8Array(16);
  padded.set(bytes.subarray(0, Math.min(bytes.length, 16)));
  return padded;
}

function decIp(bytes: Uint8Array): string {
  return new TextDecoder().decode(bytes).replace(/\0.*/, '');
}

function makeTable(publicIp: string, givenIp: string): Table {
  const table = new Table('test');
  table.addColumn('IP address', BINARY);
  table.addColumn('Game name', STRING);
  const rowId = table.getOrCreateRowForAddr(`${publicIp}:7777`);
  table.updateRow(rowId, {
    'IP address': encIp(publicIp),
    '__givenIp': encIp(givenIp),
    'Game name': 'TestServer',
  });
  return table;
}

describe('Table dual-IP query', () => {
  it('serves given IP to requester from the same public IP', () => {
    const table = makeTable('1.2.3.4', '10.0.0.5');
    const rows = table.query(null, null, null, '1.2.3.4');
    expect(rows).toHaveLength(1);
    const ip = decIp(rows[0].cells['IP address'] as Uint8Array);
    expect(ip).toBe('10.0.0.5');
  });

  it('serves public IP to requester from a different IP', () => {
    const table = makeTable('1.2.3.4', '10.0.0.5');
    const rows = table.query(null, null, null, '5.6.7.8');
    expect(rows).toHaveLength(1);
    const ip = decIp(rows[0].cells['IP address'] as Uint8Array);
    expect(ip).toBe('1.2.3.4');
  });

  it('serves public IP when requesterIp is not provided', () => {
    const table = makeTable('1.2.3.4', '10.0.0.5');
    const rows = table.query();
    expect(rows).toHaveLength(1);
    const ip = decIp(rows[0].cells['IP address'] as Uint8Array);
    expect(ip).toBe('1.2.3.4');
  });

  it('never exposes __givenIp in query results (same-IP requester)', () => {
    const table = makeTable('1.2.3.4', '10.0.0.5');
    const rows = table.query(null, null, null, '1.2.3.4');
    expect(rows[0].cells).not.toHaveProperty('__givenIp');
  });

  it('never exposes __givenIp in query results (different-IP requester)', () => {
    const table = makeTable('1.2.3.4', '10.0.0.5');
    const rows = table.query(null, null, null, '9.9.9.9');
    expect(rows[0].cells).not.toHaveProperty('__givenIp');
  });

  it('never exposes __givenIp in query results (no requesterIp)', () => {
    const table = makeTable('1.2.3.4', '10.0.0.5');
    const rows = table.query();
    expect(rows[0].cells).not.toHaveProperty('__givenIp');
  });

  it('multiple rows: each independently uses own given IP for matching requester', () => {
    const table = new Table('test');
    table.addColumn('IP address', BINARY);
    table.addColumn('Port', 1); // NUMERIC

    // Row from 1.2.3.4 with given IP 10.0.0.1
    const r0 = table.getOrCreateRowForAddr('1.2.3.4:7777');
    table.updateRow(r0, { 'IP address': encIp('1.2.3.4'), '__givenIp': encIp('10.0.0.1') });

    // Row from 5.6.7.8 with given IP 192.168.1.10
    const r1 = table.getOrCreateRowForAddr('5.6.7.8:7777');
    table.updateRow(r1, { 'IP address': encIp('5.6.7.8'), '__givenIp': encIp('192.168.1.10') });

    // Requester from 1.2.3.4 sees given IP for their own row, public for the other
    const rows = table.query(null, null, null, '1.2.3.4');
    const ipMap: Record<string, string> = {};
    for (const row of rows) {
      const ip = decIp(row.cells['IP address'] as Uint8Array);
      ipMap[ip] = ip;
    }
    expect(Object.keys(ipMap).sort()).toEqual(['10.0.0.1', '5.6.7.8'].sort());
  });
});
