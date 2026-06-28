#!/usr/bin/env python3
"""
Capture server for method_index experiment.
Accepts Unity client connections and dumps raw RPC bytes to show
what method_index Unity assigns for subsequent-use RPCs.
"""
import sys
import os
import time
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from protocol.unity_server import UnityServer
from protocol.raknet_transport import Reliability

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s %(message)s')
log = logging.getLogger('capture')

server = UnityServer(port=7777)
rpc_count = 0


def on_connect(addr, player_idx):
    log.info(f"Client connected: {addr} (player {player_idx})")


def on_raw_message(addr, payload, bit_length):
    global rpc_count
    if not payload or payload[0] != 0x1b:
        return
    if len(payload) < 10 or payload[9] != 0x0b:
        return

    rpc_count += 1
    all_bits = ''.join(f'{b:08b}' for b in payload)
    first_use = int(all_bits[80])

    if first_use:
        # Extract method name via huffman
        try:
            from protocol.unity_protocol import decode_rpc
            decoded = decode_rpc(payload, bit_length)
            name = decoded.get('method_name', '?')
        except:
            name = '?'

        ref_bits = int(all_bits[81:88], 2)
        log.info(f"RPC #{rpc_count} FIRST-USE: ref_bits=0x{ref_bits:02x} name={name}")
        log.info(f"  byte 10=0x{payload[10]:02x} byte 11=0x{payload[11]:02x} "
                 f"byte 12=0x{payload[12]:02x}")
    else:
        method_idx_7bit = int(all_bits[81:88], 2)
        method_idx_8bit = int(all_bits[80:88], 2) & 0xFE
        reserved = int(all_bits[88:104], 2)
        log.info(f"RPC #{rpc_count} SUBSEQUENT: "
                 f"7bit_idx=0x{method_idx_7bit:02x} ({method_idx_7bit}) "
                 f"8bit_idx=0x{method_idx_8bit:02x} ({method_idx_8bit}) "
                 f"reserved=0x{reserved:04x}")
        log.info(f"  byte 10=0x{payload[10]:02x} byte 11=0x{payload[11]:02x} "
                 f"byte 12=0x{payload[12]:02x}")

    log.info(f"  raw: {payload[:20].hex()}")


server.on_connect(on_connect)

# Hook into raw message handling
original_handle = server._handle_rpc


def capturing_handle(addr, payload, bit_length):
    on_raw_message(addr, payload, bit_length)
    return original_handle(addr, payload, bit_length)


server._handle_rpc = capturing_handle
server.start()

log.info("Capture server started on port 7777, waiting...")

try:
    deadline = time.time() + 30
    while time.time() < deadline:
        server.poll(0.01)
        for peer in list(server._raknet.peers.values()):
            peer.check_retransmits()
        time.sleep(0.05)
        if rpc_count >= 5:
            time.sleep(2)
            break
    log.info("Done.")
except KeyboardInterrupt:
    pass
