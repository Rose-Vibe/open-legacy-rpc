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

    value = inp['value']

    bs = BitStream()
    bs.write_compressed_u32(value)
    expected_hex = bs.to_bytes().hex()
    expected_bits = bs.bit_length

    if 'dataHex' not in out:
        failures.append("Missing output.dataHex")
    elif out['dataHex'] != expected_hex:
        failures.append(
            f"dataHex mismatch: expected '{expected_hex}', got '{out['dataHex']}'"
        )

    if 'bitLength' not in out:
        failures.append("Missing output.bitLength")
    elif out['bitLength'] != expected_bits:
        failures.append(
            f"bitLength mismatch: expected {expected_bits}, got {out['bitLength']}"
        )

    # Round-trip check: decode the implementer's output and verify it matches
    if 'dataHex' in out and 'bitLength' in out and not failures:
        try:
            impl_bs = BitStream(bytes.fromhex(out['dataHex']),
                                bit_length=out['bitLength'])
            decoded = impl_bs.read_compressed_u32()
            if decoded != value:
                failures.append(
                    f"Round-trip decode mismatch: encoded for {value}, "
                    f"decodes to {decoded}"
                )
        except Exception as e:
            failures.append(f"Round-trip decode error: {e}")

    return {'pass': len(failures) == 0, 'failures': failures}
