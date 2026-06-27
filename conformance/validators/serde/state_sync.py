import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from protocol.bitstream import BitStream
from protocol.unity_protocol import encode_state_sync


def _build_data_bs(fields):
    bs = BitStream()
    for f in fields:
        ftype = f['type']
        val = f['value']
        if ftype == 'int':
            if val < 0:
                val += 0x100000000
            bs.write_bits(val & 0xFFFFFFFF, 32)
        elif ftype == 'float':
            bs.write_float_be(val)
        elif ftype == 'bool':
            bs.write_bit(1 if val else 0)
        elif ftype == 'short':
            bs.write_bits(val & 0xFFFF, 16)
        elif ftype == 'char':
            bs.write_bits(val & 0xFF, 8)
        elif ftype == 'Vector3':
            for v in val:
                bs.write_float_be(v)
        elif ftype == 'Quaternion':
            for v in val:
                bs.write_float_be(v)
    return bs


def validate(test_obj):
    failures = []
    inp = test_obj['input']
    out = test_obj.get('output')

    if out is None:
        return {'pass': False, 'failures': ['Missing output field']}

    data_bs = _build_data_bs(inp['fields'])
    vid = inp['viewId']
    expected_data, expected_bits = encode_state_sync(
        vid['id'], inp['timestamp'], data_bs,
        is_first=inp['isFirst'], view_id_scope=vid['scope'],
    )

    if 'dataHex' not in out:
        failures.append("Missing output.dataHex")
    elif out['dataHex'] != expected_data.hex():
        failures.append(f"dataHex mismatch")

    if 'bitLength' not in out:
        failures.append("Missing output.bitLength")
    elif out['bitLength'] != expected_bits:
        failures.append(f"bitLength mismatch: expected {expected_bits}, got {out['bitLength']}")

    return {'pass': len(failures) == 0, 'failures': failures}
