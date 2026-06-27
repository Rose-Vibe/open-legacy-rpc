import os
import random
import struct
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

RPC_MODES = ['Server', 'Others', 'All', 'OthersBuffered', 'AllBuffered']

PRESET_TESTS = [
    {'name': 'RPC_Int', 'params': [{'type': 'int', 'value': 42}], 'mode': 'Others', 'desc': 'Single int param'},
    {'name': 'RPC_Float', 'params': [{'type': 'float', 'value': 3.14}], 'mode': 'Others', 'desc': 'Single float'},
    {'name': 'RPC_String', 'params': [{'type': 'string', 'value': 'hello'}], 'mode': 'Others', 'desc': 'Huffman string param'},
    {'name': 'RPC_Vector3', 'params': [{'type': 'Vector3', 'value': [1.0, 2.0, 3.0]}], 'mode': 'Others', 'desc': 'Vector3 param'},
    {'name': 'RPC_Quaternion', 'params': [{'type': 'Quaternion', 'value': [0.0, 0.0, 0.0, 1.0]}], 'mode': 'Others', 'desc': 'Quaternion param'},
    {'name': 'RPC_Bytes', 'params': [{'type': 'bytes', 'value': 'deadbeef'}], 'mode': 'Others', 'desc': 'byte[] param'},
    {'name': 'RPC_IntFloatString', 'params': [{'type': 'int', 'value': 1}, {'type': 'float', 'value': 2.0}, {'type': 'string', 'value': 'hi'}], 'mode': 'Others', 'desc': 'Multi-param'},
    {'name': 'RPC_Void', 'params': [], 'mode': 'Others', 'desc': 'No params'},
    {'name': 'RPC_Int', 'params': [{'type': 'int', 'value': 99}], 'mode': 'Server', 'desc': 'RPCMode.Server'},
    {'name': 'RPC_Int', 'params': [{'type': 'int', 'value': 0}], 'mode': 'AllBuffered', 'desc': 'Buffered mode'},
    {'name': 'RPC_NetworkViewID', 'params': [{'type': 'NetworkViewID', 'value': 4}], 'mode': 'Others', 'desc': 'ViewID param'},
    {'name': 'RPC_NetworkPlayer', 'params': [{'type': 'NetworkPlayer', 'value': 0}], 'mode': 'Others', 'desc': 'Player index param'},
]


def generate(mode, count=10, rng=None):
    if mode == 'basic':
        return _generate_basic()
    return _generate_random(count, rng or random.Random())


def _generate_basic():
    tests = []
    for i, preset in enumerate(PRESET_TESTS):
        tests.append({
            'testInfo': {
                'testId': str(uuid.uuid4()),
                'testName': f"rpcEncode: {preset['desc']}",
                'testDescription': preset['desc'],
                'category': 'rpcEncode',
                'mode': 'basic',
            },
            'input': {
                'methodName': preset['name'],
                'viewId': {'scope': 'scene', 'id': 0},
                'rpcCounter': i,
                'rpcMode': preset['mode'],
                'params': preset['params'],
            },
        })
    return tests


METHODS_WITH_SIGS = {
    'RPC_Int': [('int', (-100000, 100000))],
    'RPC_Float': [('float', None)],
    'RPC_String': [('string', None)],
    'RPC_Void': [],
    'RPC_Bytes': [('bytes', None)],
    'RPC_Vector3': [('Vector3', None)],
    'RPC_Quaternion': [('Quaternion', None)],
}


def _random_param(rng, ptype):
    if ptype == 'int':
        return {'type': 'int', 'value': rng.randint(-100000, 100000)}
    elif ptype == 'float':
        v = struct.unpack('>f', struct.pack('>f', rng.uniform(-1000, 1000)))[0]
        return {'type': 'float', 'value': v}
    elif ptype == 'string':
        length = rng.randint(0, 30)
        s = ''.join(chr(rng.randint(32, 126)) for _ in range(length))
        return {'type': 'string', 'value': s}
    elif ptype == 'bytes':
        length = rng.randint(0, 50)
        return {'type': 'bytes', 'value': bytes(rng.randint(0, 255) for _ in range(length)).hex()}
    elif ptype == 'Vector3':
        vals = [struct.unpack('>f', struct.pack('>f', rng.uniform(-100, 100)))[0] for _ in range(3)]
        return {'type': 'Vector3', 'value': vals}
    elif ptype == 'Quaternion':
        vals = [struct.unpack('>f', struct.pack('>f', rng.uniform(-1, 1)))[0] for _ in range(4)]
        return {'type': 'Quaternion', 'value': vals}
    elif ptype == 'NetworkViewID':
        return {'type': 'NetworkViewID', 'value': rng.choice([0, 4, 8, 0x4040])}
    elif ptype == 'NetworkPlayer':
        return {'type': 'NetworkPlayer', 'value': rng.randint(0, 10)}
    return {'type': ptype, 'value': 0}


def _generate_random(count, rng):
    tests = []
    method_names = list(METHODS_WITH_SIGS.keys())
    for i in range(count):
        method = rng.choice(method_names)
        sig = METHODS_WITH_SIGS[method]
        params = [_random_param(rng, ptype) for ptype, _ in sig]
        tests.append({
            'testInfo': {
                'testId': str(uuid.uuid4()),
                'testName': f"rpcEncode(random:{i})",
                'testDescription': f"Random {method} RPC",
                'category': 'rpcEncode',
                'mode': 'random',
            },
            'input': {
                'methodName': method,
                'viewId': {'scope': rng.choice(['scene', 'allocated']),
                           'id': rng.randint(0, 10)},
                'rpcCounter': rng.randint(0, 127),
                'rpcMode': rng.choice(RPC_MODES),
                'params': params,
            },
        })
    return tests
