"""
Tests for ReliableDeltaCompressed state sync encoding/decoding and server integration.
"""
import struct
import time
import threading

from protocol.unity_protocol import (
    encode_delta_state_sync, decode_delta_state_sync,
)
from protocol.unity_server import UnityServer
from protocol.unity_client import UnityClient
from protocol.raknet_transport import Reliability


# ── Unit tests: encode / decode round-trip ──


def test_encode_all_dirty():
    """First message with all fields changed from zero defaults."""
    values = [42, 100, 0]
    prev = [0, 0, 0]
    widths = [32, 32, 32]
    payload, bits = encode_delta_state_sync(0, 0x1234, values, prev, widths, is_first=True)

    assert payload[0] == 0x1b
    assert payload[9] == 0x80  # is_first flag

    result = decode_delta_state_sync(payload, bits, 3, widths, [0, 0, 0])
    assert result['dirty_flags'] == [1, 1, 0]
    assert result['field_values'] == [42, 100, 0]
    assert result['is_first'] is True


def test_encode_no_dirty():
    """No fields changed — only 3 dirty bits in data section."""
    values = [10, 20, 30]
    prev = [10, 20, 30]
    widths = [32, 32, 32]
    payload, bits = encode_delta_state_sync(0, 0, values, prev, widths)

    assert bits == 96 + 3  # header + 3 dirty bits, no field data
    result = decode_delta_state_sync(payload, bits, 3, widths, [10, 20, 30])
    assert result['dirty_flags'] == [0, 0, 0]
    assert result['field_values'] == [10, 20, 30]


def test_encode_partial_dirty():
    """Only middle field changed."""
    prev = [42, 0, 100]
    values = [42, 999, 100]
    widths = [32, 32, 32]
    payload, bits = encode_delta_state_sync(0, 0, values, prev, widths)

    assert bits == 96 + 3 + 32  # header + 3 dirty bits + 1 field
    result = decode_delta_state_sync(payload, bits, 3, widths, list(prev))
    assert result['dirty_flags'] == [0, 1, 0]
    assert result['field_values'] == [42, 999, 100]


def test_encode_float_field():
    """Float fields encode correctly via IEEE 754."""
    prev = [0, 0, 0]
    values = [0, 0, struct.unpack('>I', struct.pack('>f', 3.14))[0]]
    widths = [32, 32, 32]
    payload, bits = encode_delta_state_sync(0, 0, values, prev, widths)

    result = decode_delta_state_sync(payload, bits, 3, widths, [0, 0, 0])
    float_back = struct.unpack('>f', struct.pack('>I', result['field_values'][2]))[0]
    assert abs(float_back - 3.14) < 0.001


def test_encode_float_via_float_type():
    """encode_delta_state_sync handles Python float values directly."""
    prev = [0, 0, 0.0]
    values = [0, 0, 3.14]
    widths = [32, 32, 32]
    payload, bits = encode_delta_state_sync(0, 0, values, prev, widths)

    result = decode_delta_state_sync(payload, bits, 3, widths, [0, 0, 0])
    float_back = struct.unpack('>f', struct.pack('>I', result['field_values'][2]))[0]
    assert abs(float_back - 3.14) < 0.001


def test_roundtrip_sequence():
    """Simulate the 6-message experiment sequence."""
    widths = [32, 32, 32]
    states = [
        [0, 0, 0],
        [42, 0, 0],
        [42, 100, 0],
        [42, 100, struct.unpack('>I', struct.pack('>f', 3.14))[0]],
        [999, 0, struct.unpack('>I', struct.pack('>f', 3.14))[0]],
        [0, 0, 0],
    ]

    prev = [0, 0, 0]
    for i, cur in enumerate(states):
        payload, bits = encode_delta_state_sync(
            0, i, cur, prev, widths, is_first=(i == 0))
        result = decode_delta_state_sync(payload, bits, 3, widths, list(prev))
        assert result['field_values'] == cur, f"Mismatch at step {i}"
        prev = list(cur)


def test_view_id_preserved():
    """ViewID survives encode/decode."""
    payload, bits = encode_delta_state_sync(
        12345, 0, [1], [0], [32])
    result = decode_delta_state_sync(payload, bits, 1, [32], [0])
    assert result['view_id'] == 12345


def test_timestamp_preserved():
    """Timestamp survives encode/decode."""
    payload, bits = encode_delta_state_sync(
        0, 0xABCD, [1], [0], [32])
    result = decode_delta_state_sync(payload, bits, 1, [32], [0])
    assert result['timestamp'] == 0xABCD


def test_single_field():
    """Works with a single field."""
    payload, bits = encode_delta_state_sync(0, 0, [77], [0], [32])
    assert bits == 96 + 1 + 32
    result = decode_delta_state_sync(payload, bits, 1, [32], [0])
    assert result['field_values'] == [77]


def test_negative_int():
    """Negative integers encode as two's complement and survive round-trip."""
    payload, bits = encode_delta_state_sync(0, 0, [-1, -42], [0, 0], [32, 32])
    result = decode_delta_state_sync(payload, bits, 2, [32, 32], [0, 0])
    assert result['field_values'][0] == 0xFFFFFFFF
    assert result['field_values'][1] == 0xFFFFFFD6  # -42 as unsigned


def test_many_fields():
    """Works with many fields."""
    n = 10
    widths = [32] * n
    prev = list(range(n))
    cur = list(range(1, n + 1))
    payload, bits = encode_delta_state_sync(0, 0, cur, prev, widths)
    assert bits == 96 + n + n * 32  # all dirty
    result = decode_delta_state_sync(payload, bits, n, widths, list(prev))
    assert result['field_values'] == cur


# ── Integration: server sends delta sync to client ──


def _make_server_client(port, **kwargs):
    server = UnityServer(port=port, **kwargs)
    server.start()

    connected = []
    server.on_connect(lambda addr, idx: connected.append((addr, idx)))
    server.on_disconnect(lambda addr, idx: None)

    server_thread = threading.Thread(target=server.run, args=(5.0,), daemon=True)
    server_thread.start()
    time.sleep(0.1)

    client = UnityClient()
    client.connect('127.0.0.1', port, timeout=3.0)
    time.sleep(0.3)

    assert connected, "Client did not connect"
    addr, player_idx = connected[0]
    return server, client, addr, player_idx, server_thread


def test_server_delta_tracks_state():
    """Server tracks per-client state for delta compression."""
    server, client, addr, _, _ = _make_server_client(17850)
    try:
        widths = [32, 32]
        server.send_delta_state_sync(0, [10, 20], widths)
        key = (addr, 0)
        assert server._delta_state[key] == [10, 20]

        server.send_delta_state_sync(0, [10, 30], widths)
        assert server._delta_state[key] == [10, 30]
    finally:
        client.disconnect()
        server.stop()


def test_server_delta_cleanup_on_disconnect():
    """Delta state is cleaned up when client disconnects."""
    server, client, addr, _, _ = _make_server_client(17851)
    try:
        server.send_delta_state_sync(0, [1, 2], [32, 32])
        assert len(server._delta_state) == 1

        client.disconnect()
        time.sleep(0.5)
        assert len(server._delta_state) == 0
    finally:
        server.stop()


def test_server_delta_respects_groups():
    """Delta sync respects group send filtering."""
    server, client, addr, _, _ = _make_server_client(17852)
    try:
        server.set_view_group(5, 1)
        server.set_sending_enabled(addr, 1, False)

        server.send_delta_state_sync(5, [42], [32])
        assert (addr, 5) not in server._delta_state
    finally:
        client.disconnect()
        server.stop()
