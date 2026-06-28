#!/usr/bin/env python3
"""
Python server for CounterGapExperiment.

Tests whether Unity cares about RPC counter continuity.
Sends RPCs with deliberate gaps, duplicates, and reversals in the counter sequence.

Test cases:
  1. counter=0   RPC_Int(100) — baseline
  2. counter=5   RPC_Int(200) — gap of 5
  3. counter=6   RPC_Int(300) — sequential after gap
  4. counter=100  RPC_Int(400) — large gap
  5. counter=50   RPC_Int(500) — backwards jump
  6. counter=100  RPC_Int(600) — duplicate counter (same as test 4)
  7. counter=101  RPC_Int(700) — sequential again after duplicate
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
        for peer in list(srv._raknet.peers.values()):
            peer.check_retransmits()
        time.sleep(interval)


logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s %(message)s')
log = logging.getLogger('counter-gap')

server = UnityServer(port=7777)
client_ready = False
client_addr = None


def on_connect(addr, player_idx):
    global client_addr
    client_addr = addr
    log.info(f"Client connected: {addr} (player {player_idx})")
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

TEST_CASES = [
    # (counter, param_value, label)
    (0,   100, "baseline counter=0"),
    (5,   200, "gap to counter=5"),
    (6,   300, "sequential counter=6"),
    (100, 400, "large gap to counter=100"),
    (50,  500, "backwards jump to counter=50"),
    (100, 600, "duplicate counter=100"),
    (101, 700, "sequential counter=101"),
]

try:
    while not client_ready:
        poll_server(server)

    poll_server(server, 20)

    log.info("Sending test RPCs with varying counters...")
    for counter, param, label in TEST_CASES:
        log.info(f"  [{label}] Sending RPC_Int({param}) counter={counter}")
        # Override the server's internal counter for this send
        server._rpc_counters[client_addr] = counter
        # Force first-use encoding each time so method_index doesn't matter
        server._rpc_sent_methods[client_addr] = set()
        server.send_rpc('RPC_Int', [param], target=client_addr,
                        mode=RPCMode.Server, view_id=0,
                        target_view=0x0002)
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
