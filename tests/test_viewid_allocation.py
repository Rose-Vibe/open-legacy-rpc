"""
Tests for ViewID allocation in UnityServer.
"""
import time
import threading

from protocol.unity_client import UnityClient
from protocol.unity_server import UnityServer
from protocol.unity_protocol import RPCMode


def _make_server_client(port, **kwargs):
    """Helper to set up a connected server-client pair."""
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


def test_viewid_base_per_player():
    """Each player gets a ViewID base of player_index * stride."""
    server, client, addr, player_idx, _ = _make_server_client(17790)
    try:
        assert player_idx == 1
        assert server.get_viewid_base(addr) == 50
    finally:
        client.disconnect()
        server.stop()


def test_allocate_sequential():
    """allocate_view_id returns sequential IDs from the player's range."""
    server, client, addr, _, _ = _make_server_client(17791)
    try:
        v1 = server.allocate_view_id(addr)
        v2 = server.allocate_view_id(addr)
        v3 = server.allocate_view_id(addr)
        assert v1 == 50
        assert v2 == 51
        assert v3 == 52
    finally:
        client.disconnect()
        server.stop()


def test_allocate_with_group():
    """allocate_view_id can assign a group at allocation time."""
    server, client, addr, _, _ = _make_server_client(17792)
    try:
        v1 = server.allocate_view_id(addr, group=1)
        v2 = server.allocate_view_id(addr, group=2)
        assert server._view_groups[v1] == 1
        assert server._view_groups[v2] == 2
    finally:
        client.disconnect()
        server.stop()


def test_get_allocated_views():
    """get_allocated_views returns all ViewIDs for a client."""
    server, client, addr, _, _ = _make_server_client(17793)
    try:
        server.allocate_view_id(addr)
        server.allocate_view_id(addr)
        views = server.get_allocated_views(addr)
        assert views == [50, 51]
    finally:
        client.disconnect()
        server.stop()


def test_cleanup_on_disconnect():
    """Allocated ViewIDs and groups are freed on disconnect."""
    server, client, addr, _, _ = _make_server_client(17794)
    try:
        v1 = server.allocate_view_id(addr, group=1)
        v2 = server.allocate_view_id(addr, group=2)
        assert v1 in server._view_groups
        assert v2 in server._view_groups

        client.disconnect()
        time.sleep(0.5)

        assert addr not in server._allocated_views
        assert addr not in server._view_counters
        assert v1 not in server._view_groups
        assert v2 not in server._view_groups
    finally:
        server.stop()


def test_custom_stride():
    """Custom viewid_stride changes the allocation range size."""
    server, client, addr, player_idx, _ = _make_server_client(17795, viewid_stride=100)
    try:
        assert server.get_viewid_base(addr) == 100
        v1 = server.allocate_view_id(addr)
        assert v1 == 100
    finally:
        client.disconnect()
        server.stop()


def test_allocate_unknown_client():
    """allocate_view_id raises for unknown client."""
    server = UnityServer(port=17796)
    try:
        server.allocate_view_id(('1.2.3.4', 9999))
        assert False, "Should have raised"
    except ValueError:
        pass


def test_viewid_block_allocation():
    """allocate_view_id uses block-based ranges matching Unity's scheme."""
    server = UnityServer(port=17798, viewid_stride=50)
    server.start()

    connected = []
    server.on_connect(lambda addr, idx: connected.append((addr, idx)))
    server.on_disconnect(lambda addr, idx: None)

    server_thread = threading.Thread(target=server.run, args=(5.0,), daemon=True)
    server_thread.start()
    time.sleep(0.1)

    client = UnityClient()
    try:
        client.connect('127.0.0.1', 17798, timeout=3.0)
        time.sleep(0.3)

        addr = connected[0][0]
        # Player 1's block_start = 1*3-2 = 1, so allocation starts at 1*50 = 50
        v1 = server.allocate_view_id(addr)
        v2 = server.allocate_view_id(addr)
        v3 = server.allocate_view_id(addr)
        assert v1 == 50
        assert v2 == 51
        assert v3 == 52
    finally:
        client.disconnect()
        server.stop()


def test_client_receives_correct_base():
    """Unity client receives the correct ViewID base in player assignment."""
    server, client, addr, player_idx, _ = _make_server_client(17797)
    try:
        assert client.player_index == 1
        assert client.viewid_base == 50
    finally:
        client.disconnect()
        server.stop()


def test_client_allocate_view_id():
    """Python client allocates ViewIDs from its assigned range."""
    server, client, addr, _, _ = _make_server_client(17799)
    try:
        v1 = client.allocate_view_id()
        v2 = client.allocate_view_id()
        v3 = client.allocate_view_id()
        assert v1 == 50
        assert v2 == 51
        assert v3 == 52
    finally:
        client.disconnect()
        server.stop()


def test_client_allocate_before_connected():
    """allocate_view_id before connection returns 0 (unassigned)."""
    client = UnityClient()
    assert client.allocate_view_id() == 0


def test_server_viewid_allocation_overflow():
    """Server raises ValueError when ViewID allocation exceeds stride."""
    import pytest
    server, client, addr, _, _ = _make_server_client(17801, viewid_stride=3)
    try:
        server.allocate_view_id(addr)
        server.allocate_view_id(addr)
        server.allocate_view_id(addr)
        with pytest.raises(ValueError, match="overflow"):
            server.allocate_view_id(addr)
    finally:
        client.disconnect()
        server.stop()
