#!/usr/bin/env python3
"""
Decode Unity legacy networking RPC wire format from pcap captures.

RPC Message Format (msg_id = 0x1b):
  bits 0-7:     msg_id (0x1b)
  bits 8-71:    u64 BE senderRakNetGetTimeMS (server uptime in ms)
  bits 72-79:   constant marker 0x0b
  bit 80:       first_use flag (1=includes method name hash, 0=uses cached index)

  If first_use=1:
    bits 81+:   method name length indicator + class GUID (0c93b276d5b1) + method hash
    then:       RPCMode (4 bits) + parameters

  If first_use=0 (subsequent):
    bits 81-87:   7-bit method index
    bits 88-103:  zeros (16 bits)
    bits 104-119: remaining_bit_count = total_bit_length - 121 (16 bits BE)
    bits 120-135: metadata (16 bits, constant 0x0002)
    bits 136-139: RPCMode (4 bits)
    bits 140+:    parameters (to end of message)

  RPCMode values: 0=Server, 1=Others, 2=All, 5=OthersBuffered, 6=AllBuffered

Parameter encoding by type:
  int:        32-bit BE signed integer
  float:      32-bit BE IEEE 754 float
  string:     WriteCompressed<uint32>(stringBitLength) + Huffman-encoded data
              WriteCompressed uses big-endian byte order on wire (DoEndianSwap=true).
              Huffman uses RakNet StringCompressor with englishCharacterFrequencies.
              EncodeArray pads output to byte alignment.
  Vector3:    3 × 32-bit BE floats (x, y, z)
  Quaternion: 4 × 32-bit BE floats (x, y, z, w)
  byte[]:     uint32_be(byte_count) + raw bytes
"""
import os
import struct

from .huffman import decode_string, get_tree
from .pcap_reader import read_pcap
from .raknet import parse_datagram

RPCMODE_NAMES = {0: 'Server', 1: 'Others', 2: 'All', 5: 'OthersBuffered', 6: 'AllBuffered'}

METHOD_INDEX_MAP = {
    0x54: 'RPC_Int',
    0x58: 'RPC_Float',
    0x5c: 'RPC_String',
    0x60: 'RPC_Vector3',
    0x64: 'RPC_Quaternion',
    0x68: 'RPC_Bytes',
    0x6c: 'RPC_IntFloatString',
}

CLASS_GUID = bytes.fromhex('0c93b276d5b1')

METHOD_SIGNATURES = {
    'RPC_Int': ['int'],
    'RPC_Float': ['float'],
    'RPC_String': ['string'],
    'RPC_Vector3': ['Vector3'],
    'RPC_Quaternion': ['Quaternion'],
    'RPC_Bytes': ['bytes'],
    'RPC_IntFloatString': ['int', 'float', 'string'],
    'RPC_Alpha': ['int'],
    'RPC_Beta': ['int'],
    'RPC_Gamma': ['int'],
}

METHOD_HASH_MAP = {
    'd456': 'RPC_Int',
    '564a1a': 'RPC_Float',
    'ab2f2853': 'RPC_String',
    '55e145c655e0': 'RPC_Vector3',
    '55dadac64920': 'RPC_Quaternion',
    'a857636a': 'RPC_Bytes',
    'd456ac9435d5979429': 'RPC_IntFloatString',
    '54929865': 'RPC_Alpha',
    'a80b65': 'RPC_Beta',
    '569b4d19': 'RPC_Gamma',
}


class BitReader:
    def __init__(self, data, total_bits=None):
        self.data = data
        self.pos = 0
        self.total_bits = total_bits or len(data) * 8

    @property
    def remaining(self):
        return self.total_bits - self.pos

    def read_bits(self, n):
        val = 0
        for _ in range(n):
            byte_idx = self.pos // 8
            bit_idx = 7 - (self.pos % 8)
            val = (val << 1) | ((self.data[byte_idx] >> bit_idx) & 1)
            self.pos += 1
        return val

    def read_bit(self):
        return self.read_bits(1)

    def read_u8(self):
        return self.read_bits(8)

    def read_u16_be(self):
        return self.read_bits(16)

    def read_u32_be(self):
        return self.read_bits(32)

    def read_i32_be(self):
        v = self.read_u32_be()
        return v - 0x100000000 if v >= 0x80000000 else v

    def read_float_be(self):
        bits = self.read_u32_be()
        return struct.unpack('>f', struct.pack('>I', bits))[0]

    def read_bytes_aligned(self, n):
        result = bytearray()
        for _ in range(n):
            result.append(self.read_bits(8))
        return bytes(result)

    def read_bits_as_str(self, n):
        """Read n bits and return as a string of '0'/'1' characters."""
        result = []
        for _ in range(n):
            byte_idx = self.pos // 8
            bit_idx = 7 - (self.pos % 8)
            result.append('1' if (self.data[byte_idx] >> bit_idx) & 1 else '0')
            self.pos += 1
        return ''.join(result)

    def read_compressed_uint32(self):
        """Read a WriteCompressed<uint32> with big-endian encoding on wire.

        RakNet processes bytes from the LSB end (data[currentByte] with
        currentByte starting at sizeInBits/8 - 1). For each zero byte,
        a flag=1 is written and the byte is skipped. A flag=0 means
        the byte is non-zero and all remaining bytes are written raw.

        For the last byte (MSB), there's a half-byte optimization:
        if the top nibble is zero, flag=1 and only the bottom 4 bits
        are written. Otherwise flag=0 and all 8 bits are written.
        """
        for byte_idx in range(3, 0, -1):
            flag = self.read_bit()
            if flag:
                continue
            n_bits = (byte_idx + 1) * 8
            raw = self.read_bits(n_bits)
            return raw
        flag = self.read_bit()
        if flag:
            return self.read_bits(4) << 24
        return self.read_bits(8) << 24


def decode_rpc(payload, bit_length):
    """Decode a Unity RPC message payload."""
    br = BitReader(payload, bit_length)
    result = {}

    result['msg_id'] = br.read_u8()
    ts_hi = br.read_bits(32)
    ts_lo = br.read_bits(32)
    result['timestamp_ms'] = (ts_hi << 32) | ts_lo
    br.read_bits(8)  # 0x0b marker

    first_use = br.read_bit()
    result['first_use'] = bool(first_use)

    if first_use:
        _decode_first_use(br, result, bit_length)
    else:
        _decode_subsequent(br, result, bit_length)

    return result


def _decode_first_use(br, result, bit_length):
    """Decode a first-use RPC (includes method name hash)."""
    br.read_bits(7)  # method ref bits

    length_indicator_pos = 13 * 8
    br.pos = length_indicator_pos
    length_indicator = br.read_u8()
    method_id_bits = length_indicator * 4
    result['method_id_bit_length'] = method_id_bits

    guid_data = br.read_bytes_aligned(6)
    result['class_guid'] = guid_data.hex()
    result['class_guid_matches'] = guid_data == CLASS_GUID

    remaining_method_bytes = (method_id_bits - 48) // 8
    if remaining_method_bytes > 0:
        method_hash = br.read_bytes_aligned(remaining_method_bytes)
        result['method_hash'] = method_hash.hex()
        if method_hash.hex() in METHOD_HASH_MAP:
            result['method_name'] = METHOD_HASH_MAP[method_hash.hex()]

    hb = method_id_bits - 48
    param_start = 160 + hb + 52 + 4
    mode_start = param_start - 4

    if mode_start < bit_length:
        br.pos = mode_start
        result['rpc_mode'] = br.read_bits(4)
        result['rpc_mode_name'] = RPCMODE_NAMES.get(result['rpc_mode'], '?')
        _decode_params(br, result, bit_length)


def _decode_subsequent(br, result, bit_length):
    """Decode a subsequent RPC (uses cached method index)."""
    br.pos = 80
    method_index_byte = br.read_bits(8) & 0xFE
    result['method_index_byte'] = hex(method_index_byte)
    result['method_name'] = METHOD_INDEX_MAP.get(method_index_byte, f'unknown_0x{method_index_byte:02x}')

    br.pos = 136
    result['rpc_mode'] = br.read_bits(4)
    result['rpc_mode_name'] = RPCMODE_NAMES.get(result['rpc_mode'], '?')

    _decode_params(br, result, bit_length)


def _decode_params(br, result, bit_length):
    """Decode RPC parameters starting at br.pos."""
    param_bits = bit_length - br.pos
    method = result.get('method_name', '')

    if param_bits == 0:
        return

    sig = METHOD_SIGNATURES.get(method)
    if sig and len(sig) > 1:
        _decode_typed_params(br, result, bit_length, sig)
        return

    if param_bits == 32:
        raw_u32 = br.read_bits(32)
        result['param_u32'] = raw_u32
        result['param_i32'] = raw_u32 - 0x100000000 if raw_u32 >= 0x80000000 else raw_u32
        result['param_float'] = struct.unpack('>f', struct.pack('>I', raw_u32))[0]
    elif param_bits == 96:
        result['param_vector3'] = (br.read_float_be(), br.read_float_be(), br.read_float_be())
    elif param_bits == 128:
        result['param_quaternion'] = (br.read_float_be(), br.read_float_be(),
                                      br.read_float_be(), br.read_float_be())
    elif method == 'RPC_String' or (sig and sig == ['string']):
        _try_decode_string_param(br, result, bit_length)
    elif method == 'RPC_Bytes' or (sig and sig == ['bytes']):
        byte_count = br.read_u32_be()
        data = br.read_bytes_aligned(byte_count)
        result['param_byte_count'] = byte_count
        result['param_bytes'] = data.hex()
    elif not method and param_bits > 32:
        _try_decode_generic_param(br, result, bit_length, param_bits)
    else:
        result['param_bits'] = param_bits
        param_data_bytes = (param_bits + 7) // 8
        result['param_raw'] = br.read_bytes_aligned(param_data_bytes).hex()


def _decode_typed_params(br, result, bit_length, sig):
    """Decode RPC parameters using a known method signature."""
    params = []
    for i, ptype in enumerate(sig):
        if ptype == 'int':
            params.append(('int', br.read_i32_be()))
        elif ptype == 'float':
            params.append(('float', br.read_float_be()))
        elif ptype == 'string':
            string_bit_length = br.read_compressed_uint32()
            if string_bit_length == 0:
                params.append(('string', ''))
            else:
                huffman_bits = br.read_bits_as_str(string_bit_length)
                tree = get_tree()
                decoded = decode_string(huffman_bits, tree)
                params.append(('string', decoded.decode('ascii', errors='replace')))
        elif ptype == 'Vector3':
            params.append(('Vector3', (br.read_float_be(), br.read_float_be(), br.read_float_be())))
        elif ptype == 'Quaternion':
            params.append(('Quaternion', (br.read_float_be(), br.read_float_be(),
                                          br.read_float_be(), br.read_float_be())))
        elif ptype == 'bytes':
            byte_count = br.read_u32_be()
            data = br.read_bytes_aligned(byte_count)
            params.append(('bytes', data.hex()))
    result['params'] = params


def _try_decode_generic_param(br, result, bit_length, param_bits):
    """Try to decode params for first-use RPCs where method name is unknown."""
    save_pos = br.pos
    try:
        first_u32 = br.read_u32_be()
        remaining = param_bits - 32
        if first_u32 > 0 and first_u32 * 8 <= remaining:
            data = br.read_bytes_aligned(first_u32)
            result['param_byte_count'] = first_u32
            result['param_bytes'] = data.hex()
            return
    except (IndexError, struct.error):
        pass

    br.pos = save_pos
    try:
        _try_decode_string_param(br, result, bit_length)
    except (IndexError, ValueError):
        br.pos = save_pos
        result['param_bits'] = param_bits
        param_data_bytes = (param_bits + 7) // 8
        result['param_raw'] = br.read_bytes_aligned(param_data_bytes).hex()


def _try_decode_string_param(br, result, bit_length):
    """Decode a string parameter using Huffman encoding."""
    string_bit_length = br.read_compressed_uint32()
    result['string_bit_length'] = string_bit_length

    if string_bit_length == 0:
        result['param_string'] = ''
        return

    huffman_bits = br.read_bits_as_str(string_bit_length)
    tree = get_tree()
    decoded = decode_string(huffman_bits, tree)
    result['param_string'] = decoded.decode('ascii', errors='replace')


def extract_and_decode_rpcs(pcap_path, server_port=7777):
    """Extract and decode all RPCs from a pcap."""
    results = []
    for ts, src, dst, payload in read_pcap(pcap_path):
        result = parse_datagram(payload)
        if result[0] != 'data':
            continue
        direction = 'C->S' if dst == server_port else 'S->C'
        for msg in result[3]:
            if msg.payload and msg.payload[0] == 0x1b:
                decoded = decode_rpc(msg.payload, msg.bit_length)
                decoded['direction'] = direction
                decoded['bit_length'] = msg.bit_length
                results.append(decoded)
    return results


def main():
    captures_dir = 'captures'

    for pcap in sorted(os.listdir(captures_dir)):
        if not pcap.endswith('.pcap'):
            continue
        exp_name = pcap.split('-')[0]
        path = os.path.join(captures_dir, pcap)

        rpcs = extract_and_decode_rpcs(path)
        if not rpcs:
            continue

        print(f'=== {exp_name} ===')
        for i, r in enumerate(rpcs):
            parts = [f"  RPC {i + 1}: {r['direction']} {r['bit_length']}bits"]
            parts.append(f"ts={r.get('timestamp_ms', -1)}")

            if r.get('first_use'):
                parts.append('FIRST_USE')
                if 'class_guid_matches' in r:
                    parts.append('guid={}'.format('OK' if r['class_guid_matches'] else r.get('class_guid')))
                if 'method_hash' in r:
                    parts.append('method_hash={}'.format(r['method_hash']))
            else:
                parts.append('method={}'.format(r.get('method_name', '?')))

            if 'rpc_mode_name' in r:
                parts.append('mode={}'.format(r['rpc_mode_name']))

            if 'params' in r:
                for ptype, pval in r['params']:
                    if ptype == 'int':
                        parts.append(f'int={pval}')
                    elif ptype == 'float':
                        parts.append(f'float={pval:.6f}')
                    elif ptype == 'string':
                        parts.append(f'string={pval!r}')
                    elif ptype == 'Vector3':
                        parts.append('vec3=({:.3f}, {:.3f}, {:.3f})'.format(*pval))
                    elif ptype == 'Quaternion':
                        parts.append('quat=({:.3f}, {:.3f}, {:.3f}, {:.3f})'.format(*pval))
                    elif ptype == 'bytes':
                        parts.append(f'bytes={pval}')
            elif 'param_string' in r:
                parts.append('string={!r}'.format(r['param_string']))
            elif 'param_i32' in r:
                val = r['param_i32']
                fval = r['param_float']
                if abs(fval) > 1e-10 and abs(fval) < 1e10:
                    parts.append(f'param_i32={val} / float={fval:.6f}')
                else:
                    parts.append(f'param_i32={val}')
            elif 'param_vector3' in r:
                parts.append('vec3=({:.3f}, {:.3f}, {:.3f})'.format(*r['param_vector3']))
            elif 'param_quaternion' in r:
                parts.append('quat=({:.3f}, {:.3f}, {:.3f}, {:.3f})'.format(*r['param_quaternion']))
            elif 'param_bytes' in r:
                parts.append(f"bytes[{r['param_byte_count']}]={r['param_bytes']}")
            elif 'param_raw' in r:
                parts.append(f"param_raw={r['param_raw']} ({r.get('param_bits', 0)} bits)")

            print(' '.join(parts))
        print()


if __name__ == '__main__':
    main()
