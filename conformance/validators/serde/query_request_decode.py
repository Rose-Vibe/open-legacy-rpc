import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from protocol.master_serialization import decode_query_request, NUMERIC, STRING, BINARY

TYPE_STR = {NUMERIC: 'NUMERIC', STRING: 'STRING', BINARY: 'BINARY'}
OP_STR = {0: 'EQUAL', 1: 'NOT_EQUAL', 2: 'GREATER_THAN', 3: 'GREATER_THAN_EQ',
          4: 'LESS_THAN', 5: 'LESS_THAN_EQ', 6: 'IS_EMPTY', 7: 'NOT_EMPTY'}


def validate(test_obj):
    failures = []
    inp = test_obj['input']
    out = test_obj.get('output')

    if out is None:
        return {'pass': False, 'failures': ['Missing output field']}

    try:
        expected = decode_query_request(bytes.fromhex(inp['dataHex']))
    except Exception as e:
        return {'pass': False, 'failures': [f"Reference decode error: {e}"]}

    if out.get('tableName') != expected['table']:
        failures.append(f"tableName: expected {expected['table']!r}, got {out.get('tableName')!r}")

    exp_cols = expected.get('column_subset', [])
    out_cols = out.get('columnSubset', [])
    if out_cols != exp_cols:
        failures.append(f"columnSubset: expected {exp_cols}, got {out_cols}")

    exp_filters = expected.get('filters', [])
    out_filters = out.get('filters', [])
    if len(out_filters) != len(exp_filters):
        failures.append(f"filters count: expected {len(exp_filters)}, got {len(out_filters)}")
    else:
        for i, (ef, of) in enumerate(zip(exp_filters, out_filters)):
            if of.get('name') != ef['name']:
                failures.append(f"filters[{i}].name: expected {ef['name']!r}")
            exp_op = OP_STR.get(ef['operation'], str(ef['operation']))
            if of.get('operation') != exp_op:
                failures.append(f"filters[{i}].operation: expected {exp_op}")

    exp_rids = expected.get('row_ids', [])
    out_rids = out.get('rowIds', [])
    if out_rids != exp_rids:
        failures.append(f"rowIds: expected {exp_rids}, got {out_rids}")

    return {'pass': len(failures) == 0, 'failures': failures}
