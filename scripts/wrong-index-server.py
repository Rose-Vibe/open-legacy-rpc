#!/usr/bin/env python3
"""
Experiment: Send RPCs with deliberately WRONG method_index to Unity.

Tests whether Unity learns method_index from first-use/subsequent-use
pairs (learning protocol), or pre-computes indices from assembly metadata.

The Python server's registered indices (from the old assembly) are already
different from the current Unity build's indices. So even the "normal"
subsequent-use encoding is a cross-assembly test.

Test plan:
  Phase 1: First-use RPC_Int(100) — should always work (Huffman hash)
  Phase 2: Subsequent-use RPC_Int(101) with index 0x30 (arbitrary)
           If Unity learned index from Phase 1, this works.
           If Unity pre-computes, this is dropped.
  Phase 3: Subsequent-use RPC_Int(102) with same index 0x30
           If Phase 2 worked, this should too.
  Phase 4: First-use RPC_Float(3.14) — control: Huffman hash
  Phase 5: Subsequent-use RPC_Float(2.72) with index 0x08 (different arbitrary)
           Second method with its own fake index.
  Phase 6: Subsequent-use with index 0x78 (no prior first-use for this index)
           Orphan test — should be dropped.
  Phase 7: First-use RPC_String("alive") — verify connection works after orphan.
"""
import sys
import os
import time
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from protocol.unity_server import UnityServer
from protocol.unity_protocol import (
    RPCMode, MSG_ID_RPC, encode_view_id, METHOD_SIGNATURES,
    get_method_id, rpc_view_constant, METHOD_TAG_MAP,
)
from protocol.bitstream import BitStream
from protocol.raknet_transport import Reliability

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s %(message)s')
log = logging.getLogger('wrong-index')


def _encode_params(bs, sig, params):
    for i, ptype in enumerate(sig):
        val = params[i] if i < len(params) else None
        if ptype == 'int':
            bs.write_i32_be(val if val is not None else 0)
        elif ptype == 'float':
            bs.write_float_be(val if val is not None else 0.0)
        elif ptype == 'string':
            from protocol.unity_protocol import _encode_string_param
            _encode_string_param(bs, val if val is not None else '')


def encode_first_use(method_name, params, rpc_counter, *, method_tag=None):
    """Encode first-use with optional tag override."""
    class_guid, method_hash = get_method_id(method_name)
    method_id_bits = (len(class_guid) + len(method_hash)) * 8
    length_indicator = method_id_bits // 4
    sig = METHOD_SIGNATURES.get(method_name, [])
    param_bs = BitStream()
    _encode_params(param_bs, sig, params)
    param_bits = param_bs.bit_length
    hash_extra_bits = method_id_bits - 48
    param_start = 160 + hash_extra_bits + 52 + 4
    total_bits = param_start + param_bits

    if method_tag is None:
        method_tag = METHOD_TAG_MAP.get(method_name, 0)

    bs = BitStream()
    bs.write_u8(MSG_ID_RPC)
    bs.write_bytes(encode_view_id(0))
    counter16 = (rpc_counter * 2) & 0xFFFF
    bs.write_u8((counter16 >> 8) & 0xFF)
    bs.write_u8(counter16 & 0xFF)
    bs.write_u8(0x0b)
    bs.write_bit(1)       # first_use
    bs.write_bits(0, 7)   # ref
    while bs.pos < 104:
        bs.write_bit(0)
    bs.write_u8(length_indicator)
    bs.write_bytes(class_guid)
    bs.write_bytes(method_hash)
    remaining_count = param_bits + 19
    bs.write_bits(method_tag, 4)
    bs.write_bits(0, 16)
    bs.write_u16_be(remaining_count)
    constant = rpc_view_constant('scene', 1)
    bs.write_u16_be(constant)
    bs.write_bits(int(RPCMode.Server), 4)
    for i in range(param_bs.bit_length):
        param_bs.pos = i
        bs.write_bit(param_bs.read_bit())
    return bs.to_bytes(), total_bits


def encode_subsequent(method_name, params, rpc_counter, *, method_index):
    """Encode subsequent-use with explicit index."""
    sig = METHOD_SIGNATURES.get(method_name, [])
    param_bs = BitStream()
    _encode_params(param_bs, sig, params)
    param_bits = param_bs.bit_length
    total_bits = 140 + param_bits

    bs = BitStream()
    bs.write_u8(MSG_ID_RPC)
    bs.write_bytes(encode_view_id(0))
    counter16 = (rpc_counter * 2) & 0xFFFF
    bs.write_u8((counter16 >> 8) & 0xFF)
    bs.write_u8(counter16 & 0xFF)
    bs.write_u8(0x0b)
    bs.write_bit(0)                     # subsequent-use
    bs.write_bits(method_index, 7)
    bs.write_u16_be(0)
    remaining = total_bits - 121
    bs.write_u16_be(remaining)
    constant = rpc_view_constant('scene', 1)
    bs.write_u16_be(constant)
    bs.write_bits(int(RPCMode.Server), 4)
    for i in range(param_bs.bit_length):
        param_bs.pos = i
        bs.write_bit(param_bs.read_bit())
    return bs.to_bytes(), total_bits


def poll_server(srv, count=1, interval=0.05):
    for _ in range(count):
        srv.poll(0.01)
        for peer in list(srv._raknet.peers.values()):
            peer.check_retransmits()
        time.sleep(interval)


server = UnityServer(port=7777)
client_ready = False
client_addr = None


def on_connect(addr, player_idx):
    global client_addr
    client_addr = addr
    log.info(f"Client connected: {addr} (player {player_idx})")
    server._rpc_sent_methods[addr] = set()


def on_rpc(addr, *params):
    global client_ready
    if len(params) == 1 and params[0] == -1:
        log.info("Client ping received — ready")
        client_ready = True
    else:
        log.info(f"Received RPC from client: {params}")


server.on_connect(on_connect)
server.on_rpc('RPC_Int', on_rpc)
server.on_rpc('RPC_Float', on_rpc)
server.on_rpc('RPC_String', on_rpc)
server.start()

log.info("Server started on port 7777, waiting for client...")

try:
    while not client_ready:
        poll_server(server)
    poll_server(server, 20)

    counter = 0

    def send(payload, bits):
        server._raknet.send_to(client_addr, payload, Reliability.RELIABLE_ORDERED,
                                bit_length=bits)
        poll_server(server, 20)

    # ── Phase 1: First-use RPC_Int ──
    log.info("Phase 1: first-use RPC_Int(100) — Huffman hash, should always work")
    p, b = encode_first_use('RPC_Int', [100], counter)
    counter += 1
    send(p, b)

    # ── Phase 2: Subsequent-use with arbitrary index 0x30 ──
    log.info("Phase 2: subsequent-use RPC_Int(101) index=0x30 — if Unity learned, this works")
    p, b = encode_subsequent('RPC_Int', [101], counter, method_index=0x30)
    counter += 1
    send(p, b)

    # ── Phase 3: Same arbitrary index again ──
    log.info("Phase 3: subsequent-use RPC_Int(102) index=0x30 — repeat to confirm")
    p, b = encode_subsequent('RPC_Int', [102], counter, method_index=0x30)
    counter += 1
    send(p, b)

    # ── Phase 4: First-use RPC_Float ──
    log.info("Phase 4: first-use RPC_Float(3.14) — second method")
    p, b = encode_first_use('RPC_Float', [3.14], counter)
    counter += 1
    send(p, b)

    # ── Phase 5: Subsequent-use RPC_Float with different arbitrary index ──
    log.info("Phase 5: subsequent-use RPC_Float(2.72) index=0x08 — different fake index")
    p, b = encode_subsequent('RPC_Float', [2.72], counter, method_index=0x08)
    counter += 1
    send(p, b)

    # ── Phase 6: Orphan subsequent-use (no prior first-use) ──
    log.info("Phase 6: subsequent-use RPC_String('orphan') index=0x78 — no first-use sent")
    p, b = encode_subsequent('RPC_String', ['orphan'], counter, method_index=0x78)
    counter += 1
    send(p, b)

    # ── Phase 7: Verify connection still works ──
    log.info("Phase 7: first-use RPC_String('alive') — verify connection survived")
    p, b = encode_first_use('RPC_String', ['alive'], counter)
    counter += 1
    send(p, b)

    log.info("All 7 phases sent. Waiting for client logs...")
    deadline = time.time() + 15
    while time.time() < deadline:
        poll_server(server)

except KeyboardInterrupt:
    pass
finally:
    server.stop()
    log.info("Server stopped.")
