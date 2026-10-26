"""
End-to-end confirmation that per-peer learned dispatch indices (populated
from decode_batch_index) work correctly across two connections that each
assign their OWN local index for the same method, in a different order.

This models the "genuinely different assemblies" scenario from CLAUDE.md's
method-index testing convention without needing two real Unity builds:
_our_indices (client-side) and _peer_indices (server-side) are dynamically
assigned in the order first-use RPCs are exchanged on each connection, which
is exactly analogous to two compiled assemblies having diverged, per-build
MethodDef-ordering-derived static index tables. If the server naively
assumed a single shared index per method (instead of a real per-peer
lookup), or if decode_batch_index mis-decoded the peer's self-reported
index (see docs/research/2026-07-13-batch-index-decoder-was-broken.md),
this test would show one client's RPC misdispatching to the wrong method.
"""
import threading
import time

from protocol.unity_client import UnityClient
from protocol.unity_server import UnityServer


def _make_server_client(port):
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


def test_subsequent_use_dispatches_correctly_with_divergent_peer_indices():
    """Two clients learn different local indices for the same two methods
    (in opposite first-use order), and both must still dispatch correctly
    once the server switches to subsequent-use encoding for each."""
    server_a, client_a, addr_a, _ = _make_server_client(17790)
    server_b, client_b, addr_b, _ = _make_server_client(17791)
    # Two independent servers so each client only ever learns from its own
    # connection's first-use order — a single shared server would assign a
    # process-wide _our_indices the first time either method is seen.
    try:
        received_a = []
        received_b = []
        client_a.on_rpc('RPC_Int', lambda val: received_a.append(('RPC_Int', val)))
        client_a.on_rpc('RPC_Float', lambda val: received_a.append(('RPC_Float', val)))
        client_b.on_rpc('RPC_Int', lambda val: received_b.append(('RPC_Int', val)))
        client_b.on_rpc('RPC_Float', lambda val: received_b.append(('RPC_Float', val)))

        def pump(deadline_s, *servers_and_clients):
            deadline = time.monotonic() + deadline_s
            while time.monotonic() < deadline:
                for sc in servers_and_clients:
                    sc.poll(0.02)

        # Client A: server first-uses RPC_Int then RPC_Float -> client A's
        # local table: RPC_Int=4, RPC_Float=8.
        server_a.send_rpc('RPC_Int', [1], target=addr_a, view_id=0, target_view=0x2000)
        pump(0.3, server_a, client_a)
        server_a.send_rpc('RPC_Float', [1.0], target=addr_a, view_id=0, target_view=0x2000)
        pump(0.3, server_a, client_a)

        # Client B: server first-uses RPC_Float then RPC_Int -> client B's
        # local table: RPC_Float=4, RPC_Int=8 (opposite of client A).
        server_b.send_rpc('RPC_Float', [2.0], target=addr_b, view_id=0, target_view=0x2000)
        pump(0.3, server_b, client_b)
        server_b.send_rpc('RPC_Int', [2], target=addr_b, view_id=0, target_view=0x2000)
        pump(0.3, server_b, client_b)

        received_a.clear()
        received_b.clear()

        # Confirm the two peers really did learn opposite index assignments.
        assert server_a._peer_indices[addr_a]['RPC_Int'] == 4
        assert server_a._peer_indices[addr_a]['RPC_Float'] == 8
        assert server_b._peer_indices[addr_b]['RPC_Float'] == 4
        assert server_b._peer_indices[addr_b]['RPC_Int'] == 8

        # Now send subsequent-use RPC_Int to both; each server must use its
        # own peer's learned index (4 for A, 8 for B) — different bytes on
        # the wire, but both clients must still dispatch to RPC_Int.
        server_a.send_rpc('RPC_Int', [42], target=addr_a, view_id=0, target_view=0x2000)
        server_b.send_rpc('RPC_Int', [99], target=addr_b, view_id=0, target_view=0x2000)
        pump(0.5, server_a, client_a, server_b, client_b)

        assert ('RPC_Int', 42) in received_a, \
            f"Client A should dispatch subsequent-use RPC_Int correctly: {received_a}"
        assert ('RPC_Int', 99) in received_b, \
            f"Client B should dispatch subsequent-use RPC_Int correctly: {received_b}"
        assert ('RPC_Float', 42) not in received_a and ('RPC_Void', 42) not in received_a, \
            f"Client A must not misdispatch RPC_Int to another method: {received_a}"
        assert ('RPC_Float', 99) not in received_b and ('RPC_Void', 99) not in received_b, \
            f"Client B must not misdispatch RPC_Int to another method: {received_b}"
    finally:
        client_a.disconnect()
        client_b.disconnect()
        server_a.stop()
        server_b.stop()
