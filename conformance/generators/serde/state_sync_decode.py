import os
import random
import struct
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from protocol.unity_protocol import encode_state_sync
from .state_sync import PRESET_TESTS, _random_field
from conformance.validators.serde.state_sync import _build_data_bs


def generate(mode, count=10, rng=None):
    if mode == 'basic':
        return _generate_basic()
    return _generate_random(count, rng or random.Random())


def _encode(inp):
    data_bs = _build_data_bs(inp['fields'])
    vid = inp['viewId']
    data, bits = encode_state_sync(
        vid['id'], inp['timestamp'], data_bs,
        is_first=inp['isFirst'], view_id_scope=vid['scope'],
    )
    return data.hex(), bits


def _generate_basic():
    tests = []
    for p in PRESET_TESTS:
        inp = {
            'viewId': p['viewId'], 'timestamp': p['timestamp'],
            'isFirst': p['isFirst'], 'fields': p['fields'],
        }
        data_hex, bit_length = _encode(inp)
        tests.append({
            'testInfo': {
                'testId': str(uuid.uuid4()),
                'testName': f"stateSyncDecode: {p['name']}", 'testDescription': p['desc'],
                'category': 'stateSyncDecode', 'mode': 'basic',
            },
            'input': {'dataHex': data_hex, 'bitLength': bit_length},
        })
    return tests


def _generate_random(count, rng):
    tests = []
    for i in range(count):
        num_fields = rng.randint(1, 4)
        inp = {
            'viewId': {'scope': rng.choice(['scene', 'allocated']), 'id': rng.randint(0, 5)},
            'timestamp': rng.randint(0, 65535),
            'isFirst': rng.choice([True, False]),
            'fields': [_random_field(rng) for _ in range(num_fields)],
        }
        data_hex, bit_length = _encode(inp)
        tests.append({
            'testInfo': {
                'testId': str(uuid.uuid4()),
                'testName': f"stateSyncDecode(random:{i})", 'testDescription': 'Random decode',
                'category': 'stateSyncDecode', 'mode': 'random',
            },
            'input': {'dataHex': data_hex, 'bitLength': bit_length},
        })
    return tests
