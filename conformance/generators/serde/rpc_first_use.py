import os
import random
import struct
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from .rpc_encode import PRESET_TESTS as ENCODE_PRESETS, _random_param, METHODS_WITH_SIGS, RPC_MODES

PRESET_TESTS = ENCODE_PRESETS[:8]  # Same methods but first-use format


def generate(mode, count=10, rng=None):
    if mode == 'basic':
        return _generate_basic()
    return _generate_random(count, rng or random.Random())


def _generate_basic():
    tests = []
    for i, preset in enumerate(PRESET_TESTS):
        tests.append({
            'testInfo': {
                'testId': str(uuid.uuid4()),
                'testName': f"rpcFirstUse: {preset['desc']}",
                'testDescription': f"First-use: {preset['desc']}",
                'category': 'rpcFirstUse',
                'mode': 'basic',
            },
            'input': {
                'methodName': preset['name'],
                'viewId': {'scope': 'scene', 'id': 0},
                'rpcCounter': 0,
                'rpcMode': preset['mode'],
                'params': preset['params'],
            },
        })
    return tests


def _generate_random(count, rng):
    tests = []
    method_names = list(METHODS_WITH_SIGS.keys())
    for i in range(count):
        method = rng.choice(method_names)
        sig = METHODS_WITH_SIGS[method]
        params = [_random_param(rng, ptype) for ptype, _ in sig]
        tests.append({
            'testInfo': {
                'testId': str(uuid.uuid4()),
                'testName': f"rpcFirstUse(random:{i})",
                'testDescription': f"Random first-use {method}",
                'category': 'rpcFirstUse',
                'mode': 'random',
            },
            'input': {
                'methodName': method,
                'viewId': {'scope': 'scene', 'id': rng.randint(0, 5)},
                'rpcCounter': 0,
                'rpcMode': rng.choice(RPC_MODES),
                'params': params,
            },
        })
    return tests
