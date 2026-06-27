import os
import random
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from protocol.bitstream import BitStream


PRESET_VALUES = [
    (0, "Zero — maximum compression"),
    (1, "Smallest nonzero"),
    (127, "Fits in 7 bits (nibble boundary)"),
    (128, "Crosses nibble boundary"),
    (255, "Full single byte"),
    (256, "Two bytes"),
    (65535, "0xFFFF"),
    (65536, "Three bytes"),
    (16777215, "0xFFFFFF"),
    (16777216, "Four bytes"),
    (4294967295, "0xFFFFFFFF, maximum uint32"),
]


def _encode_value(value):
    bs = BitStream()
    bs.write_compressed_u32(value)
    return bs.to_bytes().hex(), bs.bit_length


def generate(mode, count=10, rng=None):
    if mode == 'basic':
        return _generate_basic()
    elif mode == 'random':
        return _generate_random(count, rng or random.Random())
    raise ValueError(f"Unknown mode: {mode}")


def _generate_basic():
    tests = []
    for value, desc in PRESET_VALUES:
        data_hex, bit_length = _encode_value(value)
        tests.append({
            'testInfo': {
                'testId': str(uuid.uuid4()),
                'testName': f"readCompressed → {value}",
                'testDescription': desc,
                'category': 'readCompressed',
                'mode': 'basic',
            },
            'input': {'dataHex': data_hex, 'bitLength': bit_length},
        })
    return tests


def _generate_random(count, rng):
    tests = []
    for i in range(count):
        value = rng.randint(0, 0xFFFFFFFF)
        data_hex, bit_length = _encode_value(value)
        tests.append({
            'testInfo': {
                'testId': str(uuid.uuid4()),
                'testName': f"readCompressed(random:{i})",
                'testDescription': f"Random uint32 decode → {value}",
                'category': 'readCompressed',
                'mode': 'random',
            },
            'input': {'dataHex': data_hex, 'bitLength': bit_length},
        })
    return tests
