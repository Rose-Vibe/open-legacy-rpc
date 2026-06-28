"""Tests for the pcap decoder tool."""
import json
import math
import struct
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from protocol.raknet import Reliability
from protocol.unity_protocol import (
    encode_rpc_first_use, encode_rpc_subsequent, encode_batch_index,
    encode_state_sync, RPCMode, MSG_ID_RPC, MSG_ID_BATCH_INDEX,
)
from protocol.bitstream import BitStream
from tools.decode_pcap import (
    decode_packet, decode_raknet, decode_frame, decode_unity,
    decode_rpc_layer, decode_state_sync_layer, decode_batch_index_layer,
    _json_safe, load_config,
)


def _pack_datagram(seq, messages_raw, timestamp=0):
    """Build a minimal RakNet data datagram from raw encapsulated bytes."""
    header = bytes([0x84])
    b_and_as = struct.pack('>I', 0)
    ts = struct.pack('>I', timestamp)
    seq_bytes = bytes([seq & 0xFF, (seq >> 8) & 0xFF, (seq >> 16) & 0xFF])
    return header + b_and_as + ts + seq_bytes + messages_raw


def _pack_encapsulated(payload, reliability=Reliability.RELIABLE_ORDERED, channel=0):
    """Build encapsulated message bytes for a single payload."""
    header_byte = (reliability << 5)
    bit_length = len(payload) * 8
    result = bytes([header_byte]) + struct.pack('>H', bit_length)
    if reliability >= 2:  # reliable
        result += bytes([0, 0, 0])  # reliable_msg_number
    if reliability in (1, 3, 4):  # ordered/sequenced
        result += bytes([0, 0, 0])  # ordering_index
        result += bytes([channel])  # ordering_channel
    result += payload
    return result


def _pack_ack(ranges, timestamp=0):
    """Build a RakNet ACK packet."""
    header = bytes([0xC0])
    b_and_as = struct.pack('>I', 0)
    ts = struct.pack('>I', timestamp)
    count = struct.pack('>H', len(ranges))
    body = b''
    for lo, hi in ranges:
        if lo == hi:
            body += bytes([1]) + bytes([lo & 0xFF, (lo >> 8) & 0xFF, (lo >> 16) & 0xFF])
        else:
            body += bytes([0])
            body += bytes([lo & 0xFF, (lo >> 8) & 0xFF, (lo >> 16) & 0xFF])
            body += bytes([hi & 0xFF, (hi >> 8) & 0xFF, (hi >> 16) & 0xFF])
    return header + b_and_as + ts + count + body


# --- RakNet layer tests ---

def test_datagram_decode():
    inner = _pack_encapsulated(bytes([0x04, 0x01, 0x02]), Reliability.RELIABLE)
    raw = _pack_datagram(5, inner, timestamp=100)
    result = decode_raknet(raw, {})
    assert result['type'] == 'datagram'
    assert result['sequenceNumber'] == 5
    assert result['timestamp'] == 100
    assert result['bAndAs'] == 0
    assert len(result['frames']) == 1
    assert result['rawHex'] == raw.hex()


def test_ack_decode():
    raw = _pack_ack([(3, 3), (5, 10)], timestamp=42)
    result = decode_raknet(raw, {})
    assert result['type'] == 'ack'
    assert result['timestamp'] == 42
    assert result['ranges'] == [[3, 3], [5, 10]]
    assert result['rawHex'] == raw.hex()


def test_nak_decode():
    header = bytes([0xA0])
    b_and_as = struct.pack('>I', 0)
    ts = struct.pack('>I', 7)
    count = struct.pack('>H', 1)
    body = bytes([1, 2, 0, 0])
    raw = header + b_and_as + ts + count + body
    result = decode_raknet(raw, {})
    assert result['type'] == 'nak'
    assert result['timestamp'] == 7


def test_offline_decode():
    from protocol.raknet import OFFLINE_MESSAGE_MAGIC
    raw = bytes([0x05]) + OFFLINE_MESSAGE_MAGIC + bytes([0x00] * 5)
    result = decode_raknet(raw, {})
    assert result['type'] == 'offline'
    assert result['messageId'] == 0x05


def test_unknown_decode():
    raw = bytes([0x84, 0, 0, 0])
    result = decode_raknet(raw, {})
    assert result['type'] == 'unknown'


# --- Frame decode tests ---

def test_frame_reliability():
    inner = _pack_encapsulated(bytes([0x04, 0x01]), Reliability.UNRELIABLE)
    raw = _pack_datagram(0, inner)
    result = decode_raknet(raw, {})
    frame = result['frames'][0]
    assert frame['reliability'] == 'UNRELIABLE'
    assert frame['reliableMsgNumber'] is None
    assert frame['split'] is None


def test_frame_split():
    payload = bytes([0x1b, 0x00])

    def _make_split_enc(split_index):
        header_byte = (Reliability.RELIABLE_ORDERED << 5) | (1 << 4)  # has_split
        bit_length = len(payload) * 8
        enc = bytes([header_byte]) + struct.pack('>H', bit_length)
        enc += bytes([0, 0, 0])  # reliable_msg_number
        enc += bytes([0, 0, 0, 0])  # ordering_index + channel
        enc += struct.pack('>I', 3)  # split_count
        enc += struct.pack('>H', 7)  # split_id
        enc += struct.pack('>I', split_index)
        enc += payload
        return enc

    # Non-first fragment: unity is null
    raw = _pack_datagram(0, _make_split_enc(1))
    result = decode_raknet(raw, {})
    frame = result['frames'][0]
    assert frame['split'] == {'count': 3, 'id': 7, 'index': 1}
    assert frame['unity'] is None

    # First fragment: also null (can't decode partial payload)
    raw = _pack_datagram(0, _make_split_enc(0))
    result = decode_raknet(raw, {})
    frame = result['frames'][0]
    assert frame['split'] == {'count': 3, 'id': 7, 'index': 0}
    assert frame['unity'] is None


# --- Unity layer tests ---

def test_rpc_first_use_decode():
    data, bits = encode_rpc_first_use(
        'RPC_Int', [42], view_id=1, timestamp_ms=0, mode=RPCMode.Server,
        target_view=0x2000)
    result = decode_unity(data, bits, {})
    assert result['type'] == 'rpc'
    assert result['variant'] == 'first_use'
    assert result['methodName'] == 'RPC_Int'
    assert result['rpcMode'] == 'Server'
    assert len(result['params']) == 1
    assert result['params'][0]['type'] == 'deserialized'
    assert result['params'][0]['value'] == 42
    assert 'classGuid' in result
    assert 'methodHash' in result
    assert result['targetView'] == 0x2000


def test_rpc_subsequent_decode():
    data, bits = encode_rpc_subsequent(
        'RPC_Int', [99], view_id=1, timestamp_ms=5, mode=RPCMode.Others,
        target_view=0x2000)
    result = decode_unity(data, bits, {})
    assert result['type'] == 'rpc'
    assert result['variant'] == 'subsequent_use'
    assert result['methodName'] == 'RPC_Int'
    assert result['timestampMs'] == 5
    assert result['params'][0]['value'] == 99
    assert 'methodIndex' in result
    assert result['targetView'] == 0x2000


def test_rpc_unknown_signature():
    """RPC with unknown method produces not_deserialized params."""
    from protocol.unity_protocol import METHOD_INDEX_MAP, INDEX_TO_METHOD, METHOD_SIGNATURES
    METHOD_INDEX_MAP['FakeMethod'] = 126
    INDEX_TO_METHOD[126] = 'FakeMethod'
    try:
        data, bits = encode_rpc_subsequent(
            'FakeMethod', [], view_id=1, timestamp_ms=0, mode=RPCMode.Server,
            target_view=0x2000, method_index=126)
        result = decode_unity(data, bits, {})
        assert result['type'] == 'rpc'
        assert result['params'][0]['type'] == 'not_deserialized'
    finally:
        del METHOD_INDEX_MAP['FakeMethod']
        del INDEX_TO_METHOD[126]


def test_rpc_config_signature():
    """Config-provided method signatures are used for decoding."""
    config = {'methodSignatures': {'RPC_Int': ['int']}}
    data, bits = encode_rpc_subsequent(
        'RPC_Int', [77], view_id=1, timestamp_ms=0, mode=RPCMode.Server,
        target_view=0x2000)
    result = decode_unity(data, bits, config)
    assert result['params'][0]['type'] == 'deserialized'
    assert result['params'][0]['paramType'] == 'int'
    assert result['params'][0]['value'] == 77


def test_state_sync_decode():
    data_bs = BitStream()
    data_bs.write_u32_be(0xDEADBEEF)
    data, bits = encode_state_sync(1, 100, data_bs, is_first=True)
    result = decode_unity(data, bits, {})
    assert result['type'] == 'state_sync'
    assert result['viewId'] == 1
    assert result['isFirst'] is True
    assert result['timestamp'] == 100
    assert result['data']['type'] == 'not_deserialized'
    assert len(result['data']['rawHex']) > 0


def test_batch_index_decode():
    data, bits = encode_batch_index('RPC_Int', 0x60)
    result = decode_unity(data, bits, {})
    assert result['type'] == 'batch_index'
    assert result['methodName'] == 'RPC_Int'
    assert result['methodIndex'] == 0x60


def test_connection_message():
    payload = bytes([0x04, 0x01, 0x02, 0x03])
    result = decode_unity(payload, 32, {})
    assert result['type'] == 'connection'
    assert result['messageName'] == 'CONNECTION_REQUEST'
    assert result['msgId'] == 0x04


def test_unknown_message():
    payload = bytes([0xFF, 0x01, 0x02])
    result = decode_unity(payload, 24, {})
    assert result['type'] == 'unknown'
    assert result['msgId'] == 0xFF


# --- Config tests ---

def test_config_empty():
    import argparse
    args = argparse.Namespace(config=None)
    old_isatty = sys.stdin.isatty
    sys.stdin.isatty = lambda: True
    try:
        config = load_config(args)
        assert config == {}
    finally:
        sys.stdin.isatty = old_isatty


def test_config_from_file(tmp_path):
    config_path = tmp_path / 'config.json'
    config_path.write_text('{"serverPort": 9999}')
    import argparse
    args = argparse.Namespace(config=str(config_path))
    config = load_config(args)
    assert config['serverPort'] == 9999


# --- json_safe tests ---

def test_json_safe_bytes():
    assert _json_safe(b'\xde\xad') == 'dead'


def test_json_safe_nan():
    assert _json_safe(float('nan')) == 'nan'


def test_json_safe_nested():
    result = _json_safe({'a': b'\x01', 'b': [1, b'\x02'], '_private': 'hidden'})
    assert result == {'a': '01', 'b': [1, '02']}
    assert '_private' not in result


# --- Full pipeline test ---

def test_full_pipeline_rpc():
    """End-to-end: pack a datagram with an RPC, decode it."""
    rpc_data, rpc_bits = encode_rpc_subsequent(
        'RPC_Void', [], view_id=1, timestamp_ms=0, mode=RPCMode.Server,
        target_view=0x2000)
    enc = _pack_encapsulated(rpc_data, Reliability.RELIABLE_ORDERED)
    raw = _pack_datagram(0, enc)
    result = decode_raknet(raw, {})
    assert result['type'] == 'datagram'
    frame = result['frames'][0]
    assert frame['unity']['type'] == 'rpc'
    assert frame['unity']['methodName'] == 'RPC_Void'


def test_full_pipeline_state_sync():
    data_bs = BitStream()
    data_bs.write_float_be(3.14)
    sync_data, sync_bits = encode_state_sync(5, 200, data_bs)
    enc = _pack_encapsulated(sync_data, Reliability.UNRELIABLE_SEQUENCED)
    raw = _pack_datagram(0, enc)
    result = decode_raknet(raw, {})
    frame = result['frames'][0]
    assert frame['unity']['type'] == 'state_sync'
    assert frame['unity']['viewId'] == 5


def test_direction_detection():
    from tools.decode_pcap import main
    config = {'serverPort': 7777}
    rpc_data, _ = encode_rpc_subsequent(
        'RPC_Void', [], view_id=1, timestamp_ms=0, mode=RPCMode.Server,
        target_view=0x2000)
    enc = _pack_encapsulated(rpc_data, Reliability.RELIABLE_ORDERED)
    raw = _pack_datagram(0, enc)

    result = decode_packet(raw, config)
    assert result['type'] == 'datagram'


def test_view_names():
    """RPC no longer carries a view_id (bytes 1-8 are timestamp), so viewName is absent."""
    config = {'viewNames': {'1': 'Player'}}
    data, bits = encode_rpc_subsequent(
        'RPC_Int', [42], view_id=1, timestamp_ms=0, mode=RPCMode.Server,
        target_view=0x2000)
    result = decode_unity(data, bits, config)
    assert 'viewName' not in result


def test_rawHex_at_every_level():
    """Every layer should include rawHex."""
    rpc_data, _ = encode_rpc_subsequent(
        'RPC_Int', [1], view_id=1, timestamp_ms=0, mode=RPCMode.Server,
        target_view=0x2000)
    enc = _pack_encapsulated(rpc_data, Reliability.RELIABLE_ORDERED)
    raw = _pack_datagram(0, enc)
    result = decode_raknet(raw, {})
    assert 'rawHex' in result  # raknet level
    assert 'rawHex' in result['frames'][0]  # frame level
    assert 'rawHex' in result['frames'][0]['unity']  # unity level
