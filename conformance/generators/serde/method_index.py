import random
import uuid


PRESET_TESTS = [
    (1, 0, 0, "Minimum RID"),
    (7, 0, 24, "RID 7"),
    (22, 0, 84, "RPC_Int in test DLL"),
    (5, 2, 8, "With interface methods"),
    (28, 7, 80, "RPC_Void in Loader assembly"),
    (29, 7, 84, "RPC_Int in Loader assembly"),
]


def generate(mode, count=10, rng=None):
    if mode == 'basic':
        return _generate_basic()
    return _generate_random(count, rng or random.Random())


def _generate_basic():
    return [{
        'testInfo': {
            'testId': str(uuid.uuid4()),
            'testName': f"methodIndex(RID={rid}, iface={iface})",
            'testDescription': desc,
            'category': 'methodIndex',
            'mode': 'basic',
        },
        'input': {'methodRid': rid, 'interfaceMethodCount': iface},
    } for rid, iface, _, desc in PRESET_TESTS]


def _generate_random(count, rng):
    return [{
        'testInfo': {
            'testId': str(uuid.uuid4()),
            'testName': f"methodIndex(random:{i})",
            'testDescription': f"Random RID/iface",
            'category': 'methodIndex',
            'mode': 'random',
        },
        'input': {
            'methodRid': rng.randint(1, 100),
            'interfaceMethodCount': rng.randint(0, 10),
        },
    } for i in range(count)]
