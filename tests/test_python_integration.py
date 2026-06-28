"""
Integration test: Python client <-> Python server.
Validates the full protocol stack (RakNet + Unity layer) without Unity.
"""
import time
import threading

from protocol.unity_client import UnityClient
from protocol.unity_server import UnityServer
from protocol.unity_protocol import RPCMode
from protocol.bitstream import BitStream


def test_connect_disconnect():
    """Client connects to server, both see each other, client disconnects."""
    server = UnityServer(port=17771)
    server.start()

    connected = []
    disconnected = []
    server.on_connect(lambda addr, idx: connected.append((addr, idx)))
    server.on_disconnect(lambda addr, idx: disconnected.append((addr, idx)))

    # Run server in background
    server_thread = threading.Thread(target=server.run, args=(3.0,), daemon=True)
    server_thread.start()
    time.sleep(0.1)

    client = UnityClient()
    try:
        client.connect('127.0.0.1', 17771, timeout=2.0)
        assert client.connected
        assert client.player_index == 1

        time.sleep(0.2)
        assert len(connected) == 1
        assert connected[0][1] == 1  # player index

        client.disconnect()
        time.sleep(0.3)
    finally:
        server.stop()
        server_thread.join(timeout=2.0)


def test_rpc_client_to_server():
    """Client sends RPCs to server, server receives correct values."""
    server = UnityServer(port=17772)
    server.start()
    received = []

    server.on_connect(lambda addr, idx: None)
    server.on_disconnect(lambda addr, idx: None)
    server.on_rpc('RPC_Int', lambda addr, val: received.append(('int', val)))
    server.on_rpc('RPC_Float', lambda addr, val: received.append(('float', val)))
    server.on_rpc('RPC_String', lambda addr, val: received.append(('string', val)))

    server_thread = threading.Thread(target=server.run, args=(3.0,), daemon=True)
    server_thread.start()

    client = UnityClient()
    try:
        client.connect('127.0.0.1', 17772, timeout=2.0)
        assert client.connected

        client.send_rpc('RPC_Int', [42], target_view=0x2000)
        client.send_rpc('RPC_Float', [3.14], target_view=0x2000)
        client.send_rpc('RPC_String', ['hello'], target_view=0x2000)

        # Poll to ensure messages are sent
        for _ in range(20):
            client.poll(0.05)

        time.sleep(0.5)
        assert len(received) >= 3, f"Only received {len(received)} RPCs"
        assert received[0] == ('int', 42)
        assert received[1][0] == 'float'
        assert abs(received[1][1] - 3.14) < 1e-5
        assert received[2] == ('string', 'hello')

        client.disconnect()
    finally:
        server.stop()
        server_thread.join(timeout=2.0)


def test_rpc_server_to_client():
    """Server sends RPCs to client, client receives correct values."""
    server = UnityServer(port=17773)
    server.start()
    received = []
    client_addr = [None]

    server.on_connect(lambda addr, idx: client_addr.__setitem__(0, addr))
    server.on_disconnect(lambda addr, idx: None)

    server_thread = threading.Thread(target=server.run, args=(3.0,), daemon=True)
    server_thread.start()

    client = UnityClient()
    client.on_rpc('RPC_Int', lambda val: received.append(('int', val)))

    try:
        client.connect('127.0.0.1', 17773, timeout=2.0)
        assert client.connected

        # Wait for server to register the connection
        time.sleep(0.3)
        assert client_addr[0] is not None

        # Server sends RPC to client
        server.send_rpc('RPC_Int', [99], target=client_addr[0], target_view=0x2000)

        # Client polls to receive
        for _ in range(20):
            client.poll(0.05)

        assert len(received) >= 1, f"Client received {len(received)} RPCs"
        assert received[0] == ('int', 99)

        client.disconnect()
    finally:
        server.stop()
        server_thread.join(timeout=2.0)


def test_state_sync_server_to_client():
    """Server sends state sync, client decodes it correctly."""
    server = UnityServer(port=17774)
    server.start()
    received_values = []
    client_addr = [None]

    server.on_connect(lambda addr, idx: client_addr.__setitem__(0, addr))
    server.on_disconnect(lambda addr, idx: None)

    server_thread = threading.Thread(target=server.run, args=(3.0,), daemon=True)
    server_thread.start()

    def handle_sync(result):
        val = result['data_stream'].read_i32_be()
        received_values.append(val)

    client = UnityClient()
    client.on_state_sync(1, handle_sync)

    try:
        client.connect('127.0.0.1', 17774, timeout=2.0)
        time.sleep(0.3)

        # Server sends state sync
        data = BitStream()
        data.write_i32_be(42)
        server.send_state_sync(1, data, target=client_addr[0])

        for _ in range(20):
            client.poll(0.05)

        assert len(received_values) >= 1, f"Received {len(received_values)} syncs"
        assert received_values[0] == 42

        client.disconnect()
    finally:
        server.stop()
        server_thread.join(timeout=2.0)


def test_multi_param_rpc():
    """Test multi-parameter RPC (int + float + string)."""
    server = UnityServer(port=17775)
    server.start()
    received = []

    server.on_connect(lambda addr, idx: None)
    server.on_disconnect(lambda addr, idx: None)
    server.on_rpc('RPC_IntFloatString',
                  lambda addr, i, f, s: received.append((i, f, s)))

    server_thread = threading.Thread(target=server.run, args=(3.0,), daemon=True)
    server_thread.start()

    client = UnityClient()
    try:
        client.connect('127.0.0.1', 17775, timeout=2.0)
        client.send_rpc('RPC_IntFloatString', [42, 3.14, 'hello'], target_view=0x2000)

        for _ in range(20):
            client.poll(0.05)

        time.sleep(0.5)
        assert len(received) >= 1
        assert received[0][0] == 42
        assert abs(received[0][1] - 3.14) < 1e-5
        assert received[0][2] == 'hello'

        client.disconnect()
    finally:
        server.stop()
        server_thread.join(timeout=2.0)


def test_disconnect_cleanup():
    """Server cleans up per-client state on disconnect, no resource leaks."""
    server = UnityServer(port=17779)
    server.start()

    connected = []
    disconnected = []
    server.on_connect(lambda addr, idx: connected.append((addr, idx)))
    server.on_disconnect(lambda addr, idx: disconnected.append((addr, idx)))

    server_thread = threading.Thread(target=server.run, args=(5.0,), daemon=True)
    server_thread.start()
    time.sleep(0.1)

    try:
        # Connect first client, allocate views, disconnect
        c1 = UnityClient()
        c1.connect('127.0.0.1', 17779, timeout=2.0)
        assert c1.connected
        addr1 = connected[0][0]
        v1 = server.allocate_view_id(addr1)
        v2 = server.allocate_view_id(addr1)
        assert len(server.get_allocated_views(addr1)) == 2
        c1.disconnect()
        time.sleep(0.3)

        assert len(disconnected) == 1
        assert server.get_allocated_views(addr1) == []
        assert addr1 not in server._peer_indices

        # Connect second client — should get fresh state
        c2 = UnityClient()
        c2.connect('127.0.0.1', 17779, timeout=2.0)
        assert c2.connected
        addr2 = connected[1][0]
        v3 = server.allocate_view_id(addr2)
        assert v3 == server.get_viewid_base(addr2)
        c2.disconnect()
        time.sleep(0.3)

        assert len(disconnected) == 2
        assert len(server._delta_state) == 0
    finally:
        server.stop()
        server_thread.join(timeout=2.0)


def test_password_correct():
    """Client with correct password connects successfully."""
    server = UnityServer(port=17776, password='secret123')
    server.start()

    connected = []
    server.on_connect(lambda addr, idx: connected.append(idx))
    server.on_disconnect(lambda addr, idx: None)

    server_thread = threading.Thread(target=server.run, args=(3.0,), daemon=True)
    server_thread.start()
    time.sleep(0.1)

    client = UnityClient()
    try:
        client.connect('127.0.0.1', 17776, timeout=3.0, password='secret123')
        assert client.connected
        assert len(connected) == 1
        client.disconnect()
    finally:
        server.stop()
        server_thread.join(timeout=2.0)


def test_password_wrong():
    """Client with wrong password is rejected."""
    server = UnityServer(port=17777, password='secret123')
    server.start()

    connected = []
    server.on_connect(lambda addr, idx: connected.append(idx))
    server.on_disconnect(lambda addr, idx: None)

    server_thread = threading.Thread(target=server.run, args=(3.0,), daemon=True)
    server_thread.start()
    time.sleep(0.1)

    client = UnityClient()
    try:
        client.connect('127.0.0.1', 17777, timeout=2.0, password='wrongpass')
        assert False, "Should have timed out"
    except TimeoutError:
        pass
    assert len(connected) == 0
    server.stop()
    server_thread.join(timeout=2.0)


def test_password_missing():
    """Client without password is rejected when server requires one."""
    server = UnityServer(port=17778, password='secret123')
    server.start()

    connected = []
    server.on_connect(lambda addr, idx: connected.append(idx))
    server.on_disconnect(lambda addr, idx: None)

    server_thread = threading.Thread(target=server.run, args=(3.0,), daemon=True)
    server_thread.start()
    time.sleep(0.1)

    client = UnityClient()
    try:
        client.connect('127.0.0.1', 17778, timeout=2.0, password='')
        assert False, "Should have timed out"
    except TimeoutError:
        pass
    assert len(connected) == 0
    server.stop()
    server_thread.join(timeout=2.0)


if __name__ == '__main__':
    import traceback
    tests = [v for k, v in sorted(globals().items()) if k.startswith('test_')]
    passed = failed = 0
    for t in tests:
        print(f'Running {t.__name__}...')
        try:
            t()
            passed += 1
            print(f'  PASS  {t.__name__}')
        except Exception as e:
            failed += 1
            print(f'  FAIL  {t.__name__}: {e}')
            traceback.print_exc()
    print(f'\n{passed} passed, {failed} failed')
    sys.exit(1 if failed else 0)
