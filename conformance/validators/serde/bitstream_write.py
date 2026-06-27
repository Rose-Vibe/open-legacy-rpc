import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from conformance.validators.serde._bitstream_exec import execute_ops


def validate(test_obj):
    failures = []
    inp = test_obj['input']
    out = test_obj.get('output')

    if out is None:
        return {'pass': False, 'failures': ['Missing output field']}

    try:
        expected_hex, expected_bits = execute_ops(inp['operations'])
    except Exception as e:
        return {'pass': False, 'failures': [f"Reference execution error: {e}"]}

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

    return {'pass': len(failures) == 0, 'failures': failures}
