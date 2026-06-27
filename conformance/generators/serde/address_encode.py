import random
import uuid

PRESET_TESTS = [
    ('127.0.0.1', 7777, "Loopback"),
    ('0.0.0.0', 0, "All zeros"),
    ('255.255.255.255', 65535, "All ones"),
    ('192.168.1.100', 23466, "Typical LAN + master server port"),
]


def generate(mode, count=10, rng=None):
    if mode == 'basic':
        return _generate_basic()
    return _generate_random(count, rng or random.Random())


def _generate_basic():
    return [{
        'testInfo': {
            'testId': str(uuid.uuid4()),
            'testName': f"addressEncode({ip}:{port})",
            'testDescription': desc,
            'category': 'addressEncode',
            'mode': 'basic',
        },
        'input': {'ip': ip, 'port': port},
    } for ip, port, desc in PRESET_TESTS]


def _generate_random(count, rng):
    return [{
        'testInfo': {
            'testId': str(uuid.uuid4()),
            'testName': f"addressEncode(random:{i})",
            'testDescription': "Random IP:port",
            'category': 'addressEncode',
            'mode': 'random',
        },
        'input': {
            'ip': f"{rng.randint(0,255)}.{rng.randint(0,255)}.{rng.randint(0,255)}.{rng.randint(0,255)}",
            'port': rng.randint(0, 65535),
        },
    } for i in range(count)]
