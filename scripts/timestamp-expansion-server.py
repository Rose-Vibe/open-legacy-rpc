#!/usr/bin/env python3
"""
Python server for TimestampExpansionExperiment.

Sends RPCs with precisely controlled rpcCounter values to isolate
Unity's timestamp expansion behavior (MYSTERY_CLOCK identification).

Test sequence:
  Phase 1: Fixed rpcCounter values (0, 1000, 32768, 65535)
  Phase 2: rpcCounter=0 repeated at 5-second intervals for 80 seconds
           (exceeds one 65536ms cycle to detect high-bit rollover)
"""
import sys
import os
import time
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from protocol.unity_server import UnityServer
from protocol.unity_protocol import (
    RPCMode, encode_rpc_first_use,
)
from protocol.raknet_transport import Reliability


def poll_server(srv, count=1, interval=0.05):
    for _ in range(count):
        srv.poll(0.01)
        for peer in list(srv._raknet.peers.values()):
            peer.check_retransmits()
        time.sleep(interval)


logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s %(message)s')
log = logging.getLogger('timestamp-expansion')

server = UnityServer(port=7777)
client_ready = False
client_addr = None


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


def send_rpc(param_value, rpc_counter, label):
    """Send an RPC_Int with a specific rpc_counter value."""
    payload, bits = encode_rpc_first_use(
        'RPC_Int', [param_value], view_id=0, rpc_counter=rpc_counter,
        mode=RPCMode.Server, target_view=0x0002)

    # Verify the wire counter is what we expect
    actual_wire = (payload[7] << 8) | payload[8]
    log.info(f"  [{label}] value={param_value} wire_counter=0x{actual_wire:04x} "
             f"(wanted 0x{wire_counter:04x}) bits={bits}")

    server._raknet.send_to(client_addr, payload, Reliability.RELIABLE_ORDERED)


try:
    while not client_ready:
        poll_server(server)

    poll_server(server, 20)
    log.info("=== Phase 1: Fixed rpcCounter values ===")

    # Phase 1: Send RPCs with specific rpc_counter values
    PHASE1_TESTS = [
        # (param_value, wire_counter, label)
        (100, 0x0000, "counter=0"),
        (200, 0x03E8, "counter=1000"),
        (300, 0x8000, "counter=32768"),
        (400, 0xFFFE, "counter=65534"),
        (500, 0x0000, "counter=0 repeat"),
    ]

    for param, counter, label in PHASE1_TESTS:
        send_rpc(param, counter, label)
        poll_server(server, 20)  # ~1 second gap

    log.info("=== Phase 2: Time progression (rpcCounter=0 every 5s for 80s) ===")
    log.info("  If MYSTERY_CLOCK = clientTime & 0xFFFF0000, it should jump")
    log.info("  by 65536 once during this 80-second window.")

    start_time = time.time()
    phase2_count = 0
    while time.time() - start_time < 80:
        phase2_count += 1
        elapsed = time.time() - start_time
        send_rpc(1000 + phase2_count, 0x0000,
                 f"progression t={elapsed:.1f}s")

        # Wait 5 seconds, polling throughout
        wait_until = time.time() + 5.0
        while time.time() < wait_until:
            poll_server(server)

    log.info(f"=== Done: sent {len(PHASE1_TESTS) + phase2_count} RPCs total ===")

    # Wait for client to process
    deadline = time.time() + 10
    while time.time() < deadline:
        poll_server(server)

    log.info("Server done.")

except KeyboardInterrupt:
    pass
finally:
    server.stop()
