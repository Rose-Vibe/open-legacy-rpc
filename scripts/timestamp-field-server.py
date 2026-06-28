#!/usr/bin/env python3
"""
Python server for TimestampFieldExperiment.

Tests whether the 16-bit "zeros" field (bits 88-103 in subsequent-use,
or the corresponding position in first-use) carries Network.time.

Sends RPCs with various values patched into that field:
  1. field=0x0000  RPC_Int(100) — baseline (normal zeros)
  2. field=0x0001  RPC_Int(200) — minimal non-zero
  3. field=0x00FF  RPC_Int(300) — 255
  4. field=0x0100  RPC_Int(400) — 256
  5. field=0x1000  RPC_Int(500) — 4096
  6. field=0x7FFF  RPC_Int(600) — max positive if signed
  7. field=0xFFFF  RPC_Int(700) — all ones

If Unity uses this as a timestamp, info.timestamp should vary.
If Unity ignores it, all RPCs deliver with timestamp=0 or Network.time.
If Unity validates it, some RPCs may be dropped.
"""
import sys
import os
import time
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from protocol.unity_server import UnityServer
from protocol.unity_protocol import (
    RPCMode, encode_rpc_subsequent, encode_rpc_first_use,
)
from protocol.raknet_transport import Reliability


def poll_server(srv, count=1, interval=0.05):
    for _ in range(count):
        srv.poll(0.01)
        for peer in list(srv._raknet.peers.values()):
            peer.check_retransmits()
        time.sleep(interval)


def patch_zeros_field(payload, bits, field_value, first_use, method_name):
    """Patch the 16-bit 'zeros' field in an encoded RPC payload.

    For subsequent-use: bits 88-103 (bytes 11-12).
    For first-use: offset depends on method_id length — it's at
    meta_offset + 4 (after the 4-bit method_tag).
    """
    data = bytearray(payload)

    if not first_use:
        # Subsequent-use: bits 88-103 = bytes 11 and 12
        data[11] = (field_value >> 8) & 0xFF
        data[12] = field_value & 0xFF
    else:
        # First-use: need to find the metadata block.
        # The zeros field is at meta_start + 4 bits (after method_tag).
        # meta_start = 160 + hash_extra_bits
        # For now, use bit-level manipulation.
        from protocol.unity_protocol import compute_method_id
        guid, hash_val = compute_method_id(method_name)
        method_id_bits = (len(guid) + len(hash_val)) * 8
        hash_extra_bits = method_id_bits - 48
        # zeros field is at: 160 + hash_extra_bits + 4 (after method_tag)
        zeros_start = 160 + hash_extra_bits + 4
        # Write 16 bits of field_value
        all_bits = list(''.join(f'{b:08b}' for b in data))
        field_bits = f'{field_value:016b}'
        for i in range(16):
            if zeros_start + i < len(all_bits):
                all_bits[zeros_start + i] = field_bits[i]
        # Reconstruct bytes
        bit_str = ''.join(all_bits)
        new_data = bytearray()
        for i in range(0, len(bit_str), 8):
            chunk = bit_str[i:i+8]
            if len(chunk) < 8:
                chunk = chunk.ljust(8, '0')
            new_data.append(int(chunk, 2))
        data = new_data

    return bytes(data), bits


logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s %(message)s')
log = logging.getLogger('timestamp-field')

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

TEST_CASES = [
    # (field_value, param_value, label)
    # All first-use encoding (264 bits = byte-aligned, avoids bit_length
    # truncation bug in send_to which doesn't pass sub-byte bit_length).
    (0x0000, 100, "baseline zeros #1"),
    (0x0000, 200, "baseline zeros #2"),
    (0x0000, 300, "baseline zeros #3"),
    (0x0001, 400, "field=0x0001"),
    (0x0000, 500, "baseline zeros #4"),
    (0x00FF, 600, "field=0x00FF"),
    (0x0100, 700, "field=0x0100"),
    (0x1000, 800, "field=0x1000"),
    (0x7FFF, 900, "field=0x7FFF"),
    (0xFFFF, 1000, "field=0xFFFF"),
]

try:
    while not client_ready:
        poll_server(server)

    poll_server(server, 20)

    log.info("Sending test RPCs with varying zeros-field values...")
    for field_val, param, label in TEST_CASES:
        log.info(f"  [{label}] Sending RPC_Int({param}) field=0x{field_val:04x}")

        payload, bits = encode_rpc_first_use(
            'RPC_Int', [param], view_id=0, rpc_counter=rpc_counter,
            mode=RPCMode.Server, target_view=0x0002)

        patched, bits = patch_zeros_field(payload, bits, field_val,
                                          True, 'RPC_Int')

        log.info(f"    raw:     {payload.hex()}")
        log.info(f"    patched: {patched.hex()}")

        server._raknet.send_to(client_addr, patched, Reliability.RELIABLE_ORDERED)
        rpc_counter += 1
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
