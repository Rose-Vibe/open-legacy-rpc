import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from protocol.unity_protocol import compute_method_index


def validate(test_obj):
    failures = []
    inp = test_obj['input']
    out = test_obj.get('output')

    if out is None:
        return {'pass': False, 'failures': ['Missing output field']}

    expected = compute_method_index(inp['methodRid'], inp['interfaceMethodCount'])

    if 'methodIndex' not in out:
        failures.append("Missing output.methodIndex")
    elif out['methodIndex'] != expected:
        failures.append(f"methodIndex: expected {expected}, got {out['methodIndex']}")

    return {'pass': len(failures) == 0, 'failures': failures}
