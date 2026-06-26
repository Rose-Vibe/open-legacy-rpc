"""
Tests for the master server protocol — serialization, server, and client.
"""

import time
import threading
import unittest

from protocol.master_serialization import (
    NUMERIC, STRING, BINARY,
    ID_DATABASE_QUERY_REPLY, ID_DATABASE_UPDATE_ROW, ID_DATABASE_QUERY_REQUEST,
    ID_DATABASE_REMOVE_ROW, ID_DATABASE_ROWID,
    RUM_UPDATE_OR_ADD_ROW, RUM_UPDATE_EXISTING_ROW, RUM_ADD_NEW_ROW,
    decode_update_row, encode_update_row,
    decode_query_request, encode_query_request,
    decode_query_reply, encode_query_reply,
    decode_remove_row, encode_remove_row,
    encode_rowid, read_huffman_string, write_huffman_string,
    read_cell, write_cell,
)
from protocol.bitstream import BitStream
from protocol.master_server import MasterServer
from protocol.master_client import MasterClient


class TestHuffmanStringSerialization(unittest.TestCase):
    def _roundtrip(self, s):
        bs = BitStream()
        write_huffman_string(bs, s)
        bs2 = BitStream(bs.to_bytes())
        return read_huffman_string(bs2)

    def test_empty_string(self):
        self.assertEqual(self._roundtrip(''), '')

    def test_short_string(self):
        self.assertEqual(self._roundtrip('hello'), 'hello')

    def test_game_type(self):
        self.assertEqual(self._roundtrip('TestGame'), 'TestGame')

    def test_column_name(self):
        self.assertEqual(self._roundtrip('Connected players'), 'Connected players')

    def test_internal_column(self):
        self.assertEqual(self._roundtrip('__SystemAddress'), '__SystemAddress')

    def test_special_chars(self):
        self.assertEqual(self._roundtrip('My Server (v2.1)'), 'My Server (v2.1)')


class TestCellSerialization(unittest.TestCase):
    def _roundtrip(self, value, col_type):
        bs = BitStream()
        write_cell(bs, value, col_type)
        bs2 = BitStream(bs.to_bytes())
        return read_cell(bs2, col_type)

    def test_numeric(self):
        self.assertEqual(self._roundtrip(42.0, NUMERIC), 42.0)

    def test_numeric_zero(self):
        self.assertEqual(self._roundtrip(0.0, NUMERIC), 0.0)

    def test_numeric_empty(self):
        self.assertIsNone(self._roundtrip(None, NUMERIC))

    def test_string(self):
        self.assertEqual(self._roundtrip('hello world', STRING), 'hello world')

    def test_string_empty_value(self):
        self.assertIsNone(self._roundtrip(None, STRING))

    def test_binary(self):
        data = b'10.200.1.2\x00\x00\x00\x00\x00\x00'
        self.assertEqual(self._roundtrip(data, BINARY), data)

    def test_binary_empty(self):
        self.assertIsNone(self._roundtrip(None, BINARY))


class TestUpdateRowSerialization(unittest.TestCase):
    def test_roundtrip(self):
        cells = [
            {'name': 'NAT', 'type': NUMERIC, 'value': 0.0},
            {'name': 'Game name', 'type': STRING, 'value': 'MyServer'},
            {'name': 'Port', 'type': NUMERIC, 'value': 7777.0},
            {'name': 'IP address', 'type': BINARY, 'value': b'1.2.3.4\x00' + b'\x00' * 8},
        ]
        encoded = encode_update_row('TestGame', cells, update_mode=RUM_UPDATE_OR_ADD_ROW)
        decoded = decode_update_row(encoded)

        self.assertEqual(decoded['table'], 'TestGame')
        self.assertEqual(decoded['update_mode'], RUM_UPDATE_OR_ADD_ROW)
        self.assertIsNone(decoded['row_id'])
        self.assertEqual(len(decoded['cells']), 4)
        self.assertEqual(decoded['cells'][0]['name'], 'NAT')
        self.assertEqual(decoded['cells'][0]['value'], 0.0)
        self.assertEqual(decoded['cells'][1]['value'], 'MyServer')

    def test_with_row_id(self):
        cells = [{'name': 'Port', 'type': NUMERIC, 'value': 8888.0}]
        encoded = encode_update_row('Game', cells, update_mode=RUM_UPDATE_EXISTING_ROW, row_id=5)
        decoded = decode_update_row(encoded)
        self.assertEqual(decoded['row_id'], 5)
        self.assertEqual(decoded['update_mode'], RUM_UPDATE_EXISTING_ROW)

    def test_decode_captured_update_row(self):
        """Decode the UpdateRow captured from Unity 2018.1.6f1."""
        captured = bytes.fromhex(
            '4c020000000000185486ed5a6d028041000000020312a54950000000000000000000'
            '000000c15a6d0726d02804000000487deba90ddd58333c650000002c4ed822145877'
            '524d58ced58000000000000000000000000813b24d58cf926896a004010000000000'
            '0000000002c4ec6dee98cbba998b14587000000000000000000000000071aa76767'
            '3b237b4040000001031302e3230302e312e320000000000000000000c4ec8cd80102'
            'f9b80000000000000000513b634d015a020000002058ddd5b1a234d0158'
        )
        decoded = decode_update_row(captured)
        self.assertEqual(decoded['table'], 'TestGame')
        self.assertEqual(decoded['version'], b'\x02\x00\x00')
        self.assertEqual(decoded['update_mode'], 1)
        self.assertEqual(len(decoded['cells']), 8)
        names = [c['name'] for c in decoded['cells']]
        self.assertIn('NAT', names)
        self.assertIn('Game name', names)
        self.assertIn('Comment', names)
        game_name = next(c for c in decoded['cells'] if c['name'] == 'Game name')
        self.assertEqual(game_name['value'], 'MyTestServer')


class TestQueryRequestSerialization(unittest.TestCase):
    def test_roundtrip_simple(self):
        encoded = encode_query_request('DistanceGame')
        decoded = decode_query_request(encoded)
        self.assertEqual(decoded['table'], 'DistanceGame')
        self.assertEqual(decoded['column_subset'], [])
        self.assertEqual(decoded['filters'], [])
        self.assertEqual(decoded['row_ids'], [])

    def test_decode_captured_query(self):
        captured = bytes.fromhex('4b020000000000185486ed5a6d0280000000')
        decoded = decode_query_request(captured)
        self.assertEqual(decoded['table'], 'TestGame')
        self.assertEqual(decoded['version'], b'\x02\x00\x00')


class TestQueryReplySerialization(unittest.TestCase):
    def test_roundtrip(self):
        columns = [
            {'name': 'Game name', 'type': STRING},
            {'name': 'Port', 'type': NUMERIC},
        ]
        rows = [
            {'key': 0, 'cells': {'Game name': 'Server1', 'Port': 7777.0}},
            {'key': 1, 'cells': {'Game name': 'Server2', 'Port': 7778.0}},
        ]
        encoded = encode_query_reply(columns, rows)
        decoded = decode_query_reply(encoded)
        self.assertEqual(len(decoded['columns']), 2)
        self.assertEqual(len(decoded['rows']), 2)
        self.assertEqual(decoded['rows'][0]['cells']['Game name'], 'Server1')
        self.assertEqual(decoded['rows'][1]['cells']['Port'], 7778.0)

    def test_empty_reply(self):
        encoded = encode_query_reply([], [])
        decoded = decode_query_reply(encoded)
        self.assertEqual(decoded['columns'], [])
        self.assertEqual(decoded['rows'], [])

    def test_decode_captured_reply(self):
        captured = bytes.fromhex(
            '4e0000000d0000003455b1ab635657bb1a2a39d91bda810000001'
            '62ad8d5b1ab2bdd8d15a5a38080000011156c6ad8c9b773b10a63'
            '20da905b1524d020000000078ab6356c4854ee76214d560275493'
            '40000000001018952a4a800000000c15a6d0726d02804000000b1'
            '3b60885161dd4935633b5600000000409d926ac67c9344b500000'
            '0002c4ec6dee98cbba998b14587000000000e354ecece7646f680'
            '8000000313b233600000000289db1a680ad01000000142b4ab9a8'
            'ce80800000008000000080000006800000000000000187f000001'
            '6e1e0000000100000008007a1cc9c12f5506000000000000000000'
            '00000002208129f8000000000000000190410a2c00000000000000'
            '01000000000000000000000000a000000243ef5d486eeac199e328'
            '0000003000000000000000000000001c80200000000000000000001'
            '0000000000000000000000009000000080031302e3230302e312e32'
            '0000000000000000000a205f370000000000000000058000000816'
            '37756c688d3405600000018000000604eaabae7756d5749d55e151'
            'aafabc15b55d7512ae8adab6a8'
        )
        decoded = decode_query_reply(captured)
        self.assertEqual(len(decoded['columns']), 13)
        self.assertEqual(len(decoded['rows']), 1)
        row = decoded['rows'][0]
        self.assertEqual(row['cells']['Game name'], 'MyTestServer')
        self.assertEqual(row['cells']['Port'], 7790.0)


class TestRemoveRowSerialization(unittest.TestCase):
    def test_roundtrip(self):
        encoded = encode_remove_row('TestGame', 42)
        decoded = decode_remove_row(encoded)
        self.assertEqual(decoded['table'], 'TestGame')
        self.assertEqual(decoded['row_id'], 42)
        self.assertIsNone(decoded['password'])


class TestMasterServerIntegration(unittest.TestCase):
    """Integration tests: Python master server + Python client."""

    def _start_server(self, port):
        server = MasterServer(port=port)
        server.start()
        return server

    def _run_server(self, server, duration=2.0):
        deadline = time.monotonic() + duration
        while time.monotonic() < deadline:
            server.tick(timeout=0.01)
            time.sleep(0.005)

    def test_register_and_query(self):
        port = 24466
        server = self._start_server(port)
        server_thread = threading.Thread(
            target=self._run_server, args=(server, 3.0), daemon=True)
        server_thread.start()
        time.sleep(0.2)

        try:
            # Register a host
            registrar = MasterClient()
            registrar.connect('127.0.0.1', port, timeout=2.0)
            row_id = registrar.register_host(
                'TestGame', 'MyServer', comment='hello',
                player_count=2, player_limit=8, port=7777)
            self.assertIsNotNone(row_id)

            time.sleep(0.3)

            # Query from another client
            querier = MasterClient()
            querier.connect('127.0.0.1', port, timeout=2.0)
            hosts = querier.request_host_list('TestGame')
            self.assertEqual(len(hosts), 1)
            self.assertEqual(hosts[0]['game_name'], 'MyServer')
            self.assertEqual(hosts[0]['comment'], 'hello')
            self.assertEqual(hosts[0]['connected_players'], 2)
            self.assertEqual(hosts[0]['player_limit'], 8)

            querier.disconnect()
            registrar.disconnect()
        finally:
            server.stop()
            server_thread.join(timeout=2.0)

    def test_query_empty_table(self):
        port = 24467
        server = self._start_server(port)
        server_thread = threading.Thread(
            target=self._run_server, args=(server, 2.0), daemon=True)
        server_thread.start()
        time.sleep(0.2)

        try:
            client = MasterClient()
            client.connect('127.0.0.1', port, timeout=2.0)
            hosts = client.request_host_list('NonexistentGame')
            self.assertEqual(len(hosts), 0)
            client.disconnect()
        finally:
            server.stop()
            server_thread.join(timeout=2.0)

    def test_multiple_game_types(self):
        port = 24468
        server = self._start_server(port)
        server_thread = threading.Thread(
            target=self._run_server, args=(server, 4.0), daemon=True)
        server_thread.start()
        time.sleep(0.2)

        try:
            reg1 = MasterClient()
            reg1.connect('127.0.0.1', port, timeout=2.0)
            reg1.register_host('GameA', 'Server1', port=7001)

            time.sleep(0.1)

            reg2 = MasterClient()
            reg2.connect('127.0.0.1', port, timeout=2.0)
            reg2.register_host('GameB', 'Server2', port=7002)

            time.sleep(0.3)

            query = MasterClient()
            query.connect('127.0.0.1', port, timeout=2.0)

            hosts_a = query.request_host_list('GameA')
            self.assertEqual(len(hosts_a), 1)
            self.assertEqual(hosts_a[0]['game_name'], 'Server1')

            hosts_b = query.request_host_list('GameB')
            self.assertEqual(len(hosts_b), 1)
            self.assertEqual(hosts_b[0]['game_name'], 'Server2')

            query.disconnect()
            reg1.disconnect()
            reg2.disconnect()
        finally:
            server.stop()
            server_thread.join(timeout=2.0)

    def test_disconnect_removes_entry(self):
        port = 24469
        server = self._start_server(port)
        server_thread = threading.Thread(
            target=self._run_server, args=(server, 4.0), daemon=True)
        server_thread.start()
        time.sleep(0.2)

        try:
            reg = MasterClient()
            reg.connect('127.0.0.1', port, timeout=2.0)
            reg.register_host('TestGame', 'Server1', port=7001)
            time.sleep(0.3)

            # Verify it's there
            q1 = MasterClient()
            q1.connect('127.0.0.1', port, timeout=2.0)
            hosts = q1.request_host_list('TestGame')
            self.assertEqual(len(hosts), 1)
            q1.disconnect()

            # Disconnect the registrar
            reg.disconnect()
            time.sleep(0.5)

            # Query again — should be gone
            q2 = MasterClient()
            q2.connect('127.0.0.1', port, timeout=2.0)
            hosts = q2.request_host_list('TestGame')
            self.assertEqual(len(hosts), 0)
            q2.disconnect()
        finally:
            server.stop()
            server_thread.join(timeout=2.0)


class TestMasterServerPingTimeout(unittest.TestCase):
    """Test that stale entries are removed after ping timeout."""

    def test_stale_entry_removed(self):
        from protocol.master_server import Table, PING_TIMEOUT
        table = Table('test')
        table.add_column('Game name', STRING)

        addr_key = '127.0.0.1:7777'
        row_id = table.get_or_create_row_for_addr(addr_key)
        now = time.monotonic() * 1000
        table.update_row(row_id, {
            'Game name': 'Server1',
            '__lastPingResponseTime': now - (PING_TIMEOUT + 1) * 1000,
        })

        self.assertEqual(len(table.rows), 1)

        from protocol.master_server import MasterServer
        server = MasterServer.__new__(MasterServer)
        server._tables = {'test': table}
        server._peer_tables = {}
        server._last_ping_check = 0
        server._raknet = type('', (), {'peers': {}})()

        server._check_ping_timeouts()
        self.assertEqual(len(table.rows), 0)


class TestMasterServerFilters(unittest.TestCase):
    """Test filter operations on table queries."""

    def setUp(self):
        from protocol.master_server import Table
        self.table = Table('test')
        self.table.add_column('score', NUMERIC)
        for i, score in enumerate([10.0, 20.0, 30.0]):
            row_id = self.table.allocate_row()
            self.table.update_row(row_id, {'score': score})

    def test_greater_than(self):
        rows = self.table.query(filters=[
            {'name': 'score', 'operation': 2, 'value': 15.0}])
        scores = sorted(r['cells']['score'] for r in rows)
        self.assertEqual(scores, [20.0, 30.0])

    def test_less_than_eq(self):
        rows = self.table.query(filters=[
            {'name': 'score', 'operation': 5, 'value': 20.0}])
        scores = sorted(r['cells']['score'] for r in rows)
        self.assertEqual(scores, [10.0, 20.0])

    def test_equal(self):
        rows = self.table.query(filters=[
            {'name': 'score', 'operation': 0, 'value': 20.0}])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['cells']['score'], 20.0)

    def test_not_equal(self):
        rows = self.table.query(filters=[
            {'name': 'score', 'operation': 1, 'value': 20.0}])
        scores = sorted(r['cells']['score'] for r in rows)
        self.assertEqual(scores, [10.0, 30.0])


class TestMasterServerVersionMismatch(unittest.TestCase):
    """Test that version mismatch sends an error message."""

    def test_version_mismatch_sends_error(self):
        port = 24470
        server = MasterServer(port=port)
        server.start()
        server_thread = threading.Thread(
            target=lambda: self._run_server(server, 3.0), daemon=True)
        server_thread.start()
        time.sleep(0.2)

        try:
            from protocol.raknet_connection import RakNetClient
            client = RakNetClient(unity_protocol=False)
            client.connect('127.0.0.1', port, timeout=2.0)

            from protocol.master_serialization import encode_query_request
            from protocol.bitstream import BitStream as BS

            bs = BS()
            bs.write_u8(75)  # ID_DATABASE_QUERY_REQUEST
            bs.write_bytes(bytes([99, 99, 99]))  # wrong version
            from protocol.master_serialization import write_huffman_string
            write_huffman_string(bs, 'TestGame')
            bs.write_bool(False)  # no password
            bs.write_u8(0)  # no column subset
            bs.write_u8(0)  # no filters
            bs.write_u8(0)  # no row ids
            payload = bs.to_bytes()

            from protocol.raknet_transport import Reliability
            client.send_message(payload, Reliability.RELIABLE_ORDERED)

            deadline = time.monotonic() + 2.0
            got_error = False
            while time.monotonic() < deadline:
                msgs = client.poll(timeout=0.1)
                for msg_id, data, rel, bits in msgs:
                    if msg_id == 202:  # ID_MASTERSERVER_MSG
                        got_error = True
                        break
                if got_error:
                    break

            self.assertTrue(got_error, "Expected ID_MASTERSERVER_MSG on version mismatch")
            client.disconnect()
        finally:
            server.stop()
            server_thread.join(timeout=2.0)

    def _run_server(self, server, duration):
        deadline = time.monotonic() + duration
        while time.monotonic() < deadline:
            server.tick(timeout=0.01)
            time.sleep(0.005)


if __name__ == '__main__':
    unittest.main()
