#!/usr/bin/env python3
"""Interop test: Python server with 3 Unity clients (MultiClientExperiment).

Expected behavior:
- 3 Unity clients connect
- Each sends RPC_Int with its player hash on connect
- Server broadcasts RPC_Int(999) to all when 3 are connected
- Server sends targeted RPC_Int(N*111) to each client
- Server sends targeted RPC_String("hello_player_N") to each client

Usage: Run this script first, then start 3 Unity clients.
"""
import logging
import sys
import time

sys.path.insert(0, '.')
from protocol.unity_server import UnityServer

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s %(message)s')
log = logging.getLogger('interop')

connected_clients = {}  # addr -> player_index
received_rpcs = []
phase = 0


def on_connect(addr, player_index):
    log.info(f'Client connected: {addr} player_index={player_index}')
    connected_clients[addr] = player_index


def on_disconnect(addr, player_index):
    log.info(f'Client disconnected: {addr}')
    connected_clients.pop(addr, None)


def on_rpc_int(addr, value):
    log.info(f'Received RPC_Int({value}) from {addr}')
    received_rpcs.append(('RPC_Int', value, addr))


def main():
    global phase
    server = UnityServer(port=7777)
    server.on_connect(on_connect)
    server.on_disconnect(on_disconnect)
    server.on_rpc('RPC_Int', on_rpc_int)

    log.info('Starting Python server on port 7777...')
    server.start()
    log.info('Server started. Waiting for 3 Unity clients...')

    start = time.monotonic()
    timeout = 45.0
    last_action = 0

    while time.monotonic() - start < timeout:
        server.poll(0.05)
        for peer in list(server._raknet.peers.values()):
            peer.check_retransmits()

        now = time.monotonic()

        if phase == 0 and len(connected_clients) >= 3:
            log.info(f'All 3 clients connected! Players: {list(connected_clients.values())}')
            phase = 1
            last_action = now

        elif phase == 1 and now - last_action > 1.0:
            log.info('Broadcasting RPC_Int(999) to all clients')
            server.send_rpc('RPC_Int', params=[999], target_view=0x2000)
            phase = 2
            last_action = now

        elif phase == 2 and now - last_action > 1.5:
            for i, (addr, pidx) in enumerate(connected_clients.items()):
                val = (i + 1) * 111
                log.info(f'Sending targeted RPC_Int({val}) to player {pidx} at {addr}')
                server.send_rpc('RPC_Int', params=[val], target=addr, target_view=0x2000)
            phase = 3
            last_action = now

        elif phase == 3 and now - last_action > 1.5:
            for i, (addr, pidx) in enumerate(connected_clients.items()):
                msg = f'hello_player_{i+1}'
                log.info(f'Sending targeted RPC_String("{msg}") to player {pidx}')
                server.send_rpc('RPC_String', params=[msg], target=addr, target_view=0x2000)
            phase = 4
            last_action = now

        elif phase == 4 and now - last_action > 2.0:
            break

    server.stop()

    log.info('=== Results ===')
    log.info(f'Connected clients: {len(connected_clients)}')
    log.info(f'RPCs received: {len(received_rpcs)}')
    for rpc in received_rpcs:
        log.info(f'  {rpc}')

    errors = []
    if len(connected_clients) < 3:
        errors.append(f'Only {len(connected_clients)} clients connected (expected 3)')
    if phase < 4:
        errors.append(f'Only reached phase {phase} (expected 4)')
    unique_players = set(connected_clients.values())
    if len(unique_players) < 3:
        errors.append(f'Only {len(unique_players)} unique player indices')

    if errors:
        log.error(f'FAIL: {errors}')
        return 1
    else:
        log.info('PASS: Multi-client interop succeeded')
        return 0


if __name__ == '__main__':
    sys.exit(main())
