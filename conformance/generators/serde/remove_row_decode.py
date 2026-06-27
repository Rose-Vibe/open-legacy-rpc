import os
import random
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from protocol.master_serialization import encode_remove_row
from .remove_row import PRESET_TESTS
from ._master_common import random_table_name


def generate(mode, count=10, rng=None):
    if mode == 'basic':
        return _generate_basic()
    return _generate_random(count, rng or random.Random())


def _generate_basic():
    tests = []
    for p in PRESET_TESTS:
        data = encode_remove_row(p['tableName'], p['rowId'], password=p['password'])
        tests.append({
            'testInfo': {
                'testId': str(uuid.uuid4()),
                'testName': f"removeRowDecode: {p['name']}", 'testDescription': p['desc'],
                'category': 'removeRowDecode', 'mode': 'basic',
            },
            'input': {'dataHex': data.hex()},
        })
    return tests


def _generate_random(count, rng):
    tests = []
    for i in range(count):
        data = encode_remove_row(
            random_table_name(rng), rng.randint(0, 0xFFFFFFFF),
            password=rng.choice([None, 'pw' + str(rng.randint(0, 9))]),
        )
        tests.append({
            'testInfo': {
                'testId': str(uuid.uuid4()),
                'testName': f"removeRowDecode(random:{i})", 'testDescription': 'Random decode',
                'category': 'removeRowDecode', 'mode': 'random',
            },
            'input': {'dataHex': data.hex()},
        })
    return tests
