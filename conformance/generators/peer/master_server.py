"""Master server peer test scenarios."""

import random
import uuid


def _make_scenario(name, desc, steps, mode='basic'):
    return {
        'testInfo': {
            'testId': str(uuid.uuid4()),
            'testName': f"masterServer: {name}",
            'testDescription': desc,
            'category': 'masterServer',
            'mode': mode,
        },
        'steps': steps,
    }


def _connect_steps(client='default'):
    return [
        {'action': 'startMasterServer'},
        {'action': 'connectMaster', 'client': client},
    ]


PRESET_TESTS = [
    {
        'name': 'Register and query',
        'desc': 'Register a host, query for it, verify it appears',
        'steps': _connect_steps() + [
            {'action': 'registerHost', 'gameType': 'TestGame', 'name': 'Server1', 'port': 7777},
            {'action': 'requestHostList', 'gameType': 'TestGame'},
            {'action': 'assertHostCount', 'count': 1},
            {'action': 'assertHostField', 'index': 0, 'field': 'game_name', 'value': 'Server1'},
            {'action': 'disconnectMaster'},
        ],
    },
    {
        'name': 'Unregister removes host',
        'desc': 'Register, unregister, query returns empty',
        'steps': _connect_steps('c1') + [
            {'action': 'connectMaster', 'client': 'c2'},
            {'action': 'registerHost', 'client': 'c1', 'gameType': 'TestGame',
             'name': 'Server1', 'regKey': 'r1'},
            {'action': 'unregisterHost', 'client': 'c1', 'gameType': 'TestGame', 'regKey': 'r1'},
            {'action': 'requestHostList', 'client': 'c2', 'gameType': 'TestGame'},
            {'action': 'assertHostCount', 'count': 0},
            {'action': 'disconnectMaster', 'client': 'c1'},
            {'action': 'disconnectMaster', 'client': 'c2'},
        ],
    },
    {
        'name': 'Query empty table',
        'desc': 'Query for game type with no registrations',
        'steps': _connect_steps() + [
            {'action': 'requestHostList', 'gameType': 'NonExistent', 'allowEmpty': True},
            {'action': 'assertHostCount', 'count': 0},
            {'action': 'disconnectMaster'},
        ],
    },
    {
        'name': 'Multiple registrations',
        'desc': 'Register 2 hosts from different clients, query returns both',
        'steps': [
            {'action': 'startMasterServer'},
            {'action': 'connectMaster', 'client': 'c1'},
            {'action': 'connectMaster', 'client': 'c2'},
            {'action': 'connectMaster', 'client': 'query'},
            {'action': 'registerHost', 'client': 'c1', 'gameType': 'TestGame',
             'name': 'Server1', 'port': 7777},
            {'action': 'registerHost', 'client': 'c2', 'gameType': 'TestGame',
             'name': 'Server2', 'port': 8888},
            {'action': 'requestHostList', 'client': 'query', 'gameType': 'TestGame'},
            {'action': 'assertHostCount', 'count': 2},
            {'action': 'disconnectMaster', 'client': 'c1'},
            {'action': 'disconnectMaster', 'client': 'c2'},
            {'action': 'disconnectMaster', 'client': 'query'},
        ],
    },
    {
        'name': 'Game type isolation',
        'desc': 'Hosts in different game types are isolated',
        'steps': [
            {'action': 'startMasterServer'},
            {'action': 'connectMaster', 'client': 'c1'},
            {'action': 'connectMaster', 'client': 'query'},
            {'action': 'registerHost', 'client': 'c1', 'gameType': 'GameA', 'name': 'ServerA'},
            {'action': 'requestHostList', 'client': 'query', 'gameType': 'GameB',
             'allowEmpty': True, 'resultKey': 'b'},
            {'action': 'assertHostCount', 'resultKey': 'b', 'count': 0},
            {'action': 'requestHostList', 'client': 'query', 'gameType': 'GameA',
             'resultKey': 'a'},
            {'action': 'assertHostCount', 'resultKey': 'a', 'count': 1},
            {'action': 'disconnectMaster', 'client': 'c1'},
            {'action': 'disconnectMaster', 'client': 'query'},
        ],
    },
]


def generate(mode, count=5, rng=None):
    if mode == 'basic':
        return [_make_scenario(p['name'], p['desc'], p['steps']) for p in PRESET_TESTS]
    rng = rng or random.Random()
    tests = []
    for i in range(count):
        game_type = f"Game_{rng.randint(1, 100)}"
        name = f"Server_{rng.randint(1, 100)}"
        port = rng.randint(7000, 9000)
        tests.append(_make_scenario(
            f"random register {i}", f"Register {name} in {game_type}",
            _connect_steps() + [
                {'action': 'registerHost', 'gameType': game_type, 'name': name, 'port': port},
                {'action': 'requestHostList', 'gameType': game_type},
                {'action': 'assertHostCount', 'count': 1},
                {'action': 'assertHostField', 'index': 0, 'field': 'game_name', 'value': name},
                {'action': 'disconnectMaster'},
            ],
            mode='random',
        ))
    return tests
