"""Shared bitstream operation executor for validators and reference implementer."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from protocol.bitstream import BitStream


def execute_ops(operations):
    """Execute a list of write operations on a BitStream, return (hex, bit_length)."""
    bs = BitStream()
    for op in operations:
        _exec_write(bs, op)
    return bs.to_bytes().hex(), bs.bit_length


def execute_read_ops(data_hex, bit_length, operations):
    """Execute a list of read operations on a BitStream, return list of values."""
    bs = BitStream(bytes.fromhex(data_hex), bit_length=bit_length)
    values = []
    for op in operations:
        values.append(_exec_read(bs, op))
    return values


def _exec_write(bs, op):
    name = op['op']
    if name == 'writeU8':
        bs.write_u8(op['value'])
    elif name == 'writeU16BE':
        bs.write_u16_be(op['value'])
    elif name == 'writeI16BE':
        bs.write_i16_be(op['value'])
    elif name == 'writeU32BE':
        bs.write_u32_be(op['value'])
    elif name == 'writeI32BE':
        bs.write_i32_be(op['value'])
    elif name == 'writeFloatBE':
        bs.write_float_be(op['value'])
    elif name == 'writeDoubleBE':
        bs.write_double_be(op['value'])
    elif name == 'writeBool':
        bs.write_bool(op['value'])
    elif name == 'writeBit':
        bs.write_bit(op['value'])
    elif name == 'writeBits':
        bs.write_bits(op['value'], op['count'])
    elif name == 'writeBytes':
        bs.write_bytes(bytes.fromhex(op['dataHex']))
    elif name == 'writeCompressedU32':
        bs.write_compressed_u32(op['value'])
    elif name == 'writeVector3':
        bs.write_vector3(op['x'], op['y'], op['z'])
    elif name == 'writeQuaternion':
        bs.write_quaternion(op['x'], op['y'], op['z'], op['w'])
    elif name == 'writeAlignedBytes':
        bs.write_aligned_bytes(bytes.fromhex(op['dataHex']))
    elif name == 'writeChar':
        bs.write_char(op['value'])
    else:
        raise ValueError(f"Unknown write op: {name}")


def _exec_read(bs, op):
    name = op['op']
    if name == 'readU8':
        return bs.read_u8()
    elif name == 'readU16BE':
        return bs.read_u16_be()
    elif name == 'readI16BE':
        return bs.read_i16_be()
    elif name == 'readU32BE':
        return bs.read_u32_be()
    elif name == 'readI32BE':
        return bs.read_i32_be()
    elif name == 'readFloatBE':
        return bs.read_float_be()
    elif name == 'readDoubleBE':
        return bs.read_double_be()
    elif name == 'readBool':
        return bs.read_bool()
    elif name == 'readBit':
        return bs.read_bit()
    elif name == 'readBits':
        return bs.read_bits(op['count'])
    elif name == 'readBytes':
        return bs.read_bytes(op['count']).hex()
    elif name == 'readCompressedU32':
        return bs.read_compressed_u32()
    elif name == 'readVector3':
        x, y, z = bs.read_vector3()
        return {'x': x, 'y': y, 'z': z}
    elif name == 'readQuaternion':
        x, y, z, w = bs.read_quaternion()
        return {'x': x, 'y': y, 'z': z, 'w': w}
    elif name == 'readAlignedBytes':
        return bs.read_aligned_bytes(op['count']).hex()
    elif name == 'readChar':
        return bs.read_char()
    else:
        raise ValueError(f"Unknown read op: {name}")
