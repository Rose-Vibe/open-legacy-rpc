import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from protocol.bitstream import BitStream
from protocol.master_serialization import read_cell, NUMERIC, STRING, BINARY

TYPE_INT = {'NUMERIC': NUMERIC, 'STRING': STRING, 'BINARY': BINARY}


def validate(test_obj):
    failures = []
    inp = test_obj['input']
    out = test_obj.get('output')

    if out is None:
        return {'pass': False, 'failures': ['Missing output field']}

    cell_type = inp['cellType']
    bs = BitStream(bytes.fromhex(inp['dataHex']), bit_length=inp['bitLength'])
    expected = read_cell(bs, TYPE_INT[cell_type])

    actual = out.get('value')

    if expected is None:
        if actual is not None:
            failures.append(f"Expected null, got {actual!r}")
    elif cell_type == 'NUMERIC':
        if actual != expected:
            failures.append(f"value mismatch: expected {expected}, got {actual}")
    elif cell_type == 'STRING':
        if actual != expected:
            failures.append(f"value mismatch: expected {expected!r}, got {actual!r}")
    elif cell_type == 'BINARY':
        expected_hex = expected.hex() if isinstance(expected, bytes) else expected
        if actual != expected_hex:
            failures.append(f"value mismatch: expected '{expected_hex}', got '{actual}'")

    return {'pass': len(failures) == 0, 'failures': failures}
