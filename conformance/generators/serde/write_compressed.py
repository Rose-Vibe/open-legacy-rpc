import random
import uuid


PRESET_VALUES = [
    (0, "Zero — maximum compression"),
    (1, "Smallest nonzero"),
    (127, "Fits in 7 bits (nibble boundary)"),
    (128, "Crosses nibble boundary"),
    (255, "Full single byte"),
    (256, "Two bytes, second byte is 0x01"),
    (65535, "0xFFFF, two full bytes"),
    (65536, "Three bytes"),
    (16777215, "0xFFFFFF, three full bytes"),
    (16777216, "Four bytes"),
    (4294967295, "0xFFFFFFFF, maximum uint32"),
]


def generate(mode, count=10, rng=None):
    if mode == 'basic':
        return _generate_basic()
    elif mode == 'random':
        return _generate_random(count, rng or random.Random())
    raise ValueError(f"Unknown mode: {mode}")


def _generate_basic():
    tests = []
    for value, desc in PRESET_VALUES:
        tests.append({
            'testInfo': {
                'testId': str(uuid.uuid4()),
                'testName': f"writeCompressed({value})",
                'testDescription': desc,
                'category': 'writeCompressed',
                'mode': 'basic',
            },
            'input': {'value': value},
        })
    return tests


def _generate_random(count, rng):
    tests = []
    for i in range(count):
        value = rng.randint(0, 0xFFFFFFFF)
        tests.append({
            'testInfo': {
                'testId': str(uuid.uuid4()),
                'testName': f"writeCompressed(random:{i})",
                'testDescription': f"Random uint32 value {value}",
                'category': 'writeCompressed',
                'mode': 'random',
            },
            'input': {'value': value},
        })
    return tests
