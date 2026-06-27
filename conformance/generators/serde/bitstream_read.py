import os
import random
import struct
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from protocol.bitstream import BitStream

WRITE_TO_READ = {
    'writeU8': 'readU8',
    'writeU16BE': 'readU16BE',
    'writeI16BE': 'readI16BE',
    'writeU32BE': 'readU32BE',
    'writeI32BE': 'readI32BE',
    'writeFloatBE': 'readFloatBE',
    'writeDoubleBE': 'readDoubleBE',
    'writeBool': 'readBool',
    'writeBit': 'readBit',
    'writeBits': 'readBits',
    'writeBytes': 'readBytes',
    'writeCompressedU32': 'readCompressedU32',
    'writeVector3': 'readVector3',
    'writeQuaternion': 'readQuaternion',
    'writeAlignedBytes': 'readAlignedBytes',
    'writeChar': 'readChar',
}

PRESET_TESTS = [
    {
        'name': "readU8",
        'desc': "Single byte read",
        'write_ops': [{'op': 'writeU8', 'value': 42}],
    },
    {
        'name': "readBool + readU8",
        'desc': "Bit-misaligned read",
        'write_ops': [{'op': 'writeBool', 'value': True}, {'op': 'writeU8', 'value': 42}],
    },
    {
        'name': "readFloatBE",
        'desc': "Float read",
        'write_ops': [{'op': 'writeFloatBE', 'value': 3.14}],
    },
    {
        'name': "readDoubleBE",
        'desc': "Double read",
        'write_ops': [{'op': 'writeDoubleBE', 'value': 2.718281828459045}],
    },
    {
        'name': "readI32BE negative",
        'desc': "Signed negative read",
        'write_ops': [{'op': 'writeI32BE', 'value': -12345}],
    },
    {
        'name': "readAlignedBytes after bits",
        'desc': "Alignment + aligned read",
        'write_ops': [
            {'op': 'writeBits', 'value': 7, 'count': 3},
            {'op': 'writeAlignedBytes', 'dataHex': 'aabb'},
        ],
    },
    {
        'name': "readVector3",
        'desc': "Vector3 compound read",
        'write_ops': [{'op': 'writeVector3', 'x': 1.0, 'y': 2.0, 'z': 3.0}],
    },
    {
        'name': "readQuaternion",
        'desc': "Quaternion compound read",
        'write_ops': [{'op': 'writeQuaternion', 'x': 0.0, 'y': 0.0, 'z': 0.0, 'w': 1.0}],
    },
]


def _write_ops_to_data(write_ops):
    from conformance.validators.serde._bitstream_exec import execute_ops
    return execute_ops(write_ops)


def _write_op_to_read_op(wop):
    rop = {'op': WRITE_TO_READ[wop['op']]}
    if wop['op'] == 'writeBits':
        rop['count'] = wop['count']
    elif wop['op'] in ('writeBytes', 'writeAlignedBytes'):
        rop['count'] = len(bytes.fromhex(wop['dataHex']))
    return rop


def generate(mode, count=10, rng=None):
    if mode == 'basic':
        return _generate_basic()
    return _generate_random(count, rng or random.Random())


def _generate_basic():
    tests = []
    for preset in PRESET_TESTS:
        data_hex, bit_length = _write_ops_to_data(preset['write_ops'])
        read_ops = [_write_op_to_read_op(w) for w in preset['write_ops']]
        tests.append({
            'testInfo': {
                'testId': str(uuid.uuid4()),
                'testName': preset['name'],
                'testDescription': preset['desc'],
                'category': 'bitstreamRead',
                'mode': 'basic',
            },
            'input': {
                'dataHex': data_hex,
                'bitLength': bit_length,
                'operations': read_ops,
            },
        })
    return tests


def _generate_random(count, rng):
    from conformance.generators.serde.bitstream_write import _random_op
    tests = []
    for i in range(count):
        num_ops = rng.randint(1, 8)
        write_ops = [_random_op(rng) for _ in range(num_ops)]
        data_hex, bit_length = _write_ops_to_data(write_ops)
        read_ops = [_write_op_to_read_op(w) for w in write_ops]
        tests.append({
            'testInfo': {
                'testId': str(uuid.uuid4()),
                'testName': f"bitstreamRead(random:{i})",
                'testDescription': f"Random {num_ops} read operations",
                'category': 'bitstreamRead',
                'mode': 'random',
            },
            'input': {
                'dataHex': data_hex,
                'bitLength': bit_length,
                'operations': read_ops,
            },
        })
    return tests
