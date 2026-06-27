import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from protocol.unity_protocol import compute_method_id


def validate(test_obj):
    failures = []
    inp = test_obj['input']
    out = test_obj.get('output')

    if out is None:
        return {'pass': False, 'failures': ['Missing output field']}

    guid, method_hash = compute_method_id(inp['methodName'])

    if 'classGuidHex' not in out:
        failures.append("Missing output.classGuidHex")
    elif out['classGuidHex'] != guid.hex():
        failures.append(f"classGuidHex: expected '{guid.hex()}', got '{out['classGuidHex']}'")

    if 'methodHashHex' not in out:
        failures.append("Missing output.methodHashHex")
    elif out['methodHashHex'] != method_hash.hex():
        failures.append(f"methodHashHex: expected '{method_hash.hex()}', got '{out['methodHashHex']}'")

    return {'pass': len(failures) == 0, 'failures': failures}
