import random
import uuid


PRESET_TESTS = [
    {'methodName': 'RPC_Int', 'methodIndex': 0x60, 'desc': 'RPC_Int with Unity-style index'},
    {'methodName': 'RPC_Float', 'methodIndex': 4, 'desc': 'RPC_Float low index'},
    {'methodName': 'RPC_Void', 'methodIndex': 2, 'desc': 'RPC_Void even index'},
    {'methodName': 'RPC_String', 'methodIndex': 126, 'desc': 'Near-max 7-bit index'},
    {'methodName': 'RPC_Alpha', 'methodIndex': 0, 'desc': 'Zero index'},
    {'methodName': 'RPC_Int', 'methodIndex': 127, 'desc': 'Max 7-bit index'},
]

METHODS = ['RPC_Int', 'RPC_Float', 'RPC_String', 'RPC_Void', 'RPC_Alpha',
           'RPC_Bytes', 'RPC_Vector3', 'RPC_Quaternion']


def generate(mode, count=10, rng=None):
    if mode == 'basic':
        return _generate_basic()
    return _generate_random(count, rng or random.Random())


def _generate_basic():
    tests = []
    for preset in PRESET_TESTS:
        tests.append({
            'testInfo': {
                'testId': str(uuid.uuid4()),
                'testName': f"batchIndexEncode: {preset['desc']}",
                'testDescription': preset['desc'],
                'category': 'batchIndexEncode',
                'mode': 'basic',
            },
            'input': {
                'methodName': preset['methodName'],
                'methodIndex': preset['methodIndex'],
            },
        })
    return tests


def _generate_random(count, rng):
    tests = []
    for i in range(count):
        tests.append({
            'testInfo': {
                'testId': str(uuid.uuid4()),
                'testName': f"batchIndexEncode(random:{i})",
                'testDescription': f"Random BATCH encode {i}",
                'category': 'batchIndexEncode',
                'mode': 'random',
            },
            'input': {
                'methodName': rng.choice(METHODS),
                'methodIndex': rng.randint(0, 127),
            },
        })
    return tests
