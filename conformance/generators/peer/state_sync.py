"""State sync peer test scenarios."""

import random
import struct
import uuid


def _make_scenario(name, desc, steps, mode='basic'):
    return {
        'testInfo': {
            'testId': str(uuid.uuid4()),
            'testName': f"stateSync: {name}",
            'testDescription': desc,
            'category': 'stateSync',
            'mode': mode,
        },
        'steps': steps,
    }


def _connect_steps():
    return [
        {'action': 'startServer'},
        {'action': 'connect'},
        {'action': 'assertConnected'},
    ]


def _disconnect_steps():
    return [{'action': 'disconnect'}]


PRESET_TESTS = [
    {
        'name': 'Int sync',
        'desc': 'Server sends int state sync, client receives it',
        'steps': _connect_steps() + [
            {'action': 'sendStateSync', 'from': 'server', 'viewId': 1,
             'fields': [{'type': 'int', 'value': 42}]},
            {'action': 'expectStateSync', 'on': 'client', 'viewId': 1,
             'fields': [{'type': 'int', 'value': 42}]},
        ] + _disconnect_steps(),
    },
    {
        'name': 'Float sync',
        'desc': 'Server sends float state sync',
        'steps': _connect_steps() + [
            {'action': 'sendStateSync', 'from': 'server', 'viewId': 1,
             'fields': [{'type': 'float', 'value': 3.140000104904175}]},
            {'action': 'expectStateSync', 'on': 'client', 'viewId': 1,
             'fields': [{'type': 'float', 'value': 3.140000104904175}]},
        ] + _disconnect_steps(),
    },
    {
        'name': 'Multi-field sync',
        'desc': 'Server sends int + float + Vector3',
        'steps': _connect_steps() + [
            {'action': 'sendStateSync', 'from': 'server', 'viewId': 1,
             'fields': [
                 {'type': 'int', 'value': 100},
                 {'type': 'float', 'value': 2.5},
                 {'type': 'Vector3', 'value': [1.0, 2.0, 3.0]},
             ]},
            {'action': 'expectStateSync', 'on': 'client', 'viewId': 1,
             'fields': [
                 {'type': 'int', 'value': 100},
                 {'type': 'float', 'value': 2.5},
                 {'type': 'Vector3', 'value': [1.0, 2.0, 3.0]},
             ]},
        ] + _disconnect_steps(),
    },
    {
        'name': 'Multiple views',
        'desc': 'Send to view 1 and view 2, client receives both',
        'steps': _connect_steps() + [
            {'action': 'sendStateSync', 'from': 'server', 'viewId': 1,
             'fields': [{'type': 'int', 'value': 10}]},
            {'action': 'expectStateSync', 'on': 'client', 'viewId': 1,
             'fields': [{'type': 'int', 'value': 10}]},
            {'action': 'sendStateSync', 'from': 'server', 'viewId': 2,
             'fields': [{'type': 'int', 'value': 20}]},
            {'action': 'expectStateSync', 'on': 'client', 'viewId': 2,
             'fields': [{'type': 'int', 'value': 20}]},
        ] + _disconnect_steps(),
    },
    {
        'name': 'Sequential updates',
        'desc': 'Three state sync updates in sequence',
        'steps': _connect_steps() + [
            {'action': 'sendStateSync', 'from': 'server', 'viewId': 1,
             'fields': [{'type': 'int', 'value': i}]}
            for i in [1, 2, 3]
        ] + [
            {'action': 'sleep', 'duration': 0.3},
            {'action': 'poll', 'duration': 0.3},
        ] + _disconnect_steps(),
    },
]


def generate(mode, count=5, rng=None):
    if mode == 'basic':
        return [_make_scenario(p['name'], p['desc'], p['steps']) for p in PRESET_TESTS]
    rng = rng or random.Random()
    tests = []
    for i in range(count):
        num_fields = rng.randint(1, 3)
        fields = []
        for _ in range(num_fields):
            ftype = rng.choice(['int', 'float'])
            if ftype == 'int':
                fields.append({'type': 'int', 'value': rng.randint(-10000, 10000)})
            else:
                v = struct.unpack('>f', struct.pack('>f', rng.uniform(-100, 100)))[0]
                fields.append({'type': 'float', 'value': v})
        view_id = rng.randint(1, 5)
        tests.append(_make_scenario(
            f"random sync {i}", f"Random {num_fields}-field sync to view {view_id}",
            _connect_steps() + [
                {'action': 'sendStateSync', 'from': 'server', 'viewId': view_id,
                 'fields': fields},
                {'action': 'expectStateSync', 'on': 'client', 'viewId': view_id,
                 'fields': fields},
            ] + _disconnect_steps(),
            mode='random',
        ))
    return tests
