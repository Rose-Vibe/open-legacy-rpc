"""Handshake peer test scenarios."""

import random
import uuid


def _make_scenario(name, desc, steps, mode='basic'):
    return {
        'testInfo': {
            'testId': str(uuid.uuid4()),
            'testName': f"handshake: {name}",
            'testDescription': desc,
            'category': 'handshake',
            'mode': mode,
        },
        'steps': steps,
    }


PRESET_TESTS = [
    {
        'name': 'Basic connect',
        'desc': 'Client connects to server, handshake completes',
        'steps': [
            {'action': 'startServer'},
            {'action': 'connect'},
            {'action': 'assertConnected'},
            {'action': 'disconnect'},
        ],
    },
    {
        'name': 'Connect + disconnect',
        'desc': 'Connect, verify connected, disconnect, verify server sees disconnect',
        'steps': [
            {'action': 'startServer'},
            {'action': 'connect'},
            {'action': 'assertConnected'},
            {'action': 'disconnect'},
            {'action': 'expectServerDisconnect', 'count': 1},
        ],
    },
    {
        'name': 'Password auth',
        'desc': 'Client with correct password connects successfully',
        'steps': [
            {'action': 'startServer', 'password': 'testpass'},
            {'action': 'connect', 'password': 'testpass'},
            {'action': 'assertConnected'},
            {'action': 'disconnect'},
        ],
    },
    {
        'name': 'Wrong password',
        'desc': 'Client with wrong password is rejected',
        'steps': [
            {'action': 'startServer', 'password': 'testpass'},
            {'action': 'expectConnectTimeout', 'password': 'wrongpass', 'timeout': 2.0},
            {'action': 'assertDisconnected'},
        ],
    },
    {
        'name': 'Player index assignment',
        'desc': 'First client gets player index 1',
        'steps': [
            {'action': 'startServer'},
            {'action': 'connect'},
            {'action': 'assertConnected'},
            {'action': 'assertPlayerIndex', 'index': 1},
            {'action': 'disconnect'},
        ],
    },
    {
        'name': 'Two clients sequential',
        'desc': 'Two clients connect and get different player indices',
        'steps': [
            {'action': 'startServer'},
            {'action': 'connect', 'client': 'c1'},
            {'action': 'assertConnected', 'client': 'c1'},
            {'action': 'assertPlayerIndex', 'client': 'c1', 'index': 1},
            {'action': 'connect', 'client': 'c2'},
            {'action': 'assertConnected', 'client': 'c2'},
            {'action': 'assertPlayerIndex', 'client': 'c2', 'index': 2},
            {'action': 'disconnect', 'client': 'c1'},
            {'action': 'disconnect', 'client': 'c2'},
        ],
    },
]


def generate(mode, count=5, rng=None):
    if mode == 'basic':
        return [_make_scenario(p['name'], p['desc'], p['steps']) for p in PRESET_TESTS]
    rng = rng or random.Random()
    tests = []
    for i in range(count):
        pw = ''.join(chr(rng.randint(32, 126)) for _ in range(rng.randint(4, 12)))
        tests.append(_make_scenario(
            f"random password {i}", f"Password: {pw!r}",
            [
                {'action': 'startServer', 'password': pw},
                {'action': 'connect', 'password': pw},
                {'action': 'assertConnected'},
                {'action': 'disconnect'},
            ],
            mode='random',
        ))
    return tests
