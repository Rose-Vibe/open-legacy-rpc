import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from protocol.master_serialization import encode_query_reply, NUMERIC, STRING, BINARY

TYPE_INT = {'NUMERIC': NUMERIC, 'STRING': STRING, 'BINARY': BINARY}


def validate(test_obj):
    failures = []
    inp = test_obj['input']
    out = test_obj.get('output')

    if out is None:
        return {'pass': False, 'failures': ['Missing output field']}

    columns = [{'name': c['name'], 'type': TYPE_INT[c['type']]} for c in inp['columns']]
    rows = []
    for row in inp['rows']:
        cells = {}
        for col in inp['columns']:
            if col['name'] in row['cells']:
                val = row['cells'][col['name']]
                if col['type'] == 'BINARY' and isinstance(val, str):
                    val = bytes.fromhex(val)
                cells[col['name']] = val
        rows.append({'key': row['key'], 'cells': cells})

    expected = encode_query_reply(columns, rows)
    expected_hex = expected.hex()

    if 'dataHex' not in out:
        failures.append("Missing output.dataHex")
    elif out['dataHex'] != expected_hex:
        failures.append(f"dataHex mismatch: expected '{expected_hex}', got '{out['dataHex']}'")

    return {'pass': len(failures) == 0, 'failures': failures}
