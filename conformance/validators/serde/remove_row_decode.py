import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from protocol.master_serialization import decode_remove_row


def validate(test_obj):
    failures = []
    inp = test_obj['input']
    out = test_obj.get('output')

    if out is None:
        return {'pass': False, 'failures': ['Missing output field']}

    try:
        expected = decode_remove_row(bytes.fromhex(inp['dataHex']))
    except Exception as e:
        return {'pass': False, 'failures': [f"Reference decode error: {e}"]}

    if out.get('tableName') != expected['table']:
        failures.append(f"tableName: expected {expected['table']!r}, got {out.get('tableName')!r}")
    if out.get('rowId') != expected['row_id']:
        failures.append(f"rowId: expected {expected['row_id']}, got {out.get('rowId')}")

    return {'pass': len(failures) == 0, 'failures': failures}
