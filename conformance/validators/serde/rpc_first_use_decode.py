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

    if not expected.get('first_use'):
        failures.append("Expected first_use=true in reference decode")

    if out.get('methodName') != expected.get('method_name'):
        failures.append(f"methodName: expected {expected.get('method_name')!r}, got {out.get('methodName')!r}")
    exp_mode = expected.get('rpc_mode')
    if exp_mode is not None and out.get('rpcMode') != exp_mode.name:
        failures.append(f"rpcMode: expected {exp_mode.name}, got {out.get('rpcMode')}")

    return {'pass': len(failures) == 0, 'failures': failures}
