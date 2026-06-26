#!/usr/bin/env python3
"""Interop test: Python server accepting a Unity client running ClientInteropExperiment.

Expected behavior:
- Unity client sends RPC_Int(42) on connect
- Unity client sends RPC_Int(999) at tick ~50

Usage: Run this script first, then start Unity client with ClientInteropExperiment.
  sudo ip netns exec unitynet python3 tests/interop_python_server.py
"""
import sys
import time
import logging

sys.path.insert(0, '.')
from protocol.unity_server import UnityServer

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s %(message)s')
log = logging.getLogger('interop')

received_rpcs = []
client_connected = False


def on_connect(addr, player_index):
    global client_connected
    log.info(f'Client connected: {addr} player_index={player_index}')
    client_connected = True


def on_disconnect(addr, player_index):
    global client_connected
    log.info(f'Client disconnected: {addr}')
    client_connected = False


def on_rpc_int(addr, value):
    log.info(f'Received RPC_Int({value}) from {addr}')
    received_rpcs.append(('RPC_Int', value))


def main():
    server = UnityServer(port=7777)
    server.on_connect(on_connect)
    server.on_disconnect(on_disconnect)
    server.on_rpc('RPC_Int', on_rpc_int)

    log.info('Starting Python server on port 7777...')
    server.start()
    log.info('Server started. Waiting for Unity client...')

    start = time.monotonic()
    timeout = 30.0
    while time.monotonic() - start < timeout:
        server.poll(0.05)
        for peer in list(server._raknet.peers.values()):
            peer.check_retransmits()

        got_42 = any(v == 42 for _, v in received_rpcs)
        got_999 = any(v == 999 for _, v in received_rpcs)
        if got_42 and got_999:
            break

    server.stop()

    log.info('=== Results ===')
    log.info(f'RPCs received: {received_rpcs}')

    errors = []
    if not client_connected and not received_rpcs:
        errors.append('No client connected')
    if not any(v == 42 for _, v in received_rpcs):
        errors.append('Missing RPC_Int(42)')
    if not any(v == 999 for _, v in received_rpcs):
        errors.append('Missing RPC_Int(999)')

    if errors:
        log.error(f'FAIL: {errors}')
        return 1
    else:
        log.info('PASS: All expected messages received')
        return 0


if __name__ == '__main__':
    sys.exit(main())
