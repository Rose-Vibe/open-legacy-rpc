import os
import random
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from protocol.bitstream import BitStream
from protocol.master_serialization import write_cell, NUMERIC, STRING, BINARY
from ._master_common import random_cell

TYPE_INT = {'NUMERIC': NUMERIC, 'STRING': STRING, 'BINARY': BINARY}

PRESET_TESTS = [
    ('NUMERIC', 0.0, "Zero double"),
    ('NUMERIC', 42.0, "Integer as double"),
    ('NUMERIC', -1.5, "Negative fractional"),
    ('NUMERIC', None, "Null numeric"),
    ('STRING', "Hello", "Basic string"),
    ('STRING', "", "Empty string"),
    ('STRING', None, "Null string"),
    ('BINARY', b'\xde\xad\xbe\xef', "4 bytes"),
    ('BINARY', b'', "Zero-length binary"),
    ('BINARY', None, "Null binary"),
]


def _encode_cell(cell_type, value):
    bs = BitStream()
    if cell_type == 'BINARY' and isinstance(value, str):
        value = bytes.fromhex(value) if value else b''
    write_cell(bs, value, TYPE_INT[cell_type])
    return bs.to_bytes().hex(), bs.bit_length


def generate(mode, count=10, rng=None):
    if mode == 'basic':
        return _generate_basic()
    return _generate_random(count, rng or random.Random())


def _generate_basic():
    tests = []
    for cell_type, value, desc in PRESET_TESTS:
        data_hex, bit_length = _encode_cell(cell_type, value)
        tests.append({
            'testInfo': {
                'testId': str(uuid.uuid4()),
                'testName': f"cellDecode({cell_type})",
                'testDescription': desc,
                'category': 'cellDecode',
                'mode': 'basic',
            },
            'input': {'cellType': cell_type, 'dataHex': data_hex, 'bitLength': bit_length},
        })
    return tests


def _generate_random(count, rng):
    tests = []
    for i in range(count):
        cell = random_cell(rng)
        val = cell['value']
        if cell['type'] == 'BINARY' and isinstance(val, str):
            val = bytes.fromhex(val)
        data_hex, bit_length = _encode_cell(cell['type'], val)
        tests.append({
            'testInfo': {
                'testId': str(uuid.uuid4()),
                'testName': f"cellDecode(random:{i})",
                'testDescription': f"Random {cell['type']} cell decode",
                'category': 'cellDecode',
                'mode': 'random',
            },
            'input': {'cellType': cell['type'], 'dataHex': data_hex, 'bitLength': bit_length},
        })
    return tests
