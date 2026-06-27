import random
import uuid

PRESET_TESTS = [
    ('scene', 0, 0, "Zero"),
    ('scene', 1, 4, "1 << 2"),
    ('allocated', 1, 16448, "0x4000 | (1 << 6)"),
    ('scene', 100, 400, "Large scene"),
]


def generate(mode, count=10, rng=None):
    if mode == 'basic':
        return _generate_basic()
    return _generate_random(count, rng or random.Random())


def _generate_basic():
    return [{
        'testInfo': {
            'testId': str(uuid.uuid4()),
            'testName': f"viewIdParam({scope}, {vid})",
            'testDescription': desc,
            'category': 'viewIdParam',
            'mode': 'basic',
        },
        'input': {'scope': scope, 'id': vid},
    } for scope, vid, _, desc in PRESET_TESTS]


def _generate_random(count, rng):
    return [{
        'testInfo': {
            'testId': str(uuid.uuid4()),
            'testName': f"viewIdParam(random:{i})",
            'testDescription': "Random 16-bit ViewID",
            'category': 'viewIdParam',
            'mode': 'random',
        },
        'input': {
            'scope': rng.choice(['scene', 'allocated']),
            'id': rng.randint(0, 200),
        },
    } for i in range(count)]
