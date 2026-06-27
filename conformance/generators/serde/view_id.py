import random
import uuid
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from protocol.unity_protocol import encode_view_id

PRESET_TESTS = [
    ('scene', 0, "Server primary view"),
    ('scene', 1, "Second scene view"),
    ('allocated', 1, "First allocated"),
    ('allocated', 50, "Stride boundary"),
    ('scene', 999, "Large scene ID"),
]


def generate(mode, count=10, rng=None):
    if mode == 'basic':
        return _generate_basic()
    return _generate_random(count, rng or random.Random())


def _generate_basic():
    return [{
        'testInfo': {
            'testId': str(uuid.uuid4()),
            'testName': f"viewId({scope}, {vid})",
            'testDescription': desc,
            'category': 'viewId',
            'mode': 'basic',
        },
        'input': {'scope': scope, 'id': vid},
    } for scope, vid, desc in PRESET_TESTS]


def _generate_random(count, rng):
    return [{
        'testInfo': {
            'testId': str(uuid.uuid4()),
            'testName': f"viewId(random:{i})",
            'testDescription': f"Random ViewID",
            'category': 'viewId',
            'mode': 'random',
        },
        'input': {
            'scope': rng.choice(['scene', 'allocated']),
            'id': rng.randint(0, 1000),
        },
    } for i in range(count)]
