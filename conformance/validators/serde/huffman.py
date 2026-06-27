import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from protocol.huffman import encode_string_for_wire, decode_string, get_tree


def validate(test_obj):
    failures = []
    inp = test_obj['input']
    out = test_obj.get('output')

    if out is None:
        return {'pass': False, 'failures': ['Missing output field']}

    string_bytes = bytes.fromhex(inp['stringHex'])
    s = string_bytes.decode('latin-1')

    if s == '':
        expected_hex = ''
        expected_bits = 0
    else:
        bits = encode_string_for_wire(s)
        expected_hex = int(bits, 2).to_bytes((len(bits) + 7) // 8, 'big').hex()
        expected_bits = len(bits)

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

    # Round-trip: decode the output and compare
    if not failures and out.get('dataHex') and out.get('bitLength', 0) > 0:
        try:
            data = bytes.fromhex(out['dataHex'])
            bit_str = bin(int.from_bytes(data, 'big'))[2:].zfill(len(data) * 8)
            bit_str = bit_str[:out['bitLength']]
            decoded = decode_string(bit_str, get_tree())
            if decoded != string_bytes:
                failures.append(
                    f"Round-trip mismatch: decoded {decoded.hex()}, "
                    f"expected {string_bytes.hex()}"
                )
        except Exception as e:
            failures.append(f"Round-trip decode error: {e}")

    return {'pass': len(failures) == 0, 'failures': failures}
