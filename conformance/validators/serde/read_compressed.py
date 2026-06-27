import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from protocol.bitstream import BitStream


def validate(test_obj):
    failures = []
    inp = test_obj['input']
    out = test_obj.get('output')

    if out is None:
        return {'pass': False, 'failures': ['Missing output field']}

    data_hex = inp['dataHex']
    bit_length = inp['bitLength']

    bs = BitStream(bytes.fromhex(data_hex), bit_length=bit_length)
    expected_value = bs.read_compressed_u32()

    if 'value' not in out:
        failures.append("Missing output.value")
    elif out['value'] != expected_value:
        failures.append(
            f"value mismatch: expected {expected_value}, got {out['value']}"
        )

    return {'pass': len(failures) == 0, 'failures': failures}
