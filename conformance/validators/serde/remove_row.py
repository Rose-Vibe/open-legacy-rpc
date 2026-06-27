import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from protocol.master_serialization import encode_remove_row


def validate(test_obj):
    failures = []
    inp = test_obj['input']
    out = test_obj.get('output')

    if out is None:
        return {'pass': False, 'failures': ['Missing output field']}

    expected = encode_remove_row(inp['tableName'], inp['rowId'], password=inp.get('password'))
    expected_hex = expected.hex()

    if 'dataHex' not in out:
        failures.append("Missing output.dataHex")
    elif out['dataHex'] != expected_hex:
        failures.append(f"dataHex mismatch: expected '{expected_hex}', got '{out['dataHex']}'")

    return {'pass': len(failures) == 0, 'failures': failures}
