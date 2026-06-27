import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from protocol.raknet_transport import encode_address


def validate(test_obj):
    failures = []
    inp = test_obj['input']
    out = test_obj.get('output')

    if out is None:
        return {'pass': False, 'failures': ['Missing output field']}

    expected = encode_address(inp['ip'], inp['port']).hex()

    if 'dataHex' not in out:
        failures.append("Missing output.dataHex")
    elif out['dataHex'] != expected:
        failures.append(f"dataHex: expected '{expected}', got '{out['dataHex']}'")

    return {'pass': len(failures) == 0, 'failures': failures}
