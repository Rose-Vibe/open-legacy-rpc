#!/usr/bin/env python3
"""
Phase 2 ACCEPT-side control (method_tag investigation).

Companion to rpc-tag-phase2-control.py (the reject-side control, which
confirmed a deliberately wrong tag on a statically-compiled Loader RPC
method gets rejected with "Internal RPC error. Invalid RPC index, function
not registered."). This script sends a DIFFERENT statically-compiled
Loader method (RPC_Beta) using its real, correct tag (4, from
protocol/unity_protocol.py's _LOADER_REAL_TAGS -- no override), on a fresh
connection, to confirm the paired ACCEPT case: correct tag -> clean
dispatch, no error. Together the two scripts fully bracket Phase 2's
exit criterion for statically-known methods.
"""
import logging
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from protocol.unity_server import UnityServer
from protocol.unity_protocol import RPCMode

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s %(message)s')
log = logging.getLogger('rpc-tag-phase2-accept-control')

TARGET_VIEW = 0x0002  # Loader's PrimaryNetworkView, scene ID 1


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
        log.info("Client ready ping (RPC_Int=%s) received", val)

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
        log.info("Sending RPC_Beta(555) with its real, correct tag (4, no override)")
        server.send_rpc('RPC_Beta', [555], target=addr, mode=RPCMode.All,
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
