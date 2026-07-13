#!/usr/bin/env python3
"""
Unified method_tag collision repro driver
(docs/plans/method-tag-collision-repro.md, scenarios S1-S7).

Every send in every scenario goes through the real public API
(UnityServer.send_rpc()) -- no hand-crafted packets. Forced repeated
first-use is a wire condition a real Unity sender never produces, and
distance-server's actual bug (Bug 2 / Finding A) requires no repetition:
it happened on a method's single, unavoidable first-use. Testing that
condition faithfully means never bypassing the real API.

Real per-method-name tags (docs/research/2026-07-12-method-tag-real-
derivation.md, protocol/unity_protocol.py's _LOADER_REAL_TAGS):

  tag 0:  RPC_Void, RPC_String
  tag 4:  RPC_NetworkPlayer, RPC_Alpha, RPC_Beta, RPC_Gamma
  tag 8:  RPC_Int, RPC_Vector3, RPC_Quaternion, RPC_IntFloatString, RPC_NetworkViewID
  tag 12: RPC_Float, RPC_Bytes

Usage:
  python3 scripts/tag-collision-server.py --scenario N [--repeat N] [--port PORT]
"""
import argparse
import logging
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from protocol.unity_server import UnityServer
from protocol.unity_protocol import RPCMode

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s %(message)s')
log = logging.getLogger('tag-collision')

# Scene view (id=1) -- matches Loader.cs's PrimaryNetworkView, which is a
# scene-placed NetworkView (GetComponent<NetworkView>()), not an allocated
# one. Using 0x2000 (allocated id=0) raises "Internal RPC error. Invalid
# RPC index, function not registered."
TARGET_VIEW = 0x0002

# --- Instrumentation: log every batch-index (0x07) registration ---
# UnityServer._handle_batch_index is silent by default. Whether, and what,
# the client registers via 0x07 *after a misdispatched first-use* is the
# single most mechanism-revealing observable available -- it tells us
# whether the client resolved the method's true identity internally even
# while dispatching it to the wrong handler. Wrapped here rather than
# changed in the library, since this is test-only instrumentation.
_orig_handle_batch_index = UnityServer._handle_batch_index


def _logged_handle_batch_index(self, addr, payload):
    before = dict(self._peer_indices.get(addr, {}))
    _orig_handle_batch_index(self, addr, payload)
    after = self._peer_indices.get(addr, {})
    for name, idx in after.items():
        if before.get(name) != idx:
            log.info("BATCH_INDEX: client registered %s -> index %s", name, idx)


UnityServer._handle_batch_index = _logged_handle_batch_index


def poll_server(srv, count=1, interval=0.05):
    for _ in range(count):
        srv.poll(0.01)
        for peer in list(srv._raknet.peers.values()):
            peer.check_retransmits()
        time.sleep(interval)


def make_server(port=7777):
    server = UnityServer(port=port)
    state = {'addr': None, 'ready': False}

    def on_connect(addr, player_idx):
        state['addr'] = addr
        log.info("Client connected: %s (player %s)", addr, player_idx)

    def on_ready(addr, val):
        state['ready'] = True
        log.info("Client ready ping (RPC_Gamma=%s) received", val)

    server.on_connect(on_connect)
    server.on_rpc('RPC_Gamma', on_ready)
    return server, state


def send(server, addr, method_name, params, mode=RPCMode.All, label=None):
    log.info("Sending %s%s [%s]%s", method_name, params, mode.name,
             f" -- {label}" if label else "")
    server.send_rpc(method_name, params, target=addr, mode=mode,
                    target_view=TARGET_VIEW)


def index_known(server, addr, method_name):
    return server._peer_indices.get(addr, {}).get(method_name) is not None


def wait_for_index(server, addr, method_name, max_polls=60, interval=0.05):
    """Poll until method_name's index is registered via 0x07, or give up.

    Returns True if the index registered (clean precondition), False if it
    never arrived within the deadline (degraded run -- log this in the
    findings write-up; the tag claim from the first-use send still holds
    either way, but the "would spacing sends around the round trip help"
    question is only answerable when this precondition is on record).
    """
    for _ in range(max_polls):
        if index_known(server, addr, method_name):
            log.info("PRECONDITION: %s index registered (0x07 arrived)", method_name)
            return True
        poll_server(server, 1, interval)
    log.warning(
        "PRECONDITION-DEGRADED: %s index NOT registered after %d polls "
        "(no 0x07 arrived) -- proceeding anyway; the tag claim from the "
        "first-use send still holds, but this run should be labeled "
        "degraded for the ordering-mitigation question",
        method_name, max_polls)
    return False


SCENARIOS = {
    1: "baseline / harness gate (RPC_String tag0, RPC_Float tag12, no collision)",
    2: "PRIMARY -- tag 12 order A: Float claims, Bytes single first-use",
    3: "order B (mirror of S2) -- tag 12: Bytes claims, Float single first-use",
    4: "3-way collision -- tag 8: Int / Vector3 / IntFloatString",
    5: "tag-0 sentinel check: Void claims, String single first-use",
    6: "RPCMode.Others variant of S2",
    7: "outbound-contamination probe -- tag 4: Alpha vs. client's own Gamma ping",
    8: "DIAGNOSTIC (not in original S1-S7 matrix): single-method index-staleness "
       "isolation -- RPC_Float first-use -> wait for 0x07 -> immediate subsequent-use "
       "of RPC_Float only, no other method's first-use in between. Added to "
       "investigate an S2 anomaly (see tag-collision-fable-design consult): S2's "
       "recovery/victim-check subsequent-use sends, using indices the client itself "
       "just reported via 0x07, dispatched to unrelated methods (RPC_NetworkPlayer, "
       "RPC_IntFloatString) instead of the claimed method. This isolates whether that "
       "requires a second method's first-use to intervene, or happens regardless.",
}


def _run_once(n, port):
    server, state = make_server(port)
    server.start()
    log.info("=== Scenario %d: %s ===", n, SCENARIOS[n])
    log.info("Server started on port %d, waiting for client...", port)

    try:
        deadline = time.time() + 30
        while not state['ready'] and time.time() < deadline:
            poll_server(server)
        if not state['ready']:
            log.error("Client never sent ready ping -- aborting scenario")
            return
        poll_server(server, 20)
        addr = state['addr']

        if n == 1:
            send(server, addr, 'RPC_String', ['baseline'], label='tag0, no collision')
            poll_server(server, 30)
            send(server, addr, 'RPC_Float', [1.23], label='tag12, no collision')
            poll_server(server, 30)

        elif n == 2:
            send(server, addr, 'RPC_Float', [9.99], label='claims tag12')
            wait_for_index(server, addr, 'RPC_Float')
            send(server, addr, 'RPC_Bytes', [bytes([0xDE, 0xAD, 0xBE, 0xEF])],
                 label='PRIMARY OBSERVATION: single unavoidable first-use')
            poll_server(server, 40)
            send(server, addr, 'RPC_Bytes', [bytes([0xCA, 0xFE, 0xBA, 0xBE])],
                 label='recovery send')
            poll_server(server, 40)
            send(server, addr, 'RPC_Float', [2.72],
                 label='victim-survival check: does the claimant still dispatch?')
            poll_server(server, 40)

        elif n == 3:
            send(server, addr, 'RPC_Bytes', [bytes([0xDE, 0xAD, 0xBE, 0xEF])],
                 label='claims tag12')
            wait_for_index(server, addr, 'RPC_Bytes')
            send(server, addr, 'RPC_Float', [9.99],
                 label='PRIMARY OBSERVATION (mirrored order)')
            poll_server(server, 40)
            send(server, addr, 'RPC_Float', [2.72], label='recovery send')
            poll_server(server, 40)
            send(server, addr, 'RPC_Bytes', [bytes([0xCA, 0xFE, 0xBA, 0xBE])],
                 label='victim-survival check')
            poll_server(server, 40)

        elif n == 4:
            steps = [
                ('RPC_Int', [999]),
                ('RPC_Vector3', [(1.0, 2.0, 3.0)]),
                ('RPC_IntFloatString', [7, 2.5, 'x']),
            ]
            for name, params in steps:
                send(server, addr, name, params, label='first-use (3-way, tag8)')
                poll_server(server, 30)
            for name, params in steps:
                send(server, addr, name, params, label='second send')
                poll_server(server, 30)

        elif n == 5:
            send(server, addr, 'RPC_Void', [], label='claims tag0 (server-sendable)')
            poll_server(server, 30)
            send(server, addr, 'RPC_String', ['sentinel-check'],
                 label='PRIMARY OBSERVATION: tag0 sentinel check')
            poll_server(server, 30)

        elif n == 6:
            send(server, addr, 'RPC_Float', [9.99], mode=RPCMode.Others,
                 label='claims tag12 (Others mode)')
            wait_for_index(server, addr, 'RPC_Float')
            send(server, addr, 'RPC_Bytes', [bytes([0xDE, 0xAD, 0xBE, 0xEF])],
                 mode=RPCMode.Others,
                 label='PRIMARY OBSERVATION under RPCMode.Others')
            poll_server(server, 40)

        elif n == 7:
            send(server, addr, 'RPC_Alpha', [111],
                 label='outbound-contamination probe (client already first-used '
                        'Gamma outbound, tag4, as its ready ping)')
            poll_server(server, 30)

        elif n == 8:
            send(server, addr, 'RPC_Float', [9.99],
                 label='DIAGNOSTIC: single-method claim, no other first-use follows')
            wait_for_index(server, addr, 'RPC_Float')
            send(server, addr, 'RPC_Float', [4.56],
                 label='DIAGNOSTIC: immediate subsequent-use of the SAME method, '
                       'isolating index-staleness from any second claimant')
            poll_server(server, 40)

        log.info("All sends for scenario %d complete. Waiting for client logs...", n)
        deadline = time.time() + 10
        while time.time() < deadline:
            poll_server(server)

    finally:
        server.stop()
        log.info("Server stopped.")


def run_scenario(n, port=7777, repeat=1):
    for rep in range(1, repeat + 1):
        if repeat > 1:
            log.info("########## Repeat %d/%d ##########", rep, repeat)
        _run_once(n, port)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--scenario', type=int, required=True, choices=range(1, 9))
    parser.add_argument('--port', type=int, default=7777)
    parser.add_argument('--repeat', type=int, default=1)
    args = parser.parse_args()
    run_scenario(args.scenario, port=args.port, repeat=args.repeat)
