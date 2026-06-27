import os
import random
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from protocol.unity_protocol import (
    encode_rpc_subsequent, RPCMode, METHOD_INDEX_MAP, METHOD_SIGNATURES,
)
from .rpc_encode import PRESET_TESTS as ENCODE_PRESETS, _random_param, METHODS_WITH_SIGS, RPC_MODES

MODE_MAP = {
    'Server': RPCMode.Server, 'Others': RPCMode.Others, 'All': RPCMode.All,
    'Player': RPCMode.Player, 'OthersBuffered': RPCMode.OthersBuffered,
    'AllBuffered': RPCMode.AllBuffered,
}


def _encode_from_preset(preset, counter):
    params = []
    for p in preset['params']:
        if p['type'] == 'bytes':
            params.append(bytes.fromhex(p['value']))
        elif p['type'] in ('Vector3', 'Quaternion'):
            params.append(tuple(p['value']))
        else:
            params.append(p['value'])
    mode = MODE_MAP[preset['mode']]
    data, bits = encode_rpc_subsequent(preset['name'], params, view_id=0,
                                       rpc_counter=counter, mode=mode)
    return data.hex(), bits


def generate(mode, count=10, rng=None):
    if mode == 'basic':
        return _generate_basic()
    return _generate_random(count, rng or random.Random())


def _generate_basic():
    tests = []
    for i, preset in enumerate(ENCODE_PRESETS):
        data_hex, bit_length = _encode_from_preset(preset, i)
        tests.append({
            'testInfo': {
                'testId': str(uuid.uuid4()),
                'testName': f"rpcDecode: {preset['desc']}",
                'testDescription': preset['desc'],
                'category': 'rpcDecode',
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
        sig_types = [pt for pt, _ in METHODS_WITH_SIGS[method]]
        params = []
        for pt in sig_types:
            p = _random_param(rng, pt)
            if p['type'] == 'bytes':
                params.append(bytes.fromhex(p['value']))
            elif p['type'] in ('Vector3', 'Quaternion'):
                params.append(tuple(p['value']))
            else:
                params.append(p['value'])
        mode = MODE_MAP[rng.choice(RPC_MODES)]
        counter = rng.randint(0, 127)
        data, bits = encode_rpc_subsequent(method, params, view_id=0,
                                           rpc_counter=counter, mode=mode)
        tests.append({
            'testInfo': {
                'testId': str(uuid.uuid4()),
                'testName': f"rpcDecode(random:{i})",
                'testDescription': f"Random {method} decode",
                'category': 'rpcDecode',
                'mode': 'random',
            },
            'input': {'dataHex': data.hex(), 'bitLength': bits},
        })
    return tests
