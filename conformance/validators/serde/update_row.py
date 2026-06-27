import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from protocol.master_serialization import (
    encode_update_row, decode_update_row, NUMERIC, STRING, BINARY
)

TYPE_INT = {'NUMERIC': NUMERIC, 'STRING': STRING, 'BINARY': BINARY}


def _cells_to_internal(cells):
    result = []
    for c in cells:
        val = c['value']
        if c['type'] == 'BINARY' and isinstance(val, str):
            val = bytes.fromhex(val)
        result.append({'name': c['name'], 'type': TYPE_INT[c['type']], 'value': val})
    return result


def validate(test_obj):
    failures = []
    inp = test_obj['input']
    out = test_obj.get('output')

    if out is None:
        return {'pass': False, 'failures': ['Missing output field']}

    cells = _cells_to_internal(inp['cells'])
    expected = encode_update_row(
        inp['tableName'], cells,
        update_mode=inp['updateMode'],
        row_id=inp['rowId'],
        password=inp['password'],
    )
    expected_hex = expected.hex()

    if 'dataHex' not in out:
        failures.append("Missing output.dataHex")
    elif out['dataHex'] != expected_hex:
        failures.append(f"dataHex mismatch: expected '{expected_hex}', got '{out['dataHex']}'")

    # Round-trip: decode the implementer's output
    if not failures and 'dataHex' in out:
        try:
            decoded = decode_update_row(bytes.fromhex(out['dataHex']))
            if decoded['table'] != inp['tableName']:
                failures.append(f"Round-trip table mismatch: {decoded['table']}")
            if decoded['update_mode'] != inp['updateMode']:
                failures.append(f"Round-trip updateMode mismatch: {decoded['update_mode']}")
        except Exception as e:
            failures.append(f"Round-trip decode error: {e}")

    return {'pass': len(failures) == 0, 'failures': failures}
