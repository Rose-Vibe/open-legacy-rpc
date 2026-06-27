import os
import random
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from ._master_common import random_table_name

PRESET_TESTS = [
    {'name': "Basic remove", 'desc': "Golden path", 'tableName': 'TestGame', 'password': None, 'rowId': 0},
    {'name': "With password", 'desc': "Password encoding", 'tableName': 'Secure', 'password': 'secret', 'rowId': 5},
    {'name': "Row ID 0", 'desc': "Boundary", 'tableName': 'Test', 'password': None, 'rowId': 0},
    {'name': "Row ID max", 'desc': "Max uint32", 'tableName': 'Test', 'password': None, 'rowId': 0xFFFFFFFF},
]


def generate(mode, count=10, rng=None):
    if mode == 'basic':
        return _generate_basic()
    return _generate_random(count, rng or random.Random())


def _generate_basic():
    return [{
        'testInfo': {
            'testId': str(uuid.uuid4()),
            'testName': p['name'], 'testDescription': p['desc'],
            'category': 'removeRow', 'mode': 'basic',
        },
        'input': {'tableName': p['tableName'], 'password': p['password'], 'rowId': p['rowId']},
    } for p in PRESET_TESTS]


def _generate_random(count, rng):
    return [{
        'testInfo': {
            'testId': str(uuid.uuid4()),
            'testName': f"removeRow(random:{i})", 'testDescription': 'Random remove',
            'category': 'removeRow', 'mode': 'random',
        },
        'input': {
            'tableName': random_table_name(rng),
            'password': rng.choice([None, 'pw' + str(rng.randint(0, 9))]),
            'rowId': rng.randint(0, 0xFFFFFFFF),
        },
    } for i in range(count)]
