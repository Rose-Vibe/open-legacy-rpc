#!/usr/bin/env python3
"""
Phase 2 (method_tag investigation): behavioral accept/reject test.

Sends two first-use RPCs to a real Unity client for methods it has never
seen before, via the real public API (UnityServer.send_rpc()):

  RPC_Phase2Accept(777) with method_tag=8  -- the rule's PREDICTED (correct) tag
  RPC_Phase2Reject(999) with method_tag=8  -- a DELIBERATELY WRONG tag
                                               (correct predicted tag is 4),
                                               chosen to COLLIDE with the
                                               slot RPC_Phase2Accept just
                                               claimed, not an arbitrary
                                               wrong value

Per docs/research/2026-07-12-method-tag-real-derivation.md's "What This
Means" section, a wrong tag only actually breaks dispatch when it collides
with an already-occupied slot on that connection -- an arbitrary wrong tag
landing on an empty slot dispatches fine "by luck" (this is exactly what
RPC_Void/RPC_Int did in the original investigation). A first attempt at
this Phase 2 test used tag=0 for the reject case and got a false
"accept" for both messages: tag 0 was simply an empty slot on the fresh
connection, not evidence method_tag is cosmetic. Using tag=8 here
deliberately collides with the slot RPC_Phase2Accept (sent first, correct
tag=8) just claimed, reproducing the original investigation's actual
"collision" condition. Per that investigation, the possible outcomes for a
colliding wrong tag are an explicit "Internal RPC error. Invalid RPC index,
function not registered." OR a silent misdispatch to whatever handler
already occupies that slot (i.e. RPC_Phase2Accept's handler, possibly
logging a garbled/mismatched value since the two methods' signatures are
both a single int here so no decode error will surface).

Target view: SecondRpc, scene ID 2, routing constant 0x0004 (see
experiments/RpcTagPhase2Experiment.cs and
experiments/SceneVsAllocConstantExperiment.cs).
"""
import logging
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from protocol.unity_server import UnityServer
from protocol.unity_protocol import (
    RPCMode, METHOD_SIGNATURES, register_method_tag,
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s %(message)s')
log = logging.getLogger('rpc-tag-phase2')

TARGET_VIEW = 0x0004  # SecondRpc, scene ID 2

METHOD_SIGNATURES['RPC_Phase2Accept'] = ['int']
METHOD_SIGNATURES['RPC_Phase2Reject'] = ['int']

register_method_tag('RPC_Phase2Accept', 8)   # predicted (correct)
register_method_tag('RPC_Phase2Reject', 8)   # deliberately wrong (correct is 4);
                                              # collides with Accept's slot 8


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
        log.info("Client ready ping (RPC_Gamma=%s) received", val)

    server.on_connect(on_connect)
    server.on_rpc('RPC_Gamma', on_ready)
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

        log.info("Sending RPC_Phase2Accept(777) with method_tag=8 (predicted, correct)")
        server.send_rpc('RPC_Phase2Accept', [777], target=addr, mode=RPCMode.All,
                        target_view=TARGET_VIEW)
        poll_server(server, 40)

        log.info("Sending RPC_Phase2Reject(999) with method_tag=8 (deliberately wrong; correct is 4; collides with Accept's slot)")
        server.send_rpc('RPC_Phase2Reject', [999], target=addr, mode=RPCMode.All,
                        target_view=TARGET_VIEW)
        poll_server(server, 40)

        log.info("All sends complete. Waiting for client logs...")
        deadline = time.time() + 10
        while time.time() < deadline:
            poll_server(server)
    finally:
        server.stop()
        log.info("Server stopped.")


if __name__ == '__main__':
    main()
