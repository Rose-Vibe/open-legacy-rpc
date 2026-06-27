import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from protocol.bitstream import BitStream
from protocol.master_serialization import write_cell, NUMERIC, STRING, BINARY

TYPE_INT = {'NUMERIC': NUMERIC, 'STRING': STRING, 'BINARY': BINARY}


def validate(test_obj):
    failures = []
    inp = test_obj['input']
    out = test_obj.get('output')

    if out is None:
        return {'pass': False, 'failures': ['Missing output field']}

    cell_type = inp['cellType']
    value = inp['value']

    if cell_type == 'BINARY' and isinstance(value, str):
        value = bytes.fromhex(value) if value else b''

    bs = BitStream()
    write_cell(bs, value, TYPE_INT[cell_type])
    expected_hex = bs.to_bytes().hex()
    expected_bits = bs.bit_length

    if 'dataHex' not in out:
        failures.append("Missing output.dataHex")
    elif out['dataHex'] != expected_hex:
        failures.append(f"dataHex mismatch: expected '{expected_hex}', got '{out['dataHex']}'")

    if 'bitLength' not in out:
        failures.append("Missing output.bitLength")
    elif out['bitLength'] != expected_bits:
        failures.append(f"bitLength mismatch: expected {expected_bits}, got {out['bitLength']}")

    return {'pass': len(failures) == 0, 'failures': failures}
