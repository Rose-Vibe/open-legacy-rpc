import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from protocol.master_serialization import decode_query_reply, NUMERIC, STRING, BINARY

TYPE_STR = {NUMERIC: 'NUMERIC', STRING: 'STRING', BINARY: 'BINARY'}


def validate(test_obj):
    failures = []
    inp = test_obj['input']
    out = test_obj.get('output')

    if out is None:
        return {'pass': False, 'failures': ['Missing output field']}

    try:
        expected = decode_query_reply(bytes.fromhex(inp['dataHex']))
    except Exception as e:
        return {'pass': False, 'failures': [f"Reference decode error: {e}"]}

    exp_cols = expected['columns']
    out_cols = out.get('columns', [])
    if len(out_cols) != len(exp_cols):
        failures.append(f"columns count: expected {len(exp_cols)}, got {len(out_cols)}")
    else:
        for i, (ec, oc) in enumerate(zip(exp_cols, out_cols)):
            if oc.get('name') != ec['name']:
                failures.append(f"columns[{i}].name mismatch")
            exp_type = TYPE_STR.get(ec['type'], str(ec['type']))
            if oc.get('type') != exp_type:
                failures.append(f"columns[{i}].type mismatch")

    exp_rows = expected['rows']
    out_rows = out.get('rows', [])
    if len(out_rows) != len(exp_rows):
        failures.append(f"rows count: expected {len(exp_rows)}, got {len(out_rows)}")
    else:
        for i, (er, orow) in enumerate(zip(exp_rows, out_rows)):
            if orow.get('key') != er['key']:
                failures.append(f"rows[{i}].key mismatch")

    return {'pass': len(failures) == 0, 'failures': failures}
