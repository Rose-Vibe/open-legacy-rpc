import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from protocol.master_serialization import encode_query_request, NUMERIC, STRING, BINARY

TYPE_INT = {'NUMERIC': NUMERIC, 'STRING': STRING, 'BINARY': BINARY}
OP_INT = {
    'EQUAL': 0, 'NOT_EQUAL': 1, 'GREATER_THAN': 2, 'GREATER_THAN_EQ': 3,
    'LESS_THAN': 4, 'LESS_THAN_EQ': 5, 'IS_EMPTY': 6, 'NOT_EMPTY': 7,
}


def validate(test_obj):
    failures = []
    inp = test_obj['input']
    out = test_obj.get('output')

    if out is None:
        return {'pass': False, 'failures': ['Missing output field']}

    filters = []
    for f in inp.get('filters', []):
        filt = {
            'name': f['name'],
            'type': TYPE_INT[f['type']],
            'operation': OP_INT[f['operation']],
        }
        val = f.get('value')
        if val is not None and f['type'] == 'BINARY' and isinstance(val, str):
            val = bytes.fromhex(val)
        filt['value'] = val
        filters.append(filt)

    expected = encode_query_request(
        inp['tableName'],
        column_subset=inp.get('columnSubset') or None,
        filters=filters or None,
        row_ids=inp.get('rowIds') or None,
        password=inp.get('password'),
    )
    expected_hex = expected.hex()

    if 'dataHex' not in out:
        failures.append("Missing output.dataHex")
    elif out['dataHex'] != expected_hex:
        failures.append(f"dataHex mismatch: expected '{expected_hex}', got '{out['dataHex']}'")

    return {'pass': len(failures) == 0, 'failures': failures}
