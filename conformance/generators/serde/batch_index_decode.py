import os
import random
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from protocol.unity_protocol import encode_batch_index, register_method_names

register_method_names([
    'RPC_Int', 'RPC_Float', 'RPC_String', 'RPC_Void', 'RPC_Alpha',
    'RPC_Bytes', 'RPC_Vector3', 'RPC_Quaternion',
])

PRESET_TESTS = [
    {'methodName': 'RPC_Int', 'methodIndex': 0x60, 'desc': 'RPC_Int with Unity-style index'},
    {'methodName': 'RPC_Float', 'methodIndex': 4, 'desc': 'RPC_Float low index'},
    {'methodName': 'RPC_Void', 'methodIndex': 8, 'desc': 'RPC_Void stride-4 index'},
    {'methodName': 'RPC_String', 'methodIndex': 124, 'desc': 'Near-max 5-bit index'},
    {'methodName': 'RPC_Alpha', 'methodIndex': 0, 'desc': 'Zero index'},
    {'methodName': 'RPC_Int', 'methodIndex': 76, 'desc': 'Mid-range index'},
]

METHODS = ['RPC_Int', 'RPC_Float', 'RPC_String', 'RPC_Void', 'RPC_Alpha',
           'RPC_Bytes', 'RPC_Vector3', 'RPC_Quaternion']


def generate(mode, count=10, rng=None):
    if mode == 'basic':
        return _generate_basic()
    return _generate_random(count, rng or random.Random())


def _make_test(method_name, method_index, desc, mode):
    data, bit_length = encode_batch_index(method_name, method_index)
    return {
        'testInfo': {
            'testId': str(uuid.uuid4()),
            'testName': f"batchIndexDecode: {desc}",
            'testDescription': desc,
            'category': 'batchIndexDecode',
            'mode': mode,
        },
        'input': {
            'dataHex': data.hex(),
            'bitLength': bit_length,
        },
        'expected': {
            'methodName': method_name,
            'methodIndex': method_index,
        },
    }


def _generate_basic():
    return [_make_test(p['methodName'], p['methodIndex'], p['desc'], 'basic')
            for p in PRESET_TESTS]


def _generate_random(count, rng):
    tests = []
    for i in range(count):
        method = rng.choice(METHODS)
        index = rng.randint(0, 31) * 4
        tests.append(_make_test(method, index,
                                f"Random BATCH decode {i}", 'random'))
    return tests
