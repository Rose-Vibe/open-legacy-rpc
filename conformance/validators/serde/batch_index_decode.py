import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from protocol.unity_protocol import decode_batch_index


def validate(test_obj):
    failures = []
    inp = test_obj['input']
    out = test_obj.get('output')
    expected = test_obj.get('expected', {})

    if out is None:
        return {'pass': False, 'failures': ['Missing output field']}

    payload = bytes.fromhex(inp['dataHex'])
    ref = decode_batch_index(payload)
    if ref is None:
        return {'pass': False, 'failures': ['Reference decode returned None']}

    exp_name = expected.get('methodName', ref['method_name'])
    exp_index = expected.get('methodIndex', ref['method_index'])

    if 'methodName' not in out:
        failures.append("Missing output.methodName")
    elif out['methodName'] != exp_name:
        failures.append(f"methodName mismatch: expected '{exp_name}', got '{out['methodName']}'")

    if 'methodIndex' not in out:
        failures.append("Missing output.methodIndex")
    elif out['methodIndex'] != exp_index:
        failures.append(f"methodIndex mismatch: expected {exp_index}, got {out['methodIndex']}")

    return {'pass': len(failures) == 0, 'failures': failures}
