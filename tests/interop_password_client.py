#!/usr/bin/env python3
"""Interop test: Python client connecting to a Unity server with password auth.

Tests:
1. Correct password → connects, receives RPC_Int(42)
2. Wrong password → connection rejected (timeout)

Usage: Run Unity server with PasswordInteropExperiment first.
  sudo ip netns exec unitynet python3 tests/interop_password_client.py
"""
import logging
import sys
import time

sys.path.insert(0, '.')
from protocol.unity_client import UnityClient

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s %(message)s')
log = logging.getLogger('interop')


def test_correct_password():
    log.info('=== Test: correct password ===')
    client = UnityClient()
    received = []
    client.on_rpc('RPC_Int', lambda v: received.append(v))

    client.connect('127.0.0.1', 7777, timeout=5.0, password='testpass')
    assert client.connected, "Should connect with correct password"
    log.info(f'Connected, player_index={client.player_index}')

    start = time.monotonic()
    while time.monotonic() - start < 10.0:
        client.poll(0.05)
        client._raknet.peer.check_retransmits()
        if 42 in received:
            break

    client.disconnect()
    assert 42 in received, f"Should receive RPC_Int(42), got {received}"
    log.info('PASS: correct password accepted, RPC received')


def test_wrong_password():
    log.info('=== Test: wrong password ===')
    client = UnityClient()
    try:
        client.connect('127.0.0.1', 7777, timeout=3.0, password='wrongpass')
        log.error('FAIL: connected with wrong password')
        client.disconnect()
        return False
    except TimeoutError:
        log.info('PASS: wrong password rejected (timed out)')
        return True


def main():
    errors = []

    try:
        test_correct_password()
    except Exception as e:
        log.error(f'FAIL correct password: {e}')
        errors.append(str(e))

    # Wait between tests for Unity to reset
    time.sleep(2.0)

    if not test_wrong_password():
        errors.append('Wrong password was accepted')

    if errors:
        log.error(f'FAIL: {errors}')
        return 1
    log.info('PASS: All password tests passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
