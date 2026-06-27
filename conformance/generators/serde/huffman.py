import random
import uuid
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from protocol.huffman import encode_string_for_wire


def generate(mode, count=10, rng=None):
    if mode == 'basic':
        return _generate_basic()
    return _generate_random(count, rng or random.Random())


PRESET_STRINGS = [
    ("", "Empty string"),
    ("A", "Single character"),
    ("Hello", "Basic mixed-case"),
    (" ", "Space (high frequency, short code)"),
    ("zzz", "Low-frequency character (long codes)"),
    ("Hello, World!", "Punctuation + space"),
    ("\x01", "Byte 0x01 (rare, near-max code length)"),
    ("The quick brown fox jumps over the lazy dog",
     "Pangram — covers many letters"),
    ("aaaaaa", "Repeated high-frequency char"),
    ("0123456789", "Digits"),
]


def _generate_basic():
    tests = []
    for s, desc in PRESET_STRINGS:
        tests.append(_make_test(s, desc, 'basic'))

    # Full 256-byte round-trip
    all_bytes = ''.join(chr(i) for i in range(256))
    tests.append(_make_test(all_bytes, "All 256 byte values", 'basic'))
    return tests


def _generate_random(count, rng):
    tests = []
    for i in range(count):
        length = rng.randint(0, 200)
        # ASCII printable + some control chars
        chars = [chr(rng.randint(0, 127)) for _ in range(length)]
        s = ''.join(chars)
        tests.append(_make_test(s, f"Random ASCII string length {length}", 'random'))
    return tests


def _make_test(s, desc, mode):
    # Input uses hex encoding for the string bytes to handle non-printable chars
    return {
        'testInfo': {
            'testId': str(uuid.uuid4()),
            'testName': f"huffmanEncode({repr(s)[:40]})",
            'testDescription': desc,
            'category': 'huffman',
            'mode': mode,
        },
        'input': {'stringHex': s.encode('latin-1').hex()},
    }
