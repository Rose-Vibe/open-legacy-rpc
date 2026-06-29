import os
import random
import struct
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

PRESET_TESTS = [
    {
        'name': 'All dirty (isFirst)', 'desc': 'Full initial send',
        'viewId': {'scope': 'scene', 'id': 0}, 'timestamp': 100, 'isFirst': True,
        'fieldWidths': [32, 32, 32],
        'fieldValues': [42, 1065353216, 100],  # int, float-as-bits, int
        'prevValues': [0, 0, 0],
    },
    {
        'name': 'No dirty', 'desc': 'Minimal delta — nothing changed',
        'viewId': {'scope': 'scene', 'id': 0}, 'timestamp': 200, 'isFirst': False,
        'fieldWidths': [32, 32],
        'fieldValues': [42, 100],
        'prevValues': [42, 100],
    },
    {
        'name': 'One of three dirty', 'desc': 'Selective dirty flags',
        'viewId': {'scope': 'scene', 'id': 0}, 'timestamp': 300, 'isFirst': False,
        'fieldWidths': [32, 32, 32],
        'fieldValues': [42, 999, 100],
        'prevValues': [42, 0, 100],
    },
    {
        'name': 'Single field', 'desc': 'Minimal field count',
        'viewId': {'scope': 'scene', 'id': 1}, 'timestamp': 400, 'isFirst': True,
        'fieldWidths': [32],
        'fieldValues': [12345],
        'prevValues': [0],
    },
]


def generate(mode, count=10, rng=None):
    if mode == 'basic':
        return _generate_basic()
    return _generate_random(count, rng or random.Random())


def _generate_basic():
    return [{
        'testInfo': {
            'testId': str(uuid.uuid4()),
            'testName': f"deltaSync: {p['name']}", 'testDescription': p['desc'],
            'category': 'deltaStateSync', 'mode': 'basic',
        },
        'input': {
            'viewId': p['viewId'], 'timestamp': p['timestamp'], 'isFirst': p['isFirst'],
            'fieldWidths': p['fieldWidths'],
            'fieldValues': p['fieldValues'],
            'prevValues': p['prevValues'],
        },
    } for p in PRESET_TESTS]


def _generate_random(count, rng):
    tests = []
    for i in range(count):
        num_fields = rng.randint(1, 6)
        widths = [32] * num_fields
        prev = [rng.randint(0, 0xFFFFFFFF) for _ in range(num_fields)]
        cur = list(prev)
        for j in range(num_fields):
            if rng.random() > 0.5:
                cur[j] = rng.randint(0, 0xFFFFFFFF)
        tests.append({
            'testInfo': {
                'testId': str(uuid.uuid4()),
                'testName': f"deltaSync(random:{i})", 'testDescription': f"Random {num_fields} fields",
                'category': 'deltaStateSync', 'mode': 'random',
            },
            'input': {
                'viewId': {'scope': 'scene', 'id': rng.randint(0, 5)},
                'timestamp': rng.randint(0, 0xFFFFFFFF), 'isFirst': rng.choice([True, False]),
                'fieldWidths': widths, 'fieldValues': cur, 'prevValues': prev,
            },
        })
    return tests
