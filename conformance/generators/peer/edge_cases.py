"""Edge case peer test scenarios."""

import uuid


def _make_scenario(name, desc, steps, mode='basic'):
    return {
        'testInfo': {
            'testId': str(uuid.uuid4()),
            'testName': f"edgeCases: {name}",
            'testDescription': desc,
            'category': 'edgeCases',
            'mode': mode,
        },
        'steps': steps,
    }


PRESET_TESTS = [
    {
        'name': 'Connect disconnect reconnect',
        'desc': 'Client connects, disconnects, then reconnects with a new client',
        'steps': [
            {'action': 'startServer'},
            {'action': 'connect', 'client': 'c1'},
            {'action': 'assertConnected', 'client': 'c1'},
            {'action': 'disconnect', 'client': 'c1'},
            {'action': 'sleep', 'duration': 0.3},
            {'action': 'connect', 'client': 'c2'},
            {'action': 'assertConnected', 'client': 'c2'},
            {'action': 'disconnect', 'client': 'c2'},
        ],
    },
    {
        'name': 'RPC after connect',
        'desc': 'RPC immediately after connection completes',
        'steps': [
            {'action': 'startServer'},
            {'action': 'connect'},
            {'action': 'sendRpc', 'from': 'client', 'methodName': 'RPC_Int',
             'params': [{'type': 'int', 'value': 1}]},
            {'action': 'expectRpc', 'on': 'server', 'methodName': 'RPC_Int',
             'params': [{'type': 'int', 'value': 1}]},
            {'action': 'disconnect'},
        ],
    },
    {
        'name': 'Multiple RPCs rapid fire',
        'desc': 'Send 10 RPCs without waiting between them',
        'steps': [
            {'action': 'startServer'},
            {'action': 'connect'},
            {'action': 'assertConnected'},
        ] + [
            {'action': 'sendRpc', 'from': 'client', 'methodName': 'RPC_Int',
             'params': [{'type': 'int', 'value': i}]}
            for i in range(10)
        ] + [
            {'action': 'sleep', 'duration': 1.0},
            {'action': 'expectRpc', 'on': 'server', 'methodName': 'RPC_Int',
             'params': [{'type': 'int', 'value': 0}]},
            {'action': 'disconnect'},
        ],
    },
    {
        'name': 'Empty password accepted',
        'desc': 'Server with no password, client sends empty password',
        'steps': [
            {'action': 'startServer'},
            {'action': 'connect', 'password': ''},
            {'action': 'assertConnected'},
            {'action': 'disconnect'},
        ],
    },
]


def generate(mode, count=5, rng=None):
    if mode == 'basic':
        return [_make_scenario(p['name'], p['desc'], p['steps']) for p in PRESET_TESTS]
    return []
