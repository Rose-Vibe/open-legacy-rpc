import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from protocol.unity_protocol import encode_rpc_first_use, RPCMode


MODE_MAP = {
    'Server': RPCMode.Server, 'Others': RPCMode.Others, 'All': RPCMode.All,
    'Player': RPCMode.Player, 'OthersBuffered': RPCMode.OthersBuffered,
    'AllBuffered': RPCMode.AllBuffered,
}


def validate(test_obj):
    failures = []
    inp = test_obj['input']
    out = test_obj.get('output')

    if out is None:
        return {'pass': False, 'failures': ['Missing output field']}

    params = []
    for p in inp['params']:
        if p['type'] == 'bytes':
            params.append(bytes.fromhex(p['value']))
        elif p['type'] in ('Vector3', 'Quaternion'):
            params.append(tuple(p['value']))
        else:
            params.append(p['value'])

    vid = inp['viewId']
    view_id = vid['id'] if vid['scope'] == 'scene' else (0x100000000 | vid['id'])
    mode = MODE_MAP[inp['rpcMode']]

    data, bits = encode_rpc_first_use(
        inp['methodName'], params, view_id=view_id,
        timestamp_ms=inp['timestampMs'], mode=mode, target_view=0x2000,
    )

    if 'dataHex' not in out:
        failures.append("Missing output.dataHex")
    elif out['dataHex'] != data.hex():
        failures.append(f"dataHex mismatch")

    if 'bitLength' not in out:
        failures.append("Missing output.bitLength")
    elif out['bitLength'] != bits:
        failures.append(f"bitLength mismatch: expected {bits}, got {out['bitLength']}")

    return {'pass': len(failures) == 0, 'failures': failures}
