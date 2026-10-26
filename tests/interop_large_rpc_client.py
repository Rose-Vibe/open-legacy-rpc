#!/usr/bin/env python3
"""Interop test: Python client receiving large RPC_Bytes from Unity server.

Usage: Start Unity server with LargeRpcExperiment, then run this.
"""
import logging
import sys
import time

sys.path.insert(0, '.')
from protocol.unity_client import UnityClient

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s %(message)s')
log = logging.getLogger('interop')

received = []
expected_sizes = [100, 500, 1000, 2000, 5000, 10000]


def on_rpc_bytes(data):
    log.info(f'Received RPC_Bytes({len(data)} bytes)')
    valid = True
    phase = len(received)
    for i, b in enumerate(data):
        expected = (i + phase) & 0xFF
        if b != expected:
            log.error(f'  Data corruption at byte {i}: got {b}, expected {expected}')
            valid = False
            break
    if valid:
        log.info('  Data integrity OK')
    received.append((len(data), valid))


def main():
    client = UnityClient()
    client.on_rpc('RPC_Bytes', on_rpc_bytes)

    log.info('Connecting to Unity server...')
    client.connect('127.0.0.1', 7777, timeout=5.0)
    log.info(f'Connected, player_index={client.player_index}')

    start = time.monotonic()
    while time.monotonic() - start < 30.0:
        client.poll(0.05)
        if len(received) >= len(expected_sizes):
            break

    client.disconnect()

    log.info('=== Results ===')
    errors = []
    for i, expected_size in enumerate(expected_sizes):
        if i < len(received):
            actual_size, valid = received[i]
            status = 'OK' if actual_size == expected_size and valid else 'FAIL'
            log.info(f'  Phase {i}: expected={expected_size}, got={actual_size}, integrity={"OK" if valid else "CORRUPT"} [{status}]')
            if actual_size != expected_size:
                errors.append(f'Phase {i}: size mismatch {actual_size} != {expected_size}')
            if not valid:
                errors.append(f'Phase {i}: data corruption')
        else:
            errors.append(f'Phase {i}: not received')
            log.info(f'  Phase {i}: NOT RECEIVED')

    if errors:
        log.error(f'FAIL: {errors}')
        return 1
    log.info('PASS: All large RPC payloads received correctly')
    return 0


if __name__ == '__main__':
    sys.exit(main())
