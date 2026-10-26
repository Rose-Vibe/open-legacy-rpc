#!/usr/bin/env python3
"""Interop test: Python server with password auth accepting Unity clients.

Start this, then launch Unity client with PasswordExperiment (sends password 'testpass').
The server sends RPC_Int(42) on connect to verify the session works.

Usage:
  sudo ip netns exec unitynet python3 tests/interop_password_server.py
"""
import logging
import sys

sys.path.insert(0, '.')
from protocol.unity_server import UnityServer

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s %(message)s')
log = logging.getLogger('interop')


def main():
    server = UnityServer(port=7777, password='testpass')
    server.start()
    log.info('Server started on port 7777, password=testpass')

    connected = []

    def on_connect(addr, player_idx):
        log.info(f'Client connected: addr={addr}, player_idx={player_idx}')
        connected.append(addr)
        server.send_rpc('RPC_Int', params=[42], target=addr, target_view=0x2000)
        log.info('Sent RPC_Int(42)')

    server.on_connect(on_connect)
    server.on_disconnect(lambda addr, idx: log.info(f'Client disconnected: {addr}'))

    log.info('Waiting for Unity client...')
    server.run(duration=30.0)
    server.stop()

    if connected:
        log.info(f'PASS: {len(connected)} client(s) connected with correct password')
        return 0
    else:
        log.error('FAIL: no client connected')
        return 1


if __name__ == '__main__':
    sys.exit(main())
