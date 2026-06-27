"""Multi-client peer test scenarios."""

import uuid


def _make_scenario(name, desc, steps, mode='basic'):
    return {
        'testInfo': {
            'testId': str(uuid.uuid4()),
            'testName': f"multiClient: {name}",
            'testDescription': desc,
            'category': 'multiClient',
            'mode': mode,
        },
        'steps': steps,
    }


PRESET_TESTS = [
    {
        'name': 'Two clients connect',
        'desc': 'Two clients connect simultaneously, server sees both',
        'steps': [
            {'action': 'startServer'},
            {'action': 'connect', 'client': 'c1'},
            {'action': 'assertConnected', 'client': 'c1'},
            {'action': 'connect', 'client': 'c2'},
            {'action': 'assertConnected', 'client': 'c2'},
            {'action': 'assertServerConnections', 'count': 2},
            {'action': 'disconnect', 'client': 'c1'},
            {'action': 'disconnect', 'client': 'c2'},
        ],
    },
    {
        'name': 'Client disconnect cleanup',
        'desc': 'Client disconnects, server connection count decreases',
        'steps': [
            {'action': 'startServer'},
            {'action': 'connect', 'client': 'c1'},
            {'action': 'connect', 'client': 'c2'},
            {'action': 'assertServerConnections', 'count': 2},
            {'action': 'disconnect', 'client': 'c1'},
            {'action': 'expectServerDisconnect', 'count': 1},
            {'action': 'assertServerConnections', 'count': 1},
            {'action': 'disconnect', 'client': 'c2'},
        ],
    },
    {
        'name': 'Three clients sequential',
        'desc': 'Three clients connect one after another',
        'steps': [
            {'action': 'startServer'},
            {'action': 'connect', 'client': 'c1'},
            {'action': 'assertPlayerIndex', 'client': 'c1', 'index': 1},
            {'action': 'connect', 'client': 'c2'},
            {'action': 'assertPlayerIndex', 'client': 'c2', 'index': 2},
            {'action': 'connect', 'client': 'c3'},
            {'action': 'assertPlayerIndex', 'client': 'c3', 'index': 3},
            {'action': 'assertServerConnections', 'count': 3},
            {'action': 'disconnect', 'client': 'c1'},
            {'action': 'disconnect', 'client': 'c2'},
            {'action': 'disconnect', 'client': 'c3'},
        ],
    },
    {
        'name': 'RPC to specific client',
        'desc': 'Server sends RPC to one specific client',
        'steps': [
            {'action': 'startServer'},
            {'action': 'connect', 'client': 'c1'},
            {'action': 'connect', 'client': 'c2'},
            {'action': 'sendRpc', 'from': 'server', 'target': 'c1',
             'methodName': 'RPC_Int', 'params': [{'type': 'int', 'value': 42}]},
            {'action': 'expectRpc', 'on': 'c1', 'methodName': 'RPC_Int',
             'params': [{'type': 'int', 'value': 42}]},
            {'action': 'disconnect', 'client': 'c1'},
            {'action': 'disconnect', 'client': 'c2'},
        ],
    },
]


def generate(mode, count=5, rng=None):
    if mode == 'basic':
        return [_make_scenario(p['name'], p['desc'], p['steps']) for p in PRESET_TESTS]
    return []
