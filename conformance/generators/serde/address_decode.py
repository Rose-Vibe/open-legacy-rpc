import os
import random
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from protocol.raknet_transport import encode_address
from .address_encode import PRESET_TESTS


def generate(mode, count=10, rng=None):
    if mode == 'basic':
        return _generate_basic()
    return _generate_random(count, rng or random.Random())


def _generate_basic():
    return [{
        'testInfo': {
            'testId': str(uuid.uuid4()),
            'testName': f"addressDecode({ip}:{port})",
            'testDescription': desc,
            'category': 'addressDecode',
            'mode': 'basic',
        },
        'input': {'dataHex': encode_address(ip, port).hex()},
    } for ip, port, desc in PRESET_TESTS]


def _generate_random(count, rng):
    return [{
        'testInfo': {
            'testId': str(uuid.uuid4()),
            'testName': f"addressDecode(random:{i})",
            'testDescription': "Random address decode",
            'category': 'addressDecode',
            'mode': 'random',
        },
        'input': {
            'dataHex': encode_address(
                f"{rng.randint(0,255)}.{rng.randint(0,255)}.{rng.randint(0,255)}.{rng.randint(0,255)}",
                rng.randint(0, 65535),
            ).hex(),
        },
    } for i in range(count)]
