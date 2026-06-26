#!/usr/bin/env python3
"""Interop test: Python client connecting to a Unity server running InteropExperiment.

Expected behavior:
- Unity server sends RPC_Int(777) on connect
- Unity server sends state sync updates: 42, 99, -1

Usage: Run Unity server first with InteropExperiment, then run this script.
  sudo ip netns exec unitynet python3 tests/interop_python_client.py
"""
import sys
import time
import logging
import struct

sys.path.insert(0, '.')
from protocol.unity_client import UnityClient

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s %(message)s')
log = logging.getLogger('interop')

received_rpcs = []
received_syncs = []


def on_rpc_int(value):
    log.info(f'Received RPC_Int({value})')
    received_rpcs.append(('RPC_Int', value))


def on_state_sync(result):
    ds = result['data_stream']
    val = ds.read_i32_be()
    log.info(f'Received state sync: {val}')
    received_syncs.append(val)


def main():
    client = UnityClient()
    client.on_rpc('RPC_Int', on_rpc_int)
    client.on_state_sync(None, on_state_sync)

    log.info('Connecting to Unity server at 127.0.0.1:7777...')
    try:
        client.connect('127.0.0.1', 7777, timeout=10.0)
    except TimeoutError:
        log.error('Connection timed out')
        return 1

    log.info(f'Connected! player_index={client.player_index}, viewid_base={client.viewid_base}')

    start = time.monotonic()
    timeout = 25.0
    while time.monotonic() - start < timeout:
        client.poll(0.05)
        client._raknet.peer.check_retransmits()

        rpc_ok = any(v == 777 for _, v in received_rpcs)
        sync_ok = 42 in received_syncs and 99 in received_syncs
        if rpc_ok and sync_ok:
            break

    client.disconnect()

    log.info('=== Results ===')
    log.info(f'RPCs received: {received_rpcs}')
    log.info(f'State syncs received: {sorted(set(received_syncs))}')

    errors = []
    if not any(v == 777 for _, v in received_rpcs):
        errors.append('Missing RPC_Int(777)')
    if 42 not in received_syncs:
        errors.append('Missing state sync value 42')
    if 99 not in received_syncs:
        errors.append('Missing state sync value 99')

    if errors:
        log.error(f'FAIL: {errors}')
        return 1
    else:
        log.info('PASS: All expected messages received')
        return 0


if __name__ == '__main__':
    sys.exit(main())
