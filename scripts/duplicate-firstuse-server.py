#!/usr/bin/env python3
"""
Python server for DuplicateFirstUseExperiment.

Tests whether Unity drops duplicate first-use RPCs for the same method.
Sends RPC_Int multiple times, alternating between first-use and subsequent-use
encoding to see which ones the client accepts.

Test cases:
  1. First-use  RPC_Int(100)  — should work (first time)
  2. First-use  RPC_Int(200)  — duplicate first-use, does Unity drop it?
  3. First-use  RPC_Int(300)  — third first-use
  4. Subsequent RPC_Int(400)  — after 3 first-uses, does subsequent still work?
  5. First-use  RPC_Int(500)  — first-use after a subsequent
  6. Subsequent RPC_Int(600)  — subsequent after the mixed sequence
"""
import sys
import os
import time
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from protocol.unity_server import UnityServer
from protocol.unity_protocol import (
    RPCMode, encode_rpc_first_use, encode_rpc_subsequent,
    INTERNAL_RPC_CONSTANT,
)
from protocol.raknet_transport import Reliability


def poll_server(srv, count=1, interval=0.05):
    for _ in range(count):
        srv.poll(0.01)
        for peer in list(srv._raknet.peers.values()):
            peer.check_retransmits()
        time.sleep(interval)


logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s %(message)s')
log = logging.getLogger('duplicate-firstuse')

server = UnityServer(port=7777)
client_ready = False
client_addr = None
rpc_counter = 0


def on_connect(addr, player_idx):
    global client_addr
    client_addr = addr
    log.info(f"Client connected: {addr} (player {player_idx})")


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


def send_rpc_raw(method_name, params, first_use, label):
    """Send an RPC with explicit control over first-use vs subsequent-use."""
    global rpc_counter
    if first_use:
        payload, bits = encode_rpc_first_use(
            method_name, params, view_id=0, rpc_counter=rpc_counter,
            mode=RPCMode.Server, target_view=0x0002)
    else:
        payload, bits = encode_rpc_subsequent(
            method_name, params, view_id=0, rpc_counter=rpc_counter,
            mode=RPCMode.Server, target_view=0x0002)
    log.info(f"  [{label}] Sending {method_name}({params[0]}) counter={rpc_counter} "
             f"{'first-use' if first_use else 'subsequent'} ({bits} bits)")
    server._raknet.send_to(client_addr, payload, Reliability.RELIABLE_ORDERED)
    rpc_counter += 1


TEST_CASES = [
    # (param_value, first_use, label)
    (100, True,  "1st first-use"),
    (200, True,  "2nd first-use (duplicate)"),
    (300, True,  "3rd first-use (duplicate)"),
    (400, False, "subsequent after first-uses"),
    (500, True,  "first-use after subsequent"),
    (600, False, "subsequent after mixed"),
]

try:
    while not client_ready:
        poll_server(server)

    poll_server(server, 20)

    log.info("Sending test RPCs...")
    for param, first_use, label in TEST_CASES:
        send_rpc_raw('RPC_Int', [param], first_use, label)
        poll_server(server, 10)

    log.info(f"All {len(TEST_CASES)} RPCs sent. Waiting for client to finish...")

    deadline = time.time() + 15
    while time.time() < deadline:
        poll_server(server)

    log.info("Server done.")

except KeyboardInterrupt:
    pass
finally:
    server.stop()
