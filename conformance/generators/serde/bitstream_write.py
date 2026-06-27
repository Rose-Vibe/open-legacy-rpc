import math
import os
import random
import struct
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

OP_SPECS = {
    'writeU8': {'args': ['value'], 'range': (0, 255)},
    'writeU16BE': {'args': ['value'], 'range': (0, 65535)},
    'writeI16BE': {'args': ['value'], 'range': (-32768, 32767)},
    'writeU32BE': {'args': ['value'], 'range': (0, 0xFFFFFFFF)},
    'writeI32BE': {'args': ['value'], 'range': (-2147483648, 2147483647)},
    'writeFloatBE': {'args': ['value'], 'float': True},
    'writeDoubleBE': {'args': ['value'], 'double': True},
    'writeBool': {'args': ['value'], 'bool': True},
    'writeBit': {'args': ['value'], 'range': (0, 1)},
    'writeBits': {'args': ['value', 'count']},
    'writeBytes': {'args': ['dataHex']},
    'writeCompressedU32': {'args': ['value'], 'range': (0, 0xFFFFFFFF)},
    'writeVector3': {'args': ['x', 'y', 'z'], 'float': True},
    'writeQuaternion': {'args': ['x', 'y', 'z', 'w'], 'float': True},
    'writeAlignedBytes': {'args': ['dataHex']},
    'writeChar': {'args': ['value']},
}

PRESET_TESTS = [
    {
        'name': "Single writeU8(0)",
        'desc': "Minimal byte write",
        'ops': [{'op': 'writeU8', 'value': 0}],
    },
    {
        'name': "writeU8(255)",
        'desc': "Full byte",
        'ops': [{'op': 'writeU8', 'value': 255}],
    },
    {
        'name': "writeBool(true) + writeU8(42)",
        'desc': "Bit-misaligned byte write",
        'ops': [{'op': 'writeBool', 'value': True}, {'op': 'writeU8', 'value': 42}],
    },
    {
        'name': "9 bits crossing byte boundary",
        'desc': "writeBit(1) x9",
        'ops': [{'op': 'writeBit', 'value': 1}] * 9,
    },
    {
        'name': "writeFloatBE(0.0)",
        'desc': "Float zero",
        'ops': [{'op': 'writeFloatBE', 'value': 0.0}],
    },
    {
        'name': "writeFloatBE(-1.0)",
        'desc': "Negative float",
        'ops': [{'op': 'writeFloatBE', 'value': -1.0}],
    },
    {
        'name': "writeDoubleBE(3.141592653589793)",
        'desc': "Double precision pi",
        'ops': [{'op': 'writeDoubleBE', 'value': 3.141592653589793}],
    },
    {
        'name': "writeAlignedBytes after 3 bits",
        'desc': "Alignment padding",
        'ops': [
            {'op': 'writeBits', 'value': 5, 'count': 3},
            {'op': 'writeAlignedBytes', 'dataHex': 'deadbeef'},
        ],
    },
    {
        'name': "writeVector3(1.0, 2.0, 3.0)",
        'desc': "Compound Vector3",
        'ops': [{'op': 'writeVector3', 'x': 1.0, 'y': 2.0, 'z': 3.0}],
    },
    {
        'name': "writeQuaternion(0, 0, 0, 1)",
        'desc': "Identity quaternion",
        'ops': [{'op': 'writeQuaternion', 'x': 0.0, 'y': 0.0, 'z': 0.0, 'w': 1.0}],
    },
    {
        'name': "writeI32BE(-1)",
        'desc': "Signed negative",
        'ops': [{'op': 'writeI32BE', 'value': -1}],
    },
    {
        'name': "writeI16BE(-32768)",
        'desc': "Signed min",
        'ops': [{'op': 'writeI16BE', 'value': -32768}],
    },
    {
        'name': "writeBits(0x1F, 5)",
        'desc': "Arbitrary 5-bit value",
        'ops': [{'op': 'writeBits', 'value': 0x1F, 'count': 5}],
    },
    {
        'name': "writeBytes(4 bytes)",
        'desc': "Raw bytes write",
        'ops': [{'op': 'writeBytes', 'dataHex': 'cafebabe'}],
    },
    {
        'name': "writeChar('Z')",
        'desc': "Single char write",
        'ops': [{'op': 'writeChar', 'value': 'Z'}],
    },
    {
        'name': "writeCompressedU32(0) + writeU8(0xFF)",
        'desc': "Compressed zero then full byte",
        'ops': [
            {'op': 'writeCompressedU32', 'value': 0},
            {'op': 'writeU8', 'value': 0xFF},
        ],
    },
]


def generate(mode, count=10, rng=None):
    if mode == 'basic':
        return _generate_basic()
    return _generate_random(count, rng or random.Random())


def _generate_basic():
    tests = []
    for preset in PRESET_TESTS:
        tests.append({
            'testInfo': {
                'testId': str(uuid.uuid4()),
                'testName': preset['name'],
                'testDescription': preset['desc'],
                'category': 'bitstream',
                'mode': 'basic',
            },
            'input': {'operations': preset['ops']},
        })
    return tests


def _random_op(rng):
    op_name = rng.choice(list(OP_SPECS.keys()))
    spec = OP_SPECS[op_name]
    op = {'op': op_name}

    if op_name == 'writeBits':
        count = rng.randint(1, 32)
        op['count'] = count
        op['value'] = rng.randint(0, (1 << count) - 1)
    elif op_name == 'writeBytes' or op_name == 'writeAlignedBytes':
        length = rng.randint(0, 16)
        op['dataHex'] = bytes(rng.randint(0, 255) for _ in range(length)).hex()
    elif op_name == 'writeChar':
        op['value'] = chr(rng.randint(32, 126))
    elif op_name in ('writeVector3',):
        op['x'] = _random_float(rng)
        op['y'] = _random_float(rng)
        op['z'] = _random_float(rng)
    elif op_name == 'writeQuaternion':
        op['x'] = _random_float(rng)
        op['y'] = _random_float(rng)
        op['z'] = _random_float(rng)
        op['w'] = _random_float(rng)
    elif spec.get('bool'):
        op['value'] = rng.choice([True, False])
    elif spec.get('float'):
        op['value'] = _random_float(rng)
    elif spec.get('double'):
        op['value'] = _random_double(rng)
    elif 'range' in spec:
        lo, hi = spec['range']
        op['value'] = rng.randint(lo, hi)

    return op


def _random_float(rng):
    return struct.unpack('>f', struct.pack('>f', rng.uniform(-1000, 1000)))[0]


def _random_double(rng):
    return rng.uniform(-1e10, 1e10)


def _generate_random(count, rng):
    tests = []
    for i in range(count):
        num_ops = rng.randint(1, 10)
        ops = [_random_op(rng) for _ in range(num_ops)]
        tests.append({
            'testInfo': {
                'testId': str(uuid.uuid4()),
                'testName': f"bitstream(random:{i})",
                'testDescription': f"Random {num_ops} operations",
                'category': 'bitstream',
                'mode': 'random',
            },
            'input': {'operations': ops},
        })
    return tests
