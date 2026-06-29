import os
import random
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from protocol.unity_protocol import encode_delta_state_sync
from .delta_state_sync import PRESET_TESTS


def _encode(inp):
    vid = inp['viewId']
    data, bits = encode_delta_state_sync(
        vid['id'], inp['timestamp'],
        inp['fieldValues'], inp['prevValues'], inp['fieldWidths'],
        is_first=inp['isFirst'], view_id_scope=vid['scope'],
    )
    return data.hex(), bits


def generate(mode, count=10, rng=None):
    if mode == 'basic':
        return _generate_basic()
    return _generate_random(count, rng or random.Random())


def _generate_basic():
    tests = []
    for p in PRESET_TESTS:
        inp = {
            'viewId': p['viewId'], 'timestamp': p['timestamp'], 'isFirst': p['isFirst'],
            'fieldWidths': p['fieldWidths'],
            'fieldValues': p['fieldValues'],
            'prevValues': p['prevValues'],
        }
        data_hex, bit_length = _encode(inp)
        tests.append({
            'testInfo': {
                'testId': str(uuid.uuid4()),
                'testName': f"deltaSyncDecode: {p['name']}", 'testDescription': p['desc'],
                'category': 'deltaSyncDecode', 'mode': 'basic',
            },
            'input': {
                'dataHex': data_hex, 'bitLength': bit_length,
                'fieldCount': len(p['fieldWidths']),
                'fieldWidths': p['fieldWidths'],
                'prevValues': p['prevValues'],
            },
        })
    return tests


def _generate_random(count, rng):
    tests = []
    for i in range(count):
        num_fields = rng.randint(1, 5)
        widths = [32] * num_fields
        prev = [rng.randint(0, 0xFFFFFFFF) for _ in range(num_fields)]
        cur = list(prev)
        for j in range(num_fields):
            if rng.random() > 0.5:
                cur[j] = rng.randint(0, 0xFFFFFFFF)
        inp = {
            'viewId': {'scope': 'scene', 'id': rng.randint(0, 5)},
            'timestamp': rng.randint(0, 0xFFFFFFFF), 'isFirst': rng.choice([True, False]),
            'fieldWidths': widths, 'fieldValues': cur, 'prevValues': prev,
        }
        data_hex, bit_length = _encode(inp)
        tests.append({
            'testInfo': {
                'testId': str(uuid.uuid4()),
                'testName': f"deltaSyncDecode(random:{i})", 'testDescription': 'Random decode',
                'category': 'deltaSyncDecode', 'mode': 'random',
            },
            'input': {
                'dataHex': data_hex, 'bitLength': bit_length,
                'fieldCount': num_fields, 'fieldWidths': widths, 'prevValues': prev,
            },
        })
    return tests
