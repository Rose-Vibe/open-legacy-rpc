#!/usr/bin/env python3
"""Interop test: Python client receiving state sync from 3 Unity NetworkViews.

Server runs MultiViewExperiment (3 views: RDC/int, Unreliable/float, Unreliable/Vector3).
"""
import logging
import struct
import sys
import time

sys.path.insert(0, '.')
from protocol.unity_client import UnityClient

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s %(message)s')
log = logging.getLogger('interop')

received_views = {}  # view_id -> list of values


def on_state_sync(result):
    vid = result['view_id']
    scope = result['view_id_scope']
    ds = result['data_stream']
    remaining_bits = result['data_bit_length']

    if remaining_bits <= 0:
        return

    key = (scope, vid)
    if key not in received_views:
        received_views[key] = []

    if remaining_bits == 32:
        raw = ds.read_bits(32)
        as_float = struct.unpack('>f', struct.pack('>I', raw))[0]
        as_int = struct.unpack('>i', struct.pack('>I', raw))[0]
        if abs(as_float) < 1e6 and as_float != 0 and abs(as_float) > 0.001:
            received_views[key].append(('float', as_float))
            log.info(f'View ({scope},{vid}): float={as_float}')
        else:
            received_views[key].append(('int', as_int))
            log.info(f'View ({scope},{vid}): int={as_int}')
    elif remaining_bits == 96:
        x = struct.unpack('>f', struct.pack('>I', ds.read_bits(32)))[0]
        y = struct.unpack('>f', struct.pack('>I', ds.read_bits(32)))[0]
        z = struct.unpack('>f', struct.pack('>I', ds.read_bits(32)))[0]
        received_views[key].append(('vec3', (x, y, z)))
        log.info(f'View ({scope},{vid}): Vector3=({x},{y},{z})')
    else:
        log.info(f'View ({scope},{vid}): {remaining_bits} bits (raw)')
        received_views[key].append(('raw', remaining_bits))


def main():
    client = UnityClient()
    client.on_state_sync(None, on_state_sync)

    log.info('Connecting to Unity server...')
    client.connect('127.0.0.1', 7777, timeout=5.0)
    log.info(f'Connected, player_index={client.player_index}')

    start = time.monotonic()
    while time.monotonic() - start < 20.0:
        client.poll(0.05)

    client.disconnect()

    log.info('=== Results ===')
    log.info(f'Views received: {len(received_views)}')
    for key, values in sorted(received_views.items()):
        log.info(f'  View {key}: {len(values)} updates')
        for v in values[-3:]:
            log.info(f'    {v}')

    errors = []
    if len(received_views) < 3:
        errors.append(f'Only received {len(received_views)} views (expected 3)')

    found_int = any(('int', 42) in vs or ('int', 99) in vs
                     for vs in received_views.values())
    found_float = any(any(t == 'float' for t, _ in vs)
                       for vs in received_views.values())
    found_vec3 = any(any(t == 'vec3' for t, _ in vs)
                      for vs in received_views.values())

    if not found_int:
        errors.append('No int state sync received')
    if not found_float:
        errors.append('No float state sync received')
    if not found_vec3:
        errors.append('No Vector3 state sync received')

    if errors:
        log.error(f'FAIL: {errors}')
        return 1
    log.info('PASS: Multi-view state sync received correctly')
    return 0


if __name__ == '__main__':
    sys.exit(main())
