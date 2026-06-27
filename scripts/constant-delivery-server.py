#!/usr/bin/env python3
"""
Python server for ConstantDeliveryExperiment.

Sends RPCs with various user_rpc_constant values to test whether
the constant affects RPC delivery to Unity clients.

Usage:
    python3 scripts/constant-delivery-server.py [--port 7777]
"""
import sys
import os
import time
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from protocol.unity_server import UnityServer
from protocol.unity_protocol import RPCMode


def poll_server(srv, count=1, interval=0.05):
    for _ in range(count):
        srv.poll(0.01)
        # Check retransmits for reliable delivery
        for peer in list(srv._raknet.peers.values()):
            peer.check_retransmits()
        time.sleep(interval)

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s %(message)s')
log = logging.getLogger('constant-delivery')

CONSTANT_TESTS = [
    # (label, constant_value, rpc_param_value)
    # First: send with correct constant to verify delivery works at all
    ("correct (0x0002 = SceneID:1)", 0x0002, 100),
    ("correct again (0x0002)", 0x0002, 101),
    # Then test wrong constants
    ("wrong scene (0x0004 = SceneID:2)", 0x0004, 200),
    ("wrong scene (0x0010 = SceneID:8)", 0x0010, 300),
    ("allocated (0x2640 = AllocID:50)", 0x2640, 400),
    ("zero (0x0000 = internal)", 0x0000, 500),
    ("max (0xFFFF)", 0xFFFF, 600),
    ("default (0x2000 = AllocID:0)", 0x2000, 700),
    ("random (0x1234)", 0x1234, 800),
    # Finally: send correct again to prove delivery still works
    ("correct final (0x0002)", 0x0002, 900),
]

server = UnityServer(port=7777)
client_ready = False
client_addr = None
tests_sent = False


def on_connect(addr, player_idx):
    global client_addr
    client_addr = addr
    log.info(f"Client connected: {addr} (player {player_idx})")
    # Clear pre-registered methods so first RPC sends first-use encoding
    # (Unity client needs the method hash to register the method index)
    server._rpc_sent_methods[addr] = set()


def on_rpc_int(addr, value):
    global client_ready
    if value == -1:
        log.info("Client is ready (received ping)")
        client_ready = True
    else:
        log.info(f"Received RPC_Int({value}) from client")


server.on_connect(on_connect)
server.on_rpc('RPC_Int', on_rpc_int)
server.start()

log.info("Server started on port 7777, waiting for client...")

try:
    while not client_ready:
        poll_server(server)

    # Brief delay to ensure client is fully ready
    poll_server(server, 20)

    log.info("Sending RPCs with different constant values...")
    for label, const, param in CONSTANT_TESTS:
        log.info(f"  Sending RPC_Int({param}) with constant=0x{const:04x} ({label})")
        # Force first-use encoding for every RPC so we don't depend on
        # subsequent-use method_index (which we haven't fully decoded yet)
        server._rpc_sent_methods[client_addr] = set()
        server.send_rpc('RPC_Int', [param], target=client_addr,
                        mode=RPCMode.Server, view_id=0,
                        user_rpc_constant=const)
        poll_server(server, 10)

    log.info(f"All {len(CONSTANT_TESTS)} RPCs sent. Waiting for client to finish...")

    deadline = time.time() + 15
    while time.time() < deadline:
        poll_server(server)

    log.info("Server done.")

except KeyboardInterrupt:
    pass
finally:
    server.stop()
