import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from protocol.unity_protocol import decode_delta_state_sync


def validate(test_obj):
    failures = []
    inp = test_obj['input']
    out = test_obj.get('output')

    if out is None:
        return {'pass': False, 'failures': ['Missing output field']}

    try:
        expected = decode_delta_state_sync(
            bytes.fromhex(inp['dataHex']), inp['bitLength'],
            inp['fieldCount'], inp['fieldWidths'], inp['prevValues'],
        )
    except Exception as e:
        return {'pass': False, 'failures': [f"Reference decode error: {e}"]}

    if out.get('timestamp') != expected['timestamp']:
        failures.append(f"timestamp: expected {expected['timestamp']}, got {out.get('timestamp')}")
    if out.get('isFirst') != expected['is_first']:
        failures.append(f"isFirst: expected {expected['is_first']}, got {out.get('isFirst')}")

    exp_dirty = expected.get('dirty_flags', [])
    out_dirty = out.get('dirtyFlags', [])
    if out_dirty != exp_dirty:
        failures.append(f"dirtyFlags: expected {exp_dirty}, got {out_dirty}")

    exp_vals = expected.get('field_values', [])
    out_vals = out.get('fieldValues', [])
    if out_vals != exp_vals:
        failures.append(f"fieldValues: expected {exp_vals}, got {out_vals}")

    return {'pass': len(failures) == 0, 'failures': failures}
