#!/usr/bin/env python3
"""Test ViewID block assignment scaling with increasing max_connections.

Connects N Python clients to a Unity server and logs the 0x81 message
fields for each client. Reveals how Unity computes block_start/block_end
as max_connections grows.

Usage:
  # Start Unity server with --max-connections N, then run this:
  sudo ip netns exec unitynet python3 tests/interop_viewid_scaling.py --count N
"""
import sys
import time
import struct
import logging
import argparse

sys.path.insert(0, '.')
from protocol.raknet_connection import RakNetClient, ConnectionState

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s %(message)s')
log = logging.getLogger('viewid-scaling')


class ProbeClient:
    """Minimal client that captures the raw 0x81 message fields."""

    def __init__(self, index):
        self.index = index
        self.raknet = RakNetClient()
        self.assignment = None
        self._orig_handler = self.raknet._handle_player_assignment

        def capture_assignment(payload):
            if len(payload) >= 29:
                fields = struct.unpack('>IIIIIII', payload[1:29])
                self.assignment = {
                    'constant_1': fields[0],
                    'constant_0': fields[1],
                    'player_index': fields[2],
                    'viewid_stride': fields[3],
                    'constant_2': fields[4],
                    'block_start': fields[5],
                    'block_end': fields[6],
                    'alloc_start': fields[5] * fields[3],
                }
            self._orig_handler(payload)

        self.raknet._handle_player_assignment = capture_assignment


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--count', type=int, default=4, help='Number of clients to connect')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=7777)
    args = parser.parse_args()

    clients = []
    for i in range(args.count):
        c = ProbeClient(i)
        clients.append(c)

    log.info(f'Connecting {args.count} clients to {args.host}:{args.port}...')

    for i, c in enumerate(clients):
        try:
            c.raknet.connect(args.host, args.port, timeout=5.0)
            log.info(f'  Client {i+1} connected: player_index={c.raknet.player_index}')
        except Exception as e:
            log.error(f'  Client {i+1} FAILED to connect: {e}')
            break
        time.sleep(0.3)

    log.info('')
    log.info(f'{"Client":>7} {"player_idx":>10} {"stride":>6} {"blk_start":>9} {"blk_end":>7} {"alloc_start":>11}')
    log.info('-' * 60)

    for c in clients:
        if c.assignment:
            a = c.assignment
            log.info(f'{c.index+1:>7} {a["player_index"]:>10} {a["viewid_stride"]:>6} '
                     f'{a["block_start"]:>9} {a["block_end"]:>7} {a["alloc_start"]:>11}')
        else:
            log.info(f'{c.index+1:>7} {"NO ASSIGNMENT":>40}')

    # Check for issues
    if clients and clients[-1].assignment:
        last = clients[-1].assignment
        log.info(f'\nHighest alloc_start: {last["alloc_start"]}')
        if last['alloc_start'] >= 1000:
            log.warning(f'alloc_start >= 1000 — potential ViewID overflow!')

    for c in clients:
        try:
            c.raknet.disconnect()
        except:
            pass

    return 0


if __name__ == '__main__':
    sys.exit(main())
