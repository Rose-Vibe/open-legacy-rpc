#!/usr/bin/env python3
"""
Python server for method_index assignment experiment.

Tests how Unity assigns/resolves method_index in subsequent-use RPCs.

Test cases (all send RPC_Int with different param values to identify delivery):
  Phase 1 — first-use establishes method, then subsequent-use with various indices:
    A. first-use RPC_Int(100), then subsequent 0x54 RPC_Int(101) — baseline (formula index)
    B. first-use RPC_Int(200), then subsequent 0x42 RPC_Int(201) — arbitrary index
    C. first-use RPC_Int(300), then subsequent 0x00 RPC_Int(301) — zero index

  Phase 2 — subsequent-use without prior first-use:
    D. subsequent 0x54 RPC_Int(400) — formula index, no first-use

  Phase 3 — does FIRST subsequent-use establish the mapping?
    E. first-use RPC_Int(500), then subsequent 0x20 RPC_Int(501),
       then subsequent 0x20 RPC_Int(502) — same arbitrary index twice

If Unity computes the index from its own assembly, only A and D should work.
If Unity caches from the sender's subsequent-use, B/C/E might work too.
"""
import sys
import os
import time
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from protocol.unity_server import UnityServer
from protocol.unity_protocol import (
    RPCMode, encode_rpc_subsequent, encode_rpc_first_use,
    METHOD_INDEX_MAP, INDEX_TO_METHOD, METHOD_TAG_MAP,
)
from protocol.raknet_transport import Reliability


def poll_server(srv, count=1, interval=0.05):
    for _ in range(count):
        srv.poll(0.01)
        for peer in list(srv._raknet.peers.values()):
            peer.check_retransmits()
        time.sleep(interval)


def make_subsequent_with_index(method_name, params, method_index, view_id=0,
                                rpc_counter=0, target_view=0x0002):
    """Encode a subsequent-use RPC with an explicitly chosen method_index."""
    from protocol.bitstream import BitStream
    from protocol.unity_protocol import (
        MSG_ID_RPC, encode_view_id, METHOD_SIGNATURES,
        _encode_params, INTERNAL_RPCS, INTERNAL_RPC_CONSTANT,
        _resolve_target_view,
    )

    sig = METHOD_SIGNATURES.get(method_name, [])
    param_bs = BitStream()
    _encode_params(param_bs, sig, params)
    param_bits = param_bs.bit_length

    mode = RPCMode.Server
    relay_bits = 0
    target_bits = 0
    total_bits = 140 + target_bits + param_bits + relay_bits

    bs = BitStream()
    bs.write_u8(0x1b)  # MSG_ID_RPC
    bs.write_bytes(encode_view_id(view_id))
    counter16 = rpc_counter & 0xFFFF
    bs.write_u8((counter16 >> 8) & 0xFF)
    bs.write_u8(counter16 & 0xFF)
    bs.write_u8(0x0b)
    # first_use = 0
    bs.write_bit(0)
    # method_index — 7 bits, using our chosen value
    bs.write_bits(method_index, 7)
    # reserved 16 bits of zeros
    bs.write_u16_be(0)
    # remaining_bit_count = total_bits - 121
    remaining = total_bits - 121
    bs.write_u16_be(remaining)
    # target_view constant
    constant = _resolve_target_view(target_view)
    bs.write_u16_be(constant)
    # RPCMode (4 bits)
    bs.write_bits(int(mode), 4)
    # Parameters
    for i in range(param_bs.bit_length):
        param_bs.pos = i
        bs.write_bit(param_bs.read_bit())

    return bs.to_bytes(), total_bits


logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s %(message)s')
log = logging.getLogger('method-index')

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

try:
    while not client_ready:
        poll_server(server)

    poll_server(server, 20)
    log.info("Client ready. Starting method_index tests...")

    # === Test A: baseline — first-use then subsequent with formula index 0x54 ===
    log.info("=== TEST A: first-use + subsequent index=0x54 (formula) ===")
    payload, bits = encode_rpc_first_use(
        'RPC_Int', [100], view_id=0, rpc_counter=rpc_counter,
        mode=RPCMode.Server, target_view=0x0002)
    server._raknet.send_to(client_addr, payload, Reliability.RELIABLE_ORDERED,
                           bit_length=bits)
    rpc_counter += 1
    poll_server(server, 20)

    payload, bits = make_subsequent_with_index('RPC_Int', [101], 0x54,
                                               rpc_counter=rpc_counter)
    server._raknet.send_to(client_addr, payload, Reliability.RELIABLE_ORDERED,
                           bit_length=bits)
    rpc_counter += 1
    poll_server(server, 20)

    # === Test B: first-use then subsequent with arbitrary index 0x42 ===
    log.info("=== TEST B: first-use + subsequent index=0x42 (arbitrary) ===")
    payload, bits = encode_rpc_first_use(
        'RPC_Int', [200], view_id=0, rpc_counter=rpc_counter,
        mode=RPCMode.Server, target_view=0x0002)
    server._raknet.send_to(client_addr, payload, Reliability.RELIABLE_ORDERED,
                           bit_length=bits)
    rpc_counter += 1
    poll_server(server, 20)

    payload, bits = make_subsequent_with_index('RPC_Int', [201], 0x42,
                                               rpc_counter=rpc_counter)
    server._raknet.send_to(client_addr, payload, Reliability.RELIABLE_ORDERED,
                           bit_length=bits)
    rpc_counter += 1
    poll_server(server, 20)

    # === Test C: first-use then subsequent with index 0x00 ===
    log.info("=== TEST C: first-use + subsequent index=0x00 (zero) ===")
    payload, bits = encode_rpc_first_use(
        'RPC_Int', [300], view_id=0, rpc_counter=rpc_counter,
        mode=RPCMode.Server, target_view=0x0002)
    server._raknet.send_to(client_addr, payload, Reliability.RELIABLE_ORDERED,
                           bit_length=bits)
    rpc_counter += 1
    poll_server(server, 20)

    payload, bits = make_subsequent_with_index('RPC_Int', [301], 0x00,
                                               rpc_counter=rpc_counter)
    server._raknet.send_to(client_addr, payload, Reliability.RELIABLE_ORDERED,
                           bit_length=bits)
    rpc_counter += 1
    poll_server(server, 20)

    # === Test D: subsequent-use without any first-use, index=0x54 ===
    log.info("=== TEST D: subsequent index=0x54, NO first-use ===")
    payload, bits = make_subsequent_with_index('RPC_Int', [400], 0x54,
                                               rpc_counter=rpc_counter)
    server._raknet.send_to(client_addr, payload, Reliability.RELIABLE_ORDERED,
                           bit_length=bits)
    rpc_counter += 1
    poll_server(server, 20)

    # === Test E: first-use then two subsequent-use with same arbitrary index 0x20 ===
    log.info("=== TEST E: first-use + 2x subsequent index=0x20 ===")
    payload, bits = encode_rpc_first_use(
        'RPC_Int', [500], view_id=0, rpc_counter=rpc_counter,
        mode=RPCMode.Server, target_view=0x0002)
    server._raknet.send_to(client_addr, payload, Reliability.RELIABLE_ORDERED,
                           bit_length=bits)
    rpc_counter += 1
    poll_server(server, 20)

    payload, bits = make_subsequent_with_index('RPC_Int', [501], 0x20,
                                               rpc_counter=rpc_counter)
    server._raknet.send_to(client_addr, payload, Reliability.RELIABLE_ORDERED,
                           bit_length=bits)
    rpc_counter += 1
    poll_server(server, 20)

    payload, bits = make_subsequent_with_index('RPC_Int', [502], 0x20,
                                               rpc_counter=rpc_counter)
    server._raknet.send_to(client_addr, payload, Reliability.RELIABLE_ORDERED,
                           bit_length=bits)
    rpc_counter += 1
    poll_server(server, 20)

    log.info("All tests sent. Waiting for responses...")
    poll_server(server, 40)

    log.info("Done.")

except KeyboardInterrupt:
    pass
finally:
    server.shutdown()
