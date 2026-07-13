#!/usr/bin/env python3
"""
Static-index-table validation sweep (docs/plans/method-tag-collision-repro.md,
S2 anomaly follow-up).

S2 showed that a real Unity client's subsequent-use dispatch does NOT key off
the peer-reported 0x07 batch-index value. Mining existing Unity<->Unity
captures (RpcMultiParamExperiment, RpcModeOthersRelayExperiment,
RpcNameVaryExperiment, WrongIndexExperiment -- all real client+server, no
Python driver on either side) showed real subsequent-use sends always use a
FIXED per-method index matching the original derivation-doc table
(docs/research/2026-07-12-method-tag-real-derivation.md), and that in the
current build (which carries 3 extra non-Loader [RPC] classes --
InheritedRpcBase, SecondRpcBehaviour, InheritedRpcDerived -- versus the build
that table was captured against) every one of those doc indices is shifted by
a constant +12. That shift was solved from two independent equations in S2's
own misdispatch (120->IntFloatString needs +12, 124->NetworkPlayer needs +12)
and independently reproduced a third time, via exact packet-timestamp
correlation against WrongIndex-20260628-004459's server log, where a
hand-crafted index=120 send (Phase 6, no first-use) dispatched to
RPC_IntFloatString(16, ...) exactly as +12-shifted-table predicts.

This sweep tests that causal claim directly, for every Loader RPC method in
one connection: first-use once (hash-based, should always dispatch cleanly),
then subsequent-use with the COMPUTED (doc+12) index -- overriding
UnityServer._peer_indices rather than trusting the peer's self-reported 0x07
value, since S2 already showed that value is decoupled from dispatch. A
one-shot deliberate-wrong-index negative control and RPC_Gamma-last (for
S7's outbound-contamination question) close out the run.

PREDICTIONS (registered before running -- see PREDICTIONS dict below):
  every method's subsequent-use send at its own doc+12 index should dispatch
  clean. The negative control (RPC_Float's unique subsequent value sent at
  RPC_IntFloatString's index, 120) should either misdispatch to
  RPC_IntFloatString or produce an explicit signature-mismatch error naming
  it -- never a clean RPC_Float dispatch.

Usage:
  python3 scripts/index-sweep-server.py [--port PORT]
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
log = logging.getLogger('index-sweep')

TARGET_VIEW = 0x0002  # scene view (id=1) -- see tag-collision-server.py

# doc+12: docs/research/2026-07-12-method-tag-real-derivation.md indices,
# shifted +12 for this build's 3 extra non-Loader [RPC] classes.
# name: (computed_index, first_use_params, subsequent_params)
SWEEP = [
    ('RPC_Void',            92,  [],                    []),
    ('RPC_Int',             96,  [111],                 [211]),
    ('RPC_Float',           100, [11.1],                [21.1]),
    ('RPC_String',          104, ['first'],             ['second']),
    ('RPC_Vector3',         108, [(1.0, 1.1, 1.2)],     [(2.0, 2.1, 2.2)]),
    ('RPC_Quaternion',      112, [(0.1, 0.2, 0.3, 0.9)],[(0.4, 0.5, 0.6, 0.7)]),
    ('RPC_Bytes',           116, [bytes([0x11]*4)],     [bytes([0x22]*4)]),
    ('RPC_IntFloatString',  120, [1, 1.5, 'fu'],        [2, 2.5, 'su']),
    ('RPC_NetworkPlayer',   124, [1],                   [2]),
    ('RPC_NetworkViewID',   128, [0x1001],              [0x1002]),
    ('RPC_Alpha',           132, [301],                 [401]),
    ('RPC_Beta',            136, [302],                 [402]),
    # RPC_Gamma deliberately last: client already first-used it outbound (its
    # own ready ping) before any of these sends -- tests S7's
    # outbound-contamination question for free in this same run.
    ('RPC_Gamma',           140, [303],                 [403]),
]

# Negative control: force RPC_Float's *learned* index to IntFloatString's
# slot (120) and send a third, distinct RPC_Float value. Predicts either a
# clean misdispatch to RPC_IntFloatString or an explicit signature-mismatch
# error naming it -- never a clean RPC_Float dispatch. Run after the main
# sweep, since it deliberately corrupts _peer_indices['RPC_Float'].
NEGATIVE_CONTROL = ('RPC_Float', 120, 31.4)

PREDICTIONS = {name: idx for name, idx, _, _ in SWEEP}
PREDICTIONS['RPC_Float (negative control)'] = NEGATIVE_CONTROL[1]

_orig_handle_batch_index = UnityServer._handle_batch_index


def _logged_handle_batch_index(self, addr, payload):
    before = dict(self._peer_indices.get(addr, {}))
    _orig_handle_batch_index(self, addr, payload)
    after = self._peer_indices.get(addr, {})
    for name, idx in after.items():
        if before.get(name) != idx:
            log.info("BATCH_INDEX (informational, not used for dispatch): "
                     "client registered %s -> index %s", name, idx)


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
        log.info("Client ready ping (RPC_Gamma outbound=%s) received", val)

    server.on_connect(on_connect)
    server.on_rpc('RPC_Gamma', on_ready)
    return server, state


def send(server, addr, method_name, params, label=None):
    log.info("Sending %s%s%s", method_name, params, f" -- {label}" if label else "")
    server.send_rpc(method_name, params, target=addr, mode=RPCMode.All,
                    target_view=TARGET_VIEW)


def run(port=7777):
    server, state = make_server(port)
    server.start()
    log.info("=== Static-index-table validation sweep ===")
    log.info("PREDICTIONS: %s", PREDICTIONS)
    log.info("Server started on port %d, waiting for client...", port)

    try:
        deadline = time.time() + 30
        while not state['ready'] and time.time() < deadline:
            poll_server(server)
        if not state['ready']:
            log.error("Client never sent ready ping -- aborting sweep")
            return
        poll_server(server, 20)
        addr = state['addr']

        for name, computed_index, fu_params, su_params in SWEEP:
            send(server, addr, name, fu_params, label='first-use')
            poll_server(server, 30)

            # Override the learned-index table with the computed doc+12
            # index rather than trusting whatever 0x07 reported -- S2 showed
            # the 0x07 value is decoupled from dispatch.
            server._peer_indices.setdefault(addr, {})[name] = computed_index
            send(server, addr, name, su_params,
                 label=f'subsequent-use @ computed index {computed_index}')
            poll_server(server, 30)

        neg_name, neg_index, neg_value = NEGATIVE_CONTROL
        server._peer_indices.setdefault(addr, {})[neg_name] = neg_index
        send(server, addr, neg_name, [neg_value],
             label=f'NEGATIVE CONTROL: {neg_name} forced to index {neg_index} '
                   f'(RPC_IntFloatString\'s slot) -- predict misdispatch/mismatch, '
                   f'never a clean {neg_name} dispatch')
        poll_server(server, 40)

        log.info("Sweep complete. Waiting for client logs to settle...")
        deadline = time.time() + 10
        while time.time() < deadline:
            poll_server(server)

    finally:
        server.stop()
        log.info("Server stopped.")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=7777)
    args = parser.parse_args()
    run(port=args.port)
