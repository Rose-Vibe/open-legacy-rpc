import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from protocol.huffman import decode_string, get_tree


def validate(test_obj):
    failures = []
    inp = test_obj['input']
    out = test_obj.get('output')

    if out is None:
        return {'pass': False, 'failures': ['Missing output field']}

    data_hex = inp['dataHex']
    bit_length = inp['bitLength']

    if data_hex == '' or bit_length == 0:
        expected_hex = ''
    else:
        data = bytes.fromhex(data_hex)
        bit_str = bin(int.from_bytes(data, 'big'))[2:].zfill(len(data) * 8)
        bit_str = bit_str[:bit_length]
        decoded = decode_string(bit_str, get_tree())
        expected_hex = decoded.hex()

    if 'stringHex' not in out:
        failures.append("Missing output.stringHex")
    elif out['stringHex'] != expected_hex:
        failures.append(
            f"stringHex mismatch: expected '{expected_hex}', got '{out['stringHex']}'"
        )

    return {'pass': len(failures) == 0, 'failures': failures}
