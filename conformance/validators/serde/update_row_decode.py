import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from protocol.master_serialization import decode_update_row, NUMERIC, STRING, BINARY

TYPE_STR = {NUMERIC: 'NUMERIC', STRING: 'STRING', BINARY: 'BINARY'}


def validate(test_obj):
    failures = []
    inp = test_obj['input']
    out = test_obj.get('output')

    if out is None:
        return {'pass': False, 'failures': ['Missing output field']}

    try:
        expected = decode_update_row(bytes.fromhex(inp['dataHex']))
    except Exception as e:
        return {'pass': False, 'failures': [f"Reference decode error: {e}"]}

    if out.get('tableName') != expected['table']:
        failures.append(f"tableName mismatch: expected {expected['table']!r}, got {out.get('tableName')!r}")
    if out.get('updateMode') != expected['update_mode']:
        failures.append(f"updateMode mismatch: expected {expected['update_mode']}, got {out.get('updateMode')}")
    if out.get('rowId') != expected['row_id']:
        failures.append(f"rowId mismatch: expected {expected['row_id']}, got {out.get('rowId')}")

    exp_cells = expected['cells']
    out_cells = out.get('cells', [])
    if len(out_cells) != len(exp_cells):
        failures.append(f"cells count: expected {len(exp_cells)}, got {len(out_cells)}")
    else:
        for i, (ec, oc) in enumerate(zip(exp_cells, out_cells)):
            if oc.get('name') != ec['name']:
                failures.append(f"cells[{i}].name: expected {ec['name']!r}, got {oc.get('name')!r}")
            exp_type = TYPE_STR.get(ec['type'], str(ec['type']))
            if oc.get('type') != exp_type:
                failures.append(f"cells[{i}].type: expected {exp_type}, got {oc.get('type')}")
            # Compare values, handling binary as hex
            exp_val = ec['value']
            out_val = oc.get('value')
            if isinstance(exp_val, bytes):
                exp_val = exp_val.hex()
            if exp_val != out_val:
                failures.append(f"cells[{i}].value: expected {exp_val!r}, got {out_val!r}")

    return {'pass': len(failures) == 0, 'failures': failures}
