import os
import random
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from ._master_common import random_cell, CELL_TYPES

PRESET_TESTS = [
    ('NUMERIC', 0.0, "Zero double"),
    ('NUMERIC', 42.0, "Integer as double"),
    ('NUMERIC', -1.5, "Negative fractional"),
    ('NUMERIC', None, "Null numeric"),
    ('STRING', "Hello", "Basic string"),
    ('STRING', "", "Empty string (not null)"),
    ('STRING', None, "Null string"),
    ('BINARY', "deadbeef", "4 bytes"),
    ('BINARY', "", "Zero-length binary"),
    ('BINARY', None, "Null binary"),
    ('NUMERIC', 1e100, "Large double"),
    ('STRING', "x" * 200, "Long string"),
]


def generate(mode, count=10, rng=None):
    if mode == 'basic':
        return _generate_basic()
    return _generate_random(count, rng or random.Random())


def _generate_basic():
    tests = []
    for cell_type, value, desc in PRESET_TESTS:
        tests.append({
            'testInfo': {
                'testId': str(uuid.uuid4()),
                'testName': f"cell({cell_type}, {repr(value)[:30]})",
                'testDescription': desc,
                'category': 'cell',
                'mode': 'basic',
            },
            'input': {'cellType': cell_type, 'value': value},
        })
    return tests


def _generate_random(count, rng):
    tests = []
    for i in range(count):
        cell = random_cell(rng)
        tests.append({
            'testInfo': {
                'testId': str(uuid.uuid4()),
                'testName': f"cell(random:{i})",
                'testDescription': f"Random {cell['type']} cell",
                'category': 'cell',
                'mode': 'random',
            },
            'input': {'cellType': cell['type'], 'value': cell['value']},
        })
    return tests
