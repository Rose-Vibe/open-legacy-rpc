#!/usr/bin/env python3
"""
Phase 2 CONTROL test (method_tag investigation).

Phase 2's main test (rpc-tag-phase2-server.py) sent a deliberately-wrong,
slot-colliding method_tag for a method on a RUNTIME-AddComponent'd class
(Phase2TagBehaviour, discovered via reflection, never known to Unity at
domain-load time) and found it dispatched anyway -- no rejection, contrary
to docs/research/2026-07-12-method-tag-real-derivation.md's original
finding that a wrong, slot-colliding tag for RPC_Float caused
"Internal RPC error. Invalid RPC index, function not registered."

Before concluding that finding doesn't reproduce, or reproduce differently
for compile-time-known methods, this control re-tests the ORIGINAL
mechanism directly, using ONLY Loader's own statically-compiled [RPC]
methods (part of Assembly-CSharp, discoverable at Unity's normal
domain-load reflection scan -- no AddComponent, no experiments DLL type
involved in the receiving side at all):

  1. RPC_Int(-1) sent first, as WrongIndexExperiment.cs's own built-in
     ready ping -- real tag 8 (docs/research/2026-07-12-method-tag-real-
     derivation.md's ground truth table). Occupies tag-slot 8.
  2. RPC_Float(1.23) sent second, with method_tag FORCED to 8 (deliberately
     wrong; real tag is 12) -- deliberately colliding with the slot RPC_Int
     just claimed. Per the original finding, expect either an explicit
     "Internal RPC error. Invalid RPC index, function not registered." or a
     silent misdispatch to RPC_Int's handler.

Uses experiments/WrongIndexExperiment.cs unmodified as the client (no
Unity rebuild needed) -- it already sends RPC_Int as a ready ping and does
nothing else, exactly the harness this control needs.
"""
import logging
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from protocol.unity_server import UnityServer
from protocol.unity_protocol import RPCMode, register_method_tag

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s %(message)s')
log = logging.getLogger('rpc-tag-phase2-control')

TARGET_VIEW = 0x0002  # Loader's PrimaryNetworkView, scene ID 1

register_method_tag('RPC_Float', 8)  # deliberately wrong (real is 12); collides with RPC_Int's slot 8


def poll_server(srv, count=1, interval=0.05):
    for _ in range(count):
        srv.poll(0.01)
        for peer in list(srv._raknet.peers.values()):
            peer.check_retransmits()
        time.sleep(interval)


def main():
    server = UnityServer(port=7777)
    state = {'addr': None, 'ready': False}

    def on_connect(addr, player_idx):
        state['addr'] = addr
        log.info("Client connected: %s (player %s)", addr, player_idx)

    def on_ready(addr, val):
        state['ready'] = True
        log.info("Client ready ping (RPC_Int=%s) received -- occupies tag-slot 8", val)

    server.on_connect(on_connect)
    server.on_rpc('RPC_Int', on_ready)
    server.start()
    log.info("Server started on port 7777, waiting for client...")

    try:
        deadline = time.time() + 30
        while not state['ready'] and time.time() < deadline:
            poll_server(server)
        if not state['ready']:
            log.error("Client never sent ready ping -- aborting")
            return
        addr = state['addr']

        poll_server(server, 10)
        log.info("Sending RPC_Float(1.23) with method_tag=8 (deliberately wrong; real is 12; collides with RPC_Int's slot)")
        server.send_rpc('RPC_Float', [1.23], target=addr, mode=RPCMode.All,
                        target_view=TARGET_VIEW)
        poll_server(server, 40)

        log.info("Send complete. Waiting for client logs...")
        deadline = time.time() + 10
        while time.time() < deadline:
            poll_server(server)
    finally:
        server.stop()
        log.info("Server stopped.")


if __name__ == '__main__':
    main()
