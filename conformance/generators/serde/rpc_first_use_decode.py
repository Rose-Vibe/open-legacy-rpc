import os
import random
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from protocol.unity_protocol import encode_rpc_first_use, RPCMode
from .rpc_encode import _random_param, METHODS_WITH_SIGS, RPC_MODES
from .rpc_first_use import PRESET_TESTS

MODE_MAP = {
    'Server': RPCMode.Server, 'Others': RPCMode.Others, 'All': RPCMode.All,
    'Player': RPCMode.Player, 'OthersBuffered': RPCMode.OthersBuffered,
    'AllBuffered': RPCMode.AllBuffered,
}


def _encode(inp):
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
    data, bits = encode_rpc_first_use(inp['methodName'], params, view_id=view_id,
                                       rpc_counter=inp['rpcCounter'], mode=mode,
                                       target_view=0x2000)
    return data.hex(), bits


def generate(mode, count=10, rng=None):
    if mode == 'basic':
        return _generate_basic()
    return _generate_random(count, rng or random.Random())


def _generate_basic():
    tests = []
    for preset in PRESET_TESTS:
        inp = {
            'methodName': preset['name'],
            'viewId': {'scope': 'scene', 'id': 0},
            'rpcCounter': 0,
            'rpcMode': preset['mode'],
            'params': preset['params'],
        }
        data_hex, bit_length = _encode(inp)
        tests.append({
            'testInfo': {
                'testId': str(uuid.uuid4()),
                'testName': f"rpcFirstUseDecode: {preset['desc']}",
                'testDescription': f"First-use decode: {preset['desc']}",
                'category': 'rpcFirstUseDecode',
                'mode': 'basic',
            },
            'input': {'dataHex': data_hex, 'bitLength': bit_length},
        })
    return tests


def _generate_random(count, rng):
    tests = []
    method_names = list(METHODS_WITH_SIGS.keys())
    for i in range(count):
        method = rng.choice(method_names)
        sig = METHODS_WITH_SIGS[method]
        params_json = [_random_param(rng, pt) for pt, _ in sig]
        inp = {
            'methodName': method, 'viewId': {'scope': 'scene', 'id': 0},
            'rpcCounter': 0, 'rpcMode': rng.choice(RPC_MODES), 'params': params_json,
        }
        data_hex, bit_length = _encode(inp)
        tests.append({
            'testInfo': {
                'testId': str(uuid.uuid4()),
                'testName': f"rpcFirstUseDecode(random:{i})",
                'testDescription': f"Random first-use {method} decode",
                'category': 'rpcFirstUseDecode',
                'mode': 'random',
            },
            'input': {'dataHex': data_hex, 'bitLength': bit_length},
        })
    return tests
