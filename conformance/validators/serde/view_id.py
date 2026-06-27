import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from protocol.unity_protocol import encode_view_id


def validate(test_obj):
    failures = []
    inp = test_obj['input']
    out = test_obj.get('output')

    if out is None:
        return {'pass': False, 'failures': ['Missing output field']}

    vid = inp['id'] if inp['scope'] == 'scene' else (0x100000000 | inp['id'])
    expected = encode_view_id(vid).hex()

    if 'dataHex' not in out:
        failures.append("Missing output.dataHex")
    elif out['dataHex'] != expected:
        failures.append(f"dataHex: expected '{expected}', got '{out['dataHex']}'")

    return {'pass': len(failures) == 0, 'failures': failures}
