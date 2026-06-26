"""
Unit tests for network group filtering in UnityServer.
Groups are purely server-side — no wire protocol involved.
"""
import time
import threading

from protocol.unity_client import UnityClient
from protocol.unity_server import UnityServer
from protocol.unity_protocol import RPCMode
from protocol.bitstream import BitStream


def _make_server_client(port):
    """Helper to set up a connected server-client pair."""
    server = UnityServer(port=port)
    server.start()

    connected = []
    server.on_connect(lambda addr, idx: connected.append(addr))
    server.on_disconnect(lambda addr, idx: None)

    server_thread = threading.Thread(target=server.run, args=(5.0,), daemon=True)
    server_thread.start()
    time.sleep(0.1)

    client = UnityClient()
    client.connect('127.0.0.1', port, timeout=3.0)
    time.sleep(0.3)

    assert connected, "Client did not connect"
    addr = connected[0]
    return server, client, addr, server_thread


def test_view_group_assignment():
    """set_view_group assigns views to groups."""
    server = UnityServer(port=17780)
    server.set_view_group(0, 0)
    server.set_view_group(1, 1)
    server.set_view_group(2, 2)
    assert server._view_groups == {0: 0, 1: 1, 2: 2}


def test_send_enabled_default():
    """By default, all groups are enabled for sending."""
    server = UnityServer(port=17781)
    assert server._is_send_enabled(('127.0.0.1', 1234), 0)
    assert server._is_send_enabled(('127.0.0.1', 1234), 1)


def test_send_disable_enable():
    """set_sending_enabled toggles group send filtering."""
    server = UnityServer(port=17782)
    addr = ('127.0.0.1', 1234)
    server.set_view_group(1, 1)

    server.set_sending_enabled(addr, 1, False)
    assert not server._is_send_enabled(addr, 1)
    assert server._is_send_enabled(addr, 0)

    server.set_sending_enabled(addr, 1, True)
    assert server._is_send_enabled(addr, 1)


def test_recv_disable_enable():
    """set_receiving_enabled toggles group receive filtering."""
    server = UnityServer(port=17783)
    addr = ('127.0.0.1', 1234)
    server.set_view_group(1, 1)

    server.set_receiving_enabled(addr, 1, False)
    assert not server._is_recv_enabled(addr, 1)
    assert server._is_recv_enabled(addr, 0)

    server.set_receiving_enabled(addr, 1, True)
    assert server._is_recv_enabled(addr, 1)


def test_send_rpc_filtered_by_group():
    """RPCs to a disabled group are not sent."""
    server, client, addr, _ = _make_server_client(17784)
    try:
        received = []
        client.on_rpc('RPC_Int', lambda val: received.append(val))

        server.set_view_group(0, 0)
        server.set_view_group(1, 1)

        server.set_sending_enabled(addr, 1, False)

        server.send_rpc('RPC_Int', [42], target=addr, view_id=0)
        server.send_rpc('RPC_Int', [99], target=addr, view_id=1)

        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            client.poll(0.05)

        assert 42 in received, f"Group 0 RPC should be received: {received}"
        assert 99 not in received, f"Group 1 RPC should be filtered: {received}"
    finally:
        client.disconnect()
        server.stop()


def test_state_sync_filtered_by_group():
    """State sync to a disabled group is not sent."""
    server, client, addr, _ = _make_server_client(17785)
    try:
        sync_values = []
        def on_sync(result):
            sync_values.append(result['data_stream'].read_i32_be())

        client.on_state_sync(0, on_sync)
        client.on_state_sync(1, on_sync)

        server.set_view_group(0, 0)
        server.set_view_group(1, 1)

        server.set_sending_enabled(addr, 1, False)

        bs0 = BitStream()
        bs0.write_i32_be(42)
        server.send_state_sync(0, bs0, target=addr)

        bs1 = BitStream()
        bs1.write_i32_be(99)
        server.send_state_sync(1, bs1, target=addr)

        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            client.poll(0.05)

        assert 42 in sync_values, f"Group 0 sync should be received: {sync_values}"
        assert 99 not in sync_values, f"Group 1 sync should be filtered: {sync_values}"
    finally:
        client.disconnect()
        server.stop()


def test_recv_rpc_filtered_by_group():
    """Incoming RPCs from a disabled receive group are dropped."""
    server, client, addr, _ = _make_server_client(17787)
    try:
        received = []
        server.on_rpc('RPC_Int', lambda a, val: received.append(val))

        server.set_view_group(0, 0)
        server.set_view_group(1, 1)

        server.set_receiving_enabled(addr, 1, False)

        client.send_rpc('RPC_Int', [42], view_id=0)
        client.send_rpc('RPC_Int', [99], view_id=1)

        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            server.poll(0.05)
            client.poll(0.01)

        assert 42 in received, f"Group 0 RPC should be received: {received}"
        assert 99 not in received, f"Group 1 RPC should be filtered: {received}"
    finally:
        client.disconnect()
        server.stop()


def test_broadcast_rpc_filtered_by_group():
    """Broadcast RPCs respect per-client group filtering."""
    server, client, addr, _ = _make_server_client(17788)
    try:
        received = []
        client.on_rpc('RPC_Int', lambda val: received.append(val))

        server.set_view_group(0, 0)
        server.set_view_group(1, 1)
        server.set_sending_enabled(addr, 1, False)

        server.send_rpc('RPC_Int', [42], view_id=0)
        server.send_rpc('RPC_Int', [99], view_id=1)

        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            client.poll(0.05)

        assert 42 in received, f"Group 0 RPC should be received: {received}"
        assert 99 not in received, f"Group 1 RPC should be filtered: {received}"
    finally:
        client.disconnect()
        server.stop()


def test_cleanup_on_disconnect():
    """Group state is cleaned up when a client disconnects."""
    server, client, addr, _ = _make_server_client(17786)
    try:
        server.set_sending_enabled(addr, 1, False)
        server.set_receiving_enabled(addr, 2, False)
        assert addr in server._send_groups
        assert addr in server._recv_groups

        client.disconnect()
        time.sleep(0.5)

        assert addr not in server._send_groups
        assert addr not in server._recv_groups
    finally:
        server.stop()
