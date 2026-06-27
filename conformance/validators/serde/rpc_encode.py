import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from protocol.unity_protocol import (
    encode_rpc_subsequent, encode_view_id_16, RPCMode,
    METHOD_INDEX_MAP,
)


MODE_MAP = {
    'Server': RPCMode.Server, 'Others': RPCMode.Others, 'All': RPCMode.All,
    'Player': RPCMode.Player, 'OthersBuffered': RPCMode.OthersBuffered,
    'AllBuffered': RPCMode.AllBuffered,
}


def _input_to_params(inp):
    params = []
    for p in inp['params']:
        if p['type'] == 'bytes':
            params.append(bytes.fromhex(p['value']))
        elif p['type'] == 'Vector3':
            params.append(tuple(p['value']))
        elif p['type'] == 'Quaternion':
            params.append(tuple(p['value']))
        else:
            params.append(p['value'])
    return params


def _view_id_to_int(vid):
    scope = vid['scope']
    id_val = vid['id']
    if scope == 'scene':
        return id_val
    else:
        return 0x100000000 | id_val


def validate(test_obj):
    failures = []
    inp = test_obj['input']
    out = test_obj.get('output')

    if out is None:
        return {'pass': False, 'failures': ['Missing output field']}

    method = inp['methodName']
    if method not in METHOD_INDEX_MAP:
        return {'pass': False, 'failures': [f"Unknown method: {method}"]}

    params = _input_to_params(inp)
    mode = MODE_MAP[inp['rpcMode']]
    view_id = _view_id_to_int(inp['viewId'])

    expected_data, expected_bits = encode_rpc_subsequent(
        method, params, view_id=view_id,
        rpc_counter=inp['rpcCounter'], mode=mode,
    )
    expected_hex = expected_data.hex()

    if 'dataHex' not in out:
        failures.append("Missing output.dataHex")
    elif out['dataHex'] != expected_hex:
        failures.append(f"dataHex mismatch: expected '{expected_hex}', got '{out['dataHex']}'")

    if 'bitLength' not in out:
        failures.append("Missing output.bitLength")
    elif out['bitLength'] != expected_bits:
        failures.append(f"bitLength mismatch: expected {expected_bits}, got {out['bitLength']}")

    return {'pass': len(failures) == 0, 'failures': failures}
