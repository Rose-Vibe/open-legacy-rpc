"""RPC peer test scenarios."""

import random
import struct
import uuid


def _make_scenario(name, desc, steps, mode='basic'):
    return {
        'testInfo': {
            'testId': str(uuid.uuid4()),
            'testName': f"rpc: {name}",
            'testDescription': desc,
            'category': 'rpc',
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
        'name': 'Int RPC',
        'desc': 'Client sends int RPC, server receives it',
        'steps': _connect_steps() + [
            {'action': 'sendRpc', 'from': 'client', 'methodName': 'RPC_Int',
             'params': [{'type': 'int', 'value': 42}]},
            {'action': 'expectRpc', 'on': 'server', 'methodName': 'RPC_Int',
             'params': [{'type': 'int', 'value': 42}]},
        ] + _disconnect_steps(),
    },
    {
        'name': 'Float RPC',
        'desc': 'Client sends float RPC, server receives it',
        'steps': _connect_steps() + [
            {'action': 'sendRpc', 'from': 'client', 'methodName': 'RPC_Float',
             'params': [{'type': 'float', 'value': 3.140000104904175}]},
            {'action': 'expectRpc', 'on': 'server', 'methodName': 'RPC_Float',
             'params': [{'type': 'float', 'value': 3.140000104904175}]},
        ] + _disconnect_steps(),
    },
    {
        'name': 'String RPC',
        'desc': 'Client sends string RPC, server receives it',
        'steps': _connect_steps() + [
            {'action': 'sendRpc', 'from': 'client', 'methodName': 'RPC_String',
             'params': [{'type': 'string', 'value': 'hello'}]},
            {'action': 'expectRpc', 'on': 'server', 'methodName': 'RPC_String',
             'params': [{'type': 'string', 'value': 'hello'}]},
        ] + _disconnect_steps(),
    },
    {
        'name': 'Bytes RPC',
        'desc': 'Client sends byte[] RPC, server receives it',
        'steps': _connect_steps() + [
            {'action': 'sendRpc', 'from': 'client', 'methodName': 'RPC_Bytes',
             'params': [{'type': 'bytes', 'value': 'deadbeef'}]},
            {'action': 'expectRpc', 'on': 'server', 'methodName': 'RPC_Bytes',
             'params': [{'type': 'bytes', 'value': 'deadbeef'}]},
        ] + _disconnect_steps(),
    },
    {
        'name': 'Vector3 RPC',
        'desc': 'Client sends Vector3 RPC',
        'steps': _connect_steps() + [
            {'action': 'sendRpc', 'from': 'client', 'methodName': 'RPC_Vector3',
             'params': [{'type': 'Vector3', 'value': [1.0, 2.0, 3.0]}]},
            {'action': 'expectRpc', 'on': 'server', 'methodName': 'RPC_Vector3',
             'params': [{'type': 'Vector3', 'value': [1.0, 2.0, 3.0]}]},
        ] + _disconnect_steps(),
    },
    {
        'name': 'Quaternion RPC',
        'desc': 'Client sends Quaternion RPC',
        'steps': _connect_steps() + [
            {'action': 'sendRpc', 'from': 'client', 'methodName': 'RPC_Quaternion',
             'params': [{'type': 'Quaternion', 'value': [0.0, 0.0, 0.0, 1.0]}]},
            {'action': 'expectRpc', 'on': 'server', 'methodName': 'RPC_Quaternion',
             'params': [{'type': 'Quaternion', 'value': [0.0, 0.0, 0.0, 1.0]}]},
        ] + _disconnect_steps(),
    },
    {
        'name': 'Multi-param RPC',
        'desc': 'Client sends int+float+string RPC',
        'steps': _connect_steps() + [
            {'action': 'sendRpc', 'from': 'client', 'methodName': 'RPC_IntFloatString',
             'params': [
                 {'type': 'int', 'value': 1},
                 {'type': 'float', 'value': 2.0},
                 {'type': 'string', 'value': 'hi'},
             ]},
            {'action': 'expectRpc', 'on': 'server', 'methodName': 'RPC_IntFloatString',
             'params': [
                 {'type': 'int', 'value': 1},
                 {'type': 'float', 'value': 2.0},
                 {'type': 'string', 'value': 'hi'},
             ]},
        ] + _disconnect_steps(),
    },
    {
        'name': 'Void RPC',
        'desc': 'Client sends parameterless RPC',
        'steps': _connect_steps() + [
            {'action': 'sendRpc', 'from': 'client', 'methodName': 'RPC_Void', 'params': []},
            {'action': 'expectRpc', 'on': 'server', 'methodName': 'RPC_Void', 'params': []},
        ] + _disconnect_steps(),
    },
    {
        'name': 'Bidirectional RPC',
        'desc': 'Client sends to server, then server sends back',
        'steps': _connect_steps() + [
            {'action': 'sendRpc', 'from': 'client', 'methodName': 'RPC_Int',
             'params': [{'type': 'int', 'value': 42}]},
            {'action': 'expectRpc', 'on': 'server', 'methodName': 'RPC_Int',
             'params': [{'type': 'int', 'value': 42}]},
            {'action': 'sendRpc', 'from': 'server', 'methodName': 'RPC_Int',
             'params': [{'type': 'int', 'value': 99}]},
            {'action': 'expectRpc', 'on': 'default', 'methodName': 'RPC_Int',
             'params': [{'type': 'int', 'value': 99}]},
        ] + _disconnect_steps(),
    },
    {
        'name': 'RPCMode.Server',
        'desc': 'RPC sent with Server mode',
        'steps': _connect_steps() + [
            {'action': 'sendRpc', 'from': 'client', 'methodName': 'RPC_Int',
             'params': [{'type': 'int', 'value': 77}], 'mode': 'Server'},
            {'action': 'expectRpc', 'on': 'server', 'methodName': 'RPC_Int',
             'params': [{'type': 'int', 'value': 77}]},
        ] + _disconnect_steps(),
    },
    {
        'name': 'Multiple RPCs sequence',
        'desc': 'Send 5 RPCs in sequence, all received in order',
        'steps': _connect_steps() + [
            {'action': 'sendRpc', 'from': 'client', 'methodName': 'RPC_Int',
             'params': [{'type': 'int', 'value': i}]}
            for i in range(5)
        ] + [
            {'action': 'sleep', 'duration': 0.5},
        ] + [
            {'action': 'expectRpc', 'on': 'server', 'methodName': 'RPC_Int',
             'params': [{'type': 'int', 'value': 0}]},
        ] + _disconnect_steps(),
    },
]

METHODS_WITH_SIGS = {
    'RPC_Int': [('int', (-100000, 100000))],
    'RPC_Float': [('float', None)],
    'RPC_String': [('string', None)],
    'RPC_Void': [],
}


def _random_param(rng, ptype):
    if ptype == 'int':
        return {'type': 'int', 'value': rng.randint(-100000, 100000)}
    elif ptype == 'float':
        v = struct.unpack('>f', struct.pack('>f', rng.uniform(-1000, 1000)))[0]
        return {'type': 'float', 'value': v}
    elif ptype == 'string':
        length = rng.randint(0, 20)
        s = ''.join(chr(rng.randint(32, 126)) for _ in range(length))
        return {'type': 'string', 'value': s}
    return {'type': ptype, 'value': 0}


def generate(mode, count=5, rng=None):
    if mode == 'basic':
        return [_make_scenario(p['name'], p['desc'], p['steps']) for p in PRESET_TESTS]
    rng = rng or random.Random()
    tests = []
    methods = list(METHODS_WITH_SIGS.keys())
    for i in range(count):
        method = rng.choice(methods)
        sig = METHODS_WITH_SIGS[method]
        params = [_random_param(rng, pt) for pt, _ in sig]
        tests.append(_make_scenario(
            f"random RPC {i}", f"Random {method} with params",
            _connect_steps() + [
                {'action': 'sendRpc', 'from': 'client', 'methodName': method, 'params': params},
                {'action': 'expectRpc', 'on': 'server', 'methodName': method, 'params': params},
            ] + _disconnect_steps(),
            mode='random',
        ))
    return tests
