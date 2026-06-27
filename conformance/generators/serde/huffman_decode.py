import random
import uuid
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from protocol.huffman import encode_string_for_wire


PRESET_STRINGS = [
    ("", "Empty string"),
    ("A", "Single character"),
    ("Hello", "Basic mixed-case"),
    (" ", "Space"),
    ("zzz", "Low-frequency character"),
    ("Hello, World!", "Punctuation + space"),
    ("\x01", "Byte 0x01"),
    ("The quick brown fox jumps over the lazy dog", "Pangram"),
]


def _encode(s):
    if s == '':
        return '', 0
    bits = encode_string_for_wire(s)
    data = int(bits, 2).to_bytes((len(bits) + 7) // 8, 'big')
    return data.hex(), len(bits)


def generate(mode, count=10, rng=None):
    if mode == 'basic':
        return _generate_basic()
    return _generate_random(count, rng or random.Random())


def _generate_basic():
    tests = []
    for s, desc in PRESET_STRINGS:
        data_hex, bit_length = _encode(s)
        tests.append({
            'testInfo': {
                'testId': str(uuid.uuid4()),
                'testName': f"huffmanDecode → {repr(s)[:30]}",
                'testDescription': desc,
                'category': 'huffmanDecode',
                'mode': 'basic',
            },
            'input': {'dataHex': data_hex, 'bitLength': bit_length},
        })
    return tests


def _generate_random(count, rng):
    tests = []
    for i in range(count):
        length = rng.randint(0, 100)
        chars = [chr(rng.randint(0, 127)) for _ in range(length)]
        s = ''.join(chars)
        data_hex, bit_length = _encode(s)
        tests.append({
            'testInfo': {
                'testId': str(uuid.uuid4()),
                'testName': f"huffmanDecode(random:{i})",
                'testDescription': f"Random decode, length {length}",
                'category': 'huffmanDecode',
                'mode': 'random',
            },
            'input': {'dataHex': data_hex, 'bitLength': bit_length},
        })
    return tests
