"""
Python implementation of the Unity Master Server.

Uses the RakNet LightweightDatabaseServer protocol to provide server
browser functionality. Game servers register via UpdateRow; clients
query via QueryRequest.
"""

import logging
import socket
import time

from .raknet_connection import RakNetServer
from .raknet_transport import Reliability
from .master_serialization import (
    ID_DATABASE_QUERY_REQUEST, ID_DATABASE_UPDATE_ROW, ID_DATABASE_REMOVE_ROW,
    ID_DATABASE_QUERY_REPLY, ID_DATABASE_ROWID, ID_MASTERSERVER_MSG,
    NUMERIC, STRING, BINARY,
    RUM_UPDATE_EXISTING_ROW, RUM_UPDATE_OR_ADD_ROW, RUM_ADD_NEW_ROW,
    VERSION,
    decode_update_row, decode_query_request, decode_remove_row,
    encode_query_reply, encode_rowid, encode_unknown_table,
    encode_incorrect_password,
    write_huffman_string,
)
from .bitstream import BitStream

log = logging.getLogger(__name__)

INTERNAL_COLUMNS = [
    {'name': '__SystemAddress', 'type': BINARY},
    {'name': '__SystemGuid', 'type': BINARY},
    {'name': '__lastPingResponseTime', 'type': NUMERIC},
    {'name': '__nextPingSendTime', 'type': NUMERIC},
]

PING_INTERVAL = 15.0
PING_TIMEOUT = 75.0


class Table:
    def __init__(self, name, password=None):
        self.name = name
        self.password = password
        self.columns = list(INTERNAL_COLUMNS)
        self.rows = {}
        self._next_row_id = 0
        self._addr_to_row = {}

    def add_column(self, name, col_type):
        for col in self.columns:
            if col['name'] == name:
                return
        self.columns.append({'name': name, 'type': col_type})

    def column_index(self, name):
        for i, col in enumerate(self.columns):
            if col['name'] == name:
                return i
        return -1

    def allocate_row(self):
        row_id = self._next_row_id
        self._next_row_id += 1
        self.rows[row_id] = {}
        return row_id

    def update_row(self, row_id, cells):
        if row_id not in self.rows:
            return
        for name, value in cells.items():
            self.rows[row_id][name] = value

    def remove_row(self, row_id):
        if row_id in self.rows:
            for addr, rid in list(self._addr_to_row.items()):
                if rid == row_id:
                    del self._addr_to_row[addr]
            del self.rows[row_id]

    def remove_by_addr(self, addr_key):
        if addr_key in self._addr_to_row:
            row_id = self._addr_to_row.pop(addr_key)
            self.rows.pop(row_id, None)

    def get_or_create_row_for_addr(self, addr_key):
        if addr_key in self._addr_to_row:
            return self._addr_to_row[addr_key]
        old_row = self._addr_to_row.get(addr_key)
        if old_row is not None:
            self.rows.pop(old_row, None)
        row_id = self.allocate_row()
        self._addr_to_row[addr_key] = row_id
        return row_id

    def query(self, column_subset=None, filters=None, row_ids=None):
        result_rows = []
        for row_id, cells in self.rows.items():
            if row_ids and row_id not in row_ids:
                continue
            if filters:
                if not self._matches_filters(cells, filters):
                    continue
            if column_subset:
                filtered_cells = {k: v for k, v in cells.items()
                                  if k in column_subset}
            else:
                filtered_cells = dict(cells)
            result_rows.append({'key': row_id, 'cells': filtered_cells})
        return result_rows

    def _matches_filters(self, cells, filters):
        for f in filters:
            val = cells.get(f['name'])
            op = f['operation']
            fval = f['value']
            if op == 6:  # IS_EMPTY
                if val is not None:
                    return False
            elif op == 7:  # NOT_EMPTY
                if val is None:
                    return False
            elif val is None:
                return False
            elif op == 0:  # EQUAL
                if val != fval:
                    return False
            elif op == 1:  # NOT_EQUAL
                if val == fval:
                    return False
            elif op == 2:  # GREATER_THAN
                if not (val > fval):
                    return False
            elif op == 3:  # GREATER_THAN_EQ
                if not (val >= fval):
                    return False
            elif op == 4:  # LESS_THAN
                if not (val < fval):
                    return False
            elif op == 5:  # LESS_THAN_EQ
                if not (val <= fval):
                    return False
        return True


class MasterServer:
    """Python master server implementing the LightweightDatabase protocol."""

    def __init__(self, port=23466, max_connections=1000):
        self.port = port
        self._raknet = RakNetServer(port=port, viewid_stride=0,
                                    max_connections=max_connections,
                                    unity_protocol=False)
        self._tables = {}
        self._peer_tables = {}
        self._running = False
        self._last_ping_check = 0

    def start(self):
        self._raknet.start()

    def stop(self):
        self._raknet.stop()

    def tick(self, timeout=0.01):
        messages = self._raknet.poll(timeout=timeout)
        for addr, msg_id, payload, reliability, bit_length in messages:
            self._handle_message(addr, msg_id, payload)
        self._check_disconnections()
        self._check_ping_timeouts()

    def _handle_message(self, addr, msg_id, payload):
        if msg_id == ID_DATABASE_UPDATE_ROW:
            self._on_update_row(addr, payload)
        elif msg_id == ID_DATABASE_QUERY_REQUEST:
            self._on_query_request(addr, payload)
        elif msg_id == ID_DATABASE_REMOVE_ROW:
            self._on_remove_row(addr, payload)

    def _check_version(self, addr, version):
        if version == VERSION:
            return True
        log.info("Version mismatch from %s: %s", addr, list(version))
        msg = f"Version mismatch: client={list(version)} server={list(VERSION)}"
        self._send_version_error(addr, msg)
        return False

    def _send_version_error(self, addr, message):
        bs = BitStream()
        bs.write_u8(ID_MASTERSERVER_MSG)
        write_huffman_string(bs, message)
        self._send(addr, bs.to_bytes())

    def _on_update_row(self, addr, payload):
        try:
            msg = decode_update_row(payload)
        except Exception:
            log.warning("Failed to decode UpdateRow from %s", addr, exc_info=True)
            return

        if not self._check_version(addr, msg['version']):
            return

        table_name = msg['table']
        table = self._get_or_create_table(table_name)

        if table.password and msg['password'] != table.password:
            self._send(addr, encode_incorrect_password())
            return

        addr_key = f"{addr[0]}:{addr[1]}"
        update_mode = msg['update_mode']

        if update_mode == RUM_UPDATE_OR_ADD_ROW:
            row_id = table.get_or_create_row_for_addr(addr_key)
        elif update_mode == RUM_ADD_NEW_ROW:
            old_row = table._addr_to_row.get(addr_key)
            if old_row is not None:
                table.rows.pop(old_row, None)
            row_id = table.allocate_row()
            table._addr_to_row[addr_key] = row_id
        elif update_mode == RUM_UPDATE_EXISTING_ROW:
            if msg['row_id'] is not None and msg['row_id'] in table.rows:
                row_id = msg['row_id']
            elif addr_key in table._addr_to_row:
                row_id = table._addr_to_row[addr_key]
            else:
                return
        else:
            return

        for cell in msg['cells']:
            table.add_column(cell['name'], cell['type'])

        cells = {}
        for cell in msg['cells']:
            cells[cell['name']] = cell['value']

        ip_str = addr[0]
        ip_bytes = ip_str.encode('ascii')
        ip_padded = ip_bytes + b'\x00' * (16 - len(ip_bytes))
        cells['IP address'] = ip_padded
        table.add_column('IP address', BINARY)

        cells['Port'] = float(addr[1])
        table.add_column('Port', NUMERIC)

        now = time.monotonic() * 1000
        cells['__SystemAddress'] = _encode_system_address(addr)
        cells['__SystemGuid'] = b'\x00' * 16
        cells['__lastPingResponseTime'] = now
        cells['__nextPingSendTime'] = now + PING_INTERVAL * 1000

        table.update_row(row_id, cells)

        if addr not in self._peer_tables:
            self._peer_tables[addr] = set()
        self._peer_tables[addr].add(table_name)

        self._send(addr, encode_rowid(row_id))
        log.info("Registered %s in table '%s' (row %d)", addr, table_name, row_id)

    def _on_query_request(self, addr, payload):
        try:
            msg = decode_query_request(payload)
        except Exception:
            log.warning("Failed to decode QueryRequest from %s", addr, exc_info=True)
            return

        if not self._check_version(addr, msg['version']):
            return

        table_name = msg['table']
        table = self._tables.get(table_name)

        if table is None or len(table.rows) == 0:
            self._send(addr, bytes([ID_DATABASE_QUERY_REPLY]))
            return

        if table.password and msg['password'] != table.password:
            self._send(addr, encode_incorrect_password())
            return

        rows = table.query(
            column_subset=msg['column_subset'] or None,
            filters=msg['filters'] or None,
            row_ids=msg['row_ids'] or None,
        )

        columns = list(table.columns)
        reply = encode_query_reply(columns, rows)
        self._send(addr, reply)
        log.info("Query reply to %s: %d rows from '%s'", addr, len(rows), table_name)

    def _on_remove_row(self, addr, payload):
        try:
            msg = decode_remove_row(payload)
        except Exception:
            log.warning("Failed to decode RemoveRow from %s", addr, exc_info=True)
            return

        table = self._tables.get(msg['table'])
        if table is None:
            self._send(addr, encode_unknown_table())
            return

        if table.password and msg['password'] != table.password:
            self._send(addr, encode_incorrect_password())
            return

        table.remove_row(msg['row_id'])
        log.info("Removed row %d from '%s'", msg['row_id'], msg['table'])

    def _check_disconnections(self):
        connected = set(self._raknet.peers.keys())
        for addr in list(self._peer_tables.keys()):
            if addr not in connected:
                table_names = self._peer_tables.pop(addr, set())
                addr_key = f"{addr[0]}:{addr[1]}"
                for tname in table_names:
                    table = self._tables.get(tname)
                    if table:
                        table.remove_by_addr(addr_key)
                        log.info("Removed %s from table '%s' (disconnect)",
                                 addr, tname)
                        if not table.rows:
                            del self._tables[tname]

    def _check_ping_timeouts(self):
        now = time.monotonic() * 1000
        if now - self._last_ping_check < PING_INTERVAL * 1000:
            return
        self._last_ping_check = now

        for tname in list(self._tables.keys()):
            table = self._tables[tname]
            stale_rows = []
            for row_id, cells in table.rows.items():
                last_ping = cells.get('__lastPingResponseTime', 0)
                if now - last_ping > PING_TIMEOUT * 1000:
                    stale_rows.append(row_id)
            for row_id in stale_rows:
                table.remove_row(row_id)
                log.info("Removed stale row %d from '%s' (ping timeout)",
                         row_id, tname)
            if not table.rows:
                del self._tables[tname]

    def _get_or_create_table(self, name):
        if name not in self._tables:
            self._tables[name] = Table(name)
            log.info("Created table '%s'", name)
        return self._tables[name]

    def _send(self, addr, payload):
        peer = self._raknet.peers.get(addr)
        if peer:
            peer.send_message(payload, Reliability.RELIABLE_ORDERED)

    def get_tables(self):
        return dict(self._tables)


def _encode_system_address(addr):
    ip_bytes = socket.inet_aton(addr[0])
    port_bytes = addr[1].to_bytes(2, 'big')
    return ip_bytes + port_bytes
