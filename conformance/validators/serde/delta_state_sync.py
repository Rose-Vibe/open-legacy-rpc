import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from protocol.unity_protocol import encode_delta_state_sync


def validate(test_obj):
    failures = []
    inp = test_obj['input']
    out = test_obj.get('output')

    if out is None:
        return {'pass': False, 'failures': ['Missing output field']}

    vid = inp['viewId']
    data, bits = encode_delta_state_sync(
        vid['id'], inp['timestamp'],
        inp['fieldValues'], inp['prevValues'], inp['fieldWidths'],
        is_first=inp['isFirst'], view_id_scope=vid['scope'],
    )

    if 'dataHex' not in out:
        failures.append("Missing output.dataHex")
    elif out['dataHex'] != data.hex():
        failures.append(f"dataHex mismatch")

    if 'bitLength' not in out:
        failures.append("Missing output.bitLength")
    elif out['bitLength'] != bits:
        failures.append(f"bitLength: expected {bits}, got {out['bitLength']}")

    return {'pass': len(failures) == 0, 'failures': failures}
