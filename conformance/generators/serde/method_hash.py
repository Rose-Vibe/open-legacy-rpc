import os
import random
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

KNOWN_METHODS = [
    'RPC_Int', 'RPC_Float', 'RPC_String', 'RPC_Vector3', 'RPC_Quaternion',
    'RPC_Bytes', 'RPC_IntFloatString', 'RPC_Void', 'RPC_Alpha', 'RPC_Beta',
    'RPC_Gamma', 'RPC_NetworkViewID', 'RPC_NetworkPlayer',
    '__RPCNetworkInstantiate',
]


def generate(mode, count=10, rng=None):
    if mode == 'basic':
        return _generate_basic()
    return _generate_random(count, rng or random.Random())


def _generate_basic():
    tests = []
    for method in KNOWN_METHODS:
        tests.append({
            'testInfo': {
                'testId': str(uuid.uuid4()),
                'testName': f"methodHash({method})",
                'testDescription': f"Hash for {method}",
                'category': 'methodHash',
                'mode': 'basic',
            },
            'input': {'methodName': method},
        })
    # Edge cases
    tests.append({
        'testInfo': {
            'testId': str(uuid.uuid4()),
            'testName': "methodHash(X)",
            'testDescription': "Single-char name",
            'category': 'methodHash',
            'mode': 'basic',
        },
        'input': {'methodName': 'X'},
    })
    tests.append({
        'testInfo': {
            'testId': str(uuid.uuid4()),
            'testName': "methodHash(long name)",
            'testDescription': "64-char name",
            'category': 'methodHash',
            'mode': 'basic',
        },
        'input': {'methodName': 'A' * 64},
    })
    return tests


def _generate_random(count, rng):
    tests = []
    for i in range(count):
        length = rng.randint(1, 50)
        name = ''.join(chr(rng.randint(65, 122)) for _ in range(length))
        tests.append({
            'testInfo': {
                'testId': str(uuid.uuid4()),
                'testName': f"methodHash(random:{i})",
                'testDescription': f"Random method name length {length}",
                'category': 'methodHash',
                'mode': 'random',
            },
            'input': {'methodName': name},
        })
    return tests
