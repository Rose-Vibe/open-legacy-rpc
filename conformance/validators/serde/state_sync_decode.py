import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from protocol.unity_protocol import decode_state_sync


def validate(test_obj):
    failures = []
    inp = test_obj['input']
    out = test_obj.get('output')

    if out is None:
        return {'pass': False, 'failures': ['Missing output field']}

    try:
        expected = decode_state_sync(bytes.fromhex(inp['dataHex']), inp['bitLength'])
    except Exception as e:
        return {'pass': False, 'failures': [f"Reference decode error: {e}"]}

    if out.get('timestamp') != expected['timestamp']:
        failures.append(f"timestamp: expected {expected['timestamp']}, got {out.get('timestamp')}")
    if out.get('isFirst') != expected['is_first']:
        failures.append(f"isFirst: expected {expected['is_first']}, got {out.get('isFirst')}")
    if out.get('viewIdScope') != expected['view_id_scope']:
        failures.append(f"viewIdScope mismatch")
    if out.get('viewId') != expected['view_id']:
        failures.append(f"viewId: expected {expected['view_id']}, got {out.get('viewId')}")

    return {'pass': len(failures) == 0, 'failures': failures}
