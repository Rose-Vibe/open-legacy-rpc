"""
Python client for the Unity Master Server.

Connects to a master server (Unity C++ or Python) and provides:
- register_host(): register a game server
- request_host_list(): query for available servers
- unregister_host(): remove registration
"""

import logging
import time

from .raknet_connection import RakNetClient
from .raknet_transport import Reliability
from .master_serialization import (
    ID_DATABASE_QUERY_REQUEST, ID_DATABASE_UPDATE_ROW, ID_DATABASE_REMOVE_ROW,
    ID_DATABASE_QUERY_REPLY, ID_DATABASE_ROWID,
    ID_DATABASE_UNKNOWN_TABLE, ID_DATABASE_INCORRECT_PASSWORD,
    NUMERIC, STRING, BINARY,
    RUM_UPDATE_OR_ADD_ROW,
    encode_update_row, encode_query_request, encode_remove_row,
    decode_query_reply,
)

log = logging.getLogger(__name__)


class MasterClient:
    """Client for the Unity Master Server protocol."""

    def __init__(self):
        self._client = RakNetClient(unity_protocol=False)
        self._row_id = None
        self._last_reply = None
        self._error = None
        self._registration = None
        self._last_reregister = 0

    def connect(self, host='127.0.0.1', port=23466, timeout=5.0):
        self._client.connect(host, port, timeout=timeout)

    def disconnect(self):
        self._client.disconnect()

    @property
    def connected(self):
        from .raknet_connection import ConnectionState
        return self._client.state == ConnectionState.CONNECTED

    def register_host(self, game_type, name, comment='',
                      player_count=0, player_limit=4,
                      password_protected=False, use_nat=False,
                      port=7777, timeout=5.0):
        """Register a game host with the master server. Returns the assigned row_id."""
        ip_bytes = b'0.0.0.0\x00' + b'\x00' * 8
        cells = [
            {'name': 'NAT', 'type': NUMERIC, 'value': 1.0 if use_nat else 0.0},
            {'name': 'Game name', 'type': STRING, 'value': name},
            {'name': 'Connected players', 'type': NUMERIC, 'value': float(player_count)},
            {'name': 'Player limit', 'type': NUMERIC, 'value': float(player_limit)},
            {'name': 'Password protected', 'type': NUMERIC,
             'value': 1.0 if password_protected else 0.0},
            {'name': 'IP address', 'type': BINARY, 'value': ip_bytes},
            {'name': 'Port', 'type': NUMERIC, 'value': float(port)},
            {'name': 'Comment', 'type': STRING, 'value': comment},
        ]
        payload = encode_update_row(game_type, cells,
                                    update_mode=RUM_UPDATE_OR_ADD_ROW)
        self._registration = {
            'game_type': game_type, 'name': name, 'comment': comment,
            'player_count': player_count, 'player_limit': player_limit,
            'password_protected': password_protected, 'use_nat': use_nat,
            'port': port,
        }
        self._client.send_message(payload, Reliability.RELIABLE_ORDERED)
        self._last_reregister = time.monotonic()

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            msgs = self._client.poll(timeout=0.1)
            for msg_id, data, rel, bits in msgs:
                if msg_id == ID_DATABASE_ROWID:
                    if len(data) < 5:
                        log.warning("RowID response too short: %d bytes", len(data))
                        continue
                    self._row_id = int.from_bytes(data[1:5], 'big')
                    log.info("Registered with row_id=%d", self._row_id)
                    return self._row_id
                elif msg_id == ID_DATABASE_INCORRECT_PASSWORD:
                    raise PermissionError("Incorrect password")
                elif msg_id == ID_DATABASE_UNKNOWN_TABLE:
                    raise ValueError("Unknown table")
        raise TimeoutError("No RowID response")

    def request_host_list(self, game_type, timeout=5.0):
        """Query the master server for available hosts. Returns list of host dicts."""
        payload = encode_query_request(game_type)
        self._client.send_message(payload, Reliability.RELIABLE_ORDERED)

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            msgs = self._client.poll(timeout=0.1)
            for msg_id, data, rel, bits in msgs:
                if msg_id == ID_DATABASE_QUERY_REPLY:
                    reply = decode_query_reply(data)
                    self._last_reply = reply
                    hosts = self._parse_hosts(reply)
                    return hosts
                elif msg_id == ID_DATABASE_INCORRECT_PASSWORD:
                    raise PermissionError("Incorrect password")
        raise TimeoutError("No QueryReply response")

    def unregister_host(self, game_type, row_id=None):
        rid = row_id if row_id is not None else self._row_id
        if rid is None:
            raise ValueError("No row_id — must register first or pass row_id")
        payload = encode_remove_row(game_type, rid)
        self._client.send_message(payload, Reliability.RELIABLE_ORDERED)

    REREGISTER_INTERVAL = 300.0

    def poll(self, timeout=0.0):
        msgs = self._client.poll(timeout)
        self._maybe_reregister()
        return msgs

    def _maybe_reregister(self):
        if self._registration is None:
            return
        if time.monotonic() - self._last_reregister < self.REREGISTER_INTERVAL:
            return
        r = self._registration
        ip_bytes = b'0.0.0.0\x00' + b'\x00' * 8
        cells = [
            {'name': 'NAT', 'type': NUMERIC,
             'value': 1.0 if r['use_nat'] else 0.0},
            {'name': 'Game name', 'type': STRING, 'value': r['name']},
            {'name': 'Connected players', 'type': NUMERIC,
             'value': float(r['player_count'])},
            {'name': 'Player limit', 'type': NUMERIC,
             'value': float(r['player_limit'])},
            {'name': 'Password protected', 'type': NUMERIC,
             'value': 1.0 if r['password_protected'] else 0.0},
            {'name': 'IP address', 'type': BINARY, 'value': ip_bytes},
            {'name': 'Port', 'type': NUMERIC, 'value': float(r['port'])},
            {'name': 'Comment', 'type': STRING, 'value': r['comment']},
        ]
        payload = encode_update_row(r['game_type'], cells,
                                    update_mode=RUM_UPDATE_OR_ADD_ROW)
        self._client.send_message(payload, Reliability.RELIABLE_ORDERED)
        self._last_reregister = time.monotonic()
        log.debug("Re-registered with master server")

    def _parse_hosts(self, reply):
        hosts = []
        for row in reply['rows']:
            cells = row['cells']
            ip_raw = cells.get('IP address', b'')
            if isinstance(ip_raw, bytes):
                ip = ip_raw.split(b'\x00')[0].decode('ascii', errors='replace')
            else:
                ip = str(ip_raw)

            host = {
                'ip': ip,
                'port': int(cells.get('Port', 0)),
                'game_name': cells.get('Game name', ''),
                'connected_players': int(cells.get('Connected players', 0)),
                'player_limit': int(cells.get('Player limit', 0)),
                'password_protected': bool(cells.get('Password protected', 0)),
                'comment': cells.get('Comment', ''),
                'guid': cells.get('GUID', ''),
                'nat': bool(cells.get('NAT', 0)),
                'row_id': row['key'],
            }
            hosts.append(host)
        return hosts
