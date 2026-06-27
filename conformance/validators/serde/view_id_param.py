import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from protocol.unity_protocol import encode_view_id_16


def validate(test_obj):
    failures = []
    inp = test_obj['input']
    out = test_obj.get('output')

    if out is None:
        return {'pass': False, 'failures': ['Missing output field']}

    expected = encode_view_id_16(inp['scope'], inp['id'])

    if 'value16' not in out:
        failures.append("Missing output.value16")
    elif out['value16'] != expected:
        failures.append(f"value16: expected {expected}, got {out['value16']}")

    return {'pass': len(failures) == 0, 'failures': failures}
