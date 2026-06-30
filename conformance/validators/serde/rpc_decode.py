import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from protocol.unity_protocol import decode_rpc


def validate(test_obj):
    failures = []
    inp = test_obj['input']
    out = test_obj.get('output')

    if out is None:
        return {'pass': False, 'failures': ['Missing output field']}

    try:
        expected = decode_rpc(bytes.fromhex(inp['dataHex']), inp['bitLength'])
    except Exception as e:
        return {'pass': False, 'failures': [f"Reference decode error: {e}"]}

    if out.get('methodName') != expected.get('method_name'):
        failures.append(f"methodName: expected {expected.get('method_name')!r}, got {out.get('methodName')!r}")
    if out.get('timestampMs') != expected.get('timestamp_ms'):
        failures.append(f"timestampMs: expected {expected.get('timestamp_ms')}, got {out.get('timestampMs')}")
    exp_mode = expected.get('rpc_mode')
    if exp_mode is not None:
        exp_mode_name = exp_mode.name
        if out.get('rpcMode') != exp_mode_name:
            failures.append(f"rpcMode: expected {exp_mode_name}, got {out.get('rpcMode')}")
    exp_tv = expected.get('target_view')
    if exp_tv is not None and out.get('targetView') != exp_tv:
        failures.append(f"targetView: expected {exp_tv}, got {out.get('targetView')}")

    return {'pass': len(failures) == 0, 'failures': failures}
