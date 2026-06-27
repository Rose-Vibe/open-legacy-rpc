import os
import random
import struct
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from protocol.bitstream import BitStream

FIELD_TYPES = {
    'int': 32, 'float': 32, 'bool': 1, 'short': 16, 'char': 8,
    'Vector3': 96, 'Quaternion': 128,
}

PRESET_TESTS = [
    {
        'name': 'Single float', 'desc': 'Minimal state sync',
        'viewId': {'scope': 'scene', 'id': 0}, 'timestamp': 100, 'isFirst': True,
        'fields': [{'type': 'float', 'value': 1.5}],
    },
    {
        'name': 'int + float + Vector3', 'desc': 'Mixed types',
        'viewId': {'scope': 'scene', 'id': 0}, 'timestamp': 200, 'isFirst': True,
        'fields': [
            {'type': 'int', 'value': 42},
            {'type': 'float', 'value': 3.14},
            {'type': 'Vector3', 'value': [1.0, 2.0, 3.0]},
        ],
    },
    {
        'name': 'Quaternion', 'desc': '128-bit field',
        'viewId': {'scope': 'scene', 'id': 1}, 'timestamp': 300, 'isFirst': True,
        'fields': [{'type': 'Quaternion', 'value': [0.0, 0.0, 0.0, 1.0]}],
    },
    {
        'name': 'bool', 'desc': '1-bit field',
        'viewId': {'scope': 'scene', 'id': 0}, 'timestamp': 400, 'isFirst': True,
        'fields': [{'type': 'bool', 'value': True}],
    },
    {
        'name': 'short + char', 'desc': 'Small fields',
        'viewId': {'scope': 'scene', 'id': 0}, 'timestamp': 500, 'isFirst': True,
        'fields': [{'type': 'short', 'value': 1234}, {'type': 'char', 'value': 65}],
    },
    {
        'name': 'isFirst=false', 'desc': 'Non-first flag',
        'viewId': {'scope': 'scene', 'id': 0}, 'timestamp': 600, 'isFirst': False,
        'fields': [{'type': 'float', 'value': 2.5}],
    },
    {
        'name': 'Allocated ViewID', 'desc': 'ViewID scope variant',
        'viewId': {'scope': 'allocated', 'id': 3}, 'timestamp': 700, 'isFirst': True,
        'fields': [{'type': 'int', 'value': 99}],
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
            'testName': f"stateSync: {p['name']}", 'testDescription': p['desc'],
            'category': 'stateSync', 'mode': 'basic',
        },
        'input': {
            'viewId': p['viewId'], 'timestamp': p['timestamp'],
            'isFirst': p['isFirst'], 'fields': p['fields'],
        },
    } for p in PRESET_TESTS]


def _random_field(rng):
    ftype = rng.choice(list(FIELD_TYPES.keys()))
    if ftype == 'int':
        return {'type': 'int', 'value': rng.randint(-10000, 10000)}
    elif ftype == 'float':
        v = struct.unpack('>f', struct.pack('>f', rng.uniform(-100, 100)))[0]
        return {'type': 'float', 'value': v}
    elif ftype == 'bool':
        return {'type': 'bool', 'value': rng.choice([True, False])}
    elif ftype == 'short':
        return {'type': 'short', 'value': rng.randint(0, 65535)}
    elif ftype == 'char':
        return {'type': 'char', 'value': rng.randint(0, 255)}
    elif ftype == 'Vector3':
        vals = [struct.unpack('>f', struct.pack('>f', rng.uniform(-10, 10)))[0] for _ in range(3)]
        return {'type': 'Vector3', 'value': vals}
    elif ftype == 'Quaternion':
        vals = [struct.unpack('>f', struct.pack('>f', rng.uniform(-1, 1)))[0] for _ in range(4)]
        return {'type': 'Quaternion', 'value': vals}


def _generate_random(count, rng):
    tests = []
    for i in range(count):
        num_fields = rng.randint(1, 5)
        tests.append({
            'testInfo': {
                'testId': str(uuid.uuid4()),
                'testName': f"stateSync(random:{i})", 'testDescription': f"Random {num_fields} fields",
                'category': 'stateSync', 'mode': 'random',
            },
            'input': {
                'viewId': {'scope': rng.choice(['scene', 'allocated']), 'id': rng.randint(0, 10)},
                'timestamp': rng.randint(0, 65535),
                'isFirst': rng.choice([True, False]),
                'fields': [_random_field(rng) for _ in range(num_fields)],
            },
        })
    return tests
