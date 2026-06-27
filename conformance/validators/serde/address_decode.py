import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from protocol.raknet_transport import decode_address


def validate(test_obj):
    failures = []
    inp = test_obj['input']
    out = test_obj.get('output')

    if out is None:
        return {'pass': False, 'failures': ['Missing output field']}

    data = bytes.fromhex(inp['dataHex'])
    expected_ip, expected_port = decode_address(data)

    if out.get('ip') != expected_ip:
        failures.append(f"ip: expected '{expected_ip}', got '{out.get('ip')}'")
    if out.get('port') != expected_port:
        failures.append(f"port: expected {expected_port}, got {out.get('port')}")

    return {'pass': len(failures) == 0, 'failures': failures}
