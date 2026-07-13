#!/usr/bin/env python3
"""Decode a pcap file into structured JSON: RakNet → Unity → game-specific.

Usage:
    python3 tools/decode_pcap.py capture.pcap [--config config.json] [--compact]
    cat config.json | python3 tools/decode_pcap.py capture.pcap
"""
import argparse
import json
import math
import struct
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from protocol.pcap_reader import read_pcap
from protocol.raknet import parse_datagram, Reliability, is_offline_message
from protocol.unity_protocol import (
    decode_rpc, decode_batch_index, decode_state_sync, is_rpc,
    MSG_ID_RPC, MSG_ID_BATCH_INDEX, METHOD_SIGNATURES, RPCMode,
    compute_method_tag,
)
from protocol.master_serialization import (
    ID_DATABASE_QUERY_REQUEST, ID_DATABASE_UPDATE_ROW, ID_DATABASE_REMOVE_ROW,
    ID_DATABASE_QUERY_REPLY, ID_DATABASE_UNKNOWN_TABLE, ID_DATABASE_INCORRECT_PASSWORD,
    ID_DATABASE_ROWID, ID_MASTERSERVER_REDIRECT, ID_MASTERSERVER_MSG,
    decode_query_request, decode_update_row, decode_remove_row, decode_query_reply,
)

CONNECTION_MSG_NAMES = {
    0x00: 'INTERNAL_PING',
    0x03: 'CONNECTED_PONG',
    0x04: 'CONNECTION_REQUEST',
    0x09: 'OPEN_CONNECTION_REQUEST',
    0x0A: 'OPEN_CONNECTION_REPLY',
    0x0E: 'CONNECTION_REQUEST_ACCEPTED',
    0x11: 'NEW_INCOMING_CONNECTION',
    0x13: 'DISCONNECTION_NOTIFICATION_LEGACY',
    0x15: 'DISCONNECTION_NOTIFICATION',
    0x17: 'CONNECTION_BANNED',
    0x81: 'UNITY_PLAYER_ASSIGNMENT',
    0x83: 'UNITY_PLAYER_READY',
}

MASTER_SERVER_MSG_NAMES = {
    ID_DATABASE_QUERY_REQUEST: 'DATABASE_QUERY_REQUEST',
    ID_DATABASE_UPDATE_ROW: 'DATABASE_UPDATE_ROW',
    ID_DATABASE_REMOVE_ROW: 'DATABASE_REMOVE_ROW',
    ID_DATABASE_QUERY_REPLY: 'DATABASE_QUERY_REPLY',
    ID_DATABASE_UNKNOWN_TABLE: 'DATABASE_UNKNOWN_TABLE',
    ID_DATABASE_INCORRECT_PASSWORD: 'DATABASE_INCORRECT_PASSWORD',
    ID_DATABASE_ROWID: 'DATABASE_ROWID',
    ID_MASTERSERVER_REDIRECT: 'MASTERSERVER_REDIRECT',
    ID_MASTERSERVER_MSG: 'MASTERSERVER_MSG',
}

MASTER_SERVER_DECODERS = {
    ID_DATABASE_QUERY_REQUEST: decode_query_request,
    ID_DATABASE_UPDATE_ROW: decode_update_row,
    ID_DATABASE_REMOVE_ROW: decode_remove_row,
    ID_DATABASE_QUERY_REPLY: decode_query_reply,
}

RELIABILITY_NAMES = {r.value: r.name for r in Reliability}


def decode_packet(raw, config):
    return decode_raknet(raw, config)


def decode_raknet(raw, config):
    parsed = parse_datagram(raw)
    kind = parsed[0]

    if kind == 'data':
        _, timestamp, seq, messages = parsed
        b_and_as = struct.unpack('>I', raw[1:5])[0] if len(raw) >= 5 else 0
        frames = [decode_frame(msg, config) for msg in messages]
        return {
            'type': 'datagram',
            'rawHex': raw.hex(),
            'bAndAs': b_and_as,
            'timestamp': timestamp,
            'sequenceNumber': seq,
            'frames': frames,
        }
    elif kind in ('ack', 'nak'):
        _, timestamp, ranges = parsed
        return {
            'type': kind,
            'rawHex': raw.hex(),
            'timestamp': timestamp,
            'ranges': [[lo, hi] for lo, hi in ranges],
        }
    elif kind == 'offline':
        _, first_byte, _ = parsed
        return {
            'type': 'offline',
            'rawHex': raw.hex(),
            'messageId': first_byte,
        }
    else:
        return {
            'type': 'unknown',
            'rawHex': raw.hex(),
        }


def decode_frame(msg, config):
    reliability_name = RELIABILITY_NAMES.get(msg.reliability, f'UNKNOWN_{msg.reliability}')

    split = None
    if msg.split_packet_count and msg.split_packet_count > 0:
        split = {
            'count': msg.split_packet_count,
            'id': msg.split_packet_id,
            'index': msg.split_packet_index,
        }

    unity = None
    if msg.payload:
        if split is None:
            try:
                unity = decode_unity(msg.payload, msg.bit_length, config)
            except Exception as e:
                unity = {
                    'type': 'decode_error',
                    'rawHex': msg.payload.hex(),
                    'msgId': msg.payload[0] if msg.payload else None,
                    'error': str(e),
                }

    return {
        'rawHex': msg.payload.hex() if msg.payload else '',
        'bitLength': msg.bit_length,
        'reliability': reliability_name,
        'reliableMsgNumber': msg.reliable_msg_number,
        'orderingChannel': msg.ordering_channel,
        'orderingIndex': msg.ordering_index,
        'split': split,
        'unity': unity,
    }


def decode_unity(payload, bit_length, config):
    if not payload:
        return {'type': 'unknown', 'rawHex': '', 'msgId': None}

    msg_id = payload[0]

    if msg_id == MSG_ID_BATCH_INDEX:
        return decode_batch_index_layer(payload)

    if msg_id == MSG_ID_RPC:
        if is_rpc(payload):
            try:
                return decode_rpc_layer(payload, bit_length, config)
            except Exception:
                return _partial_rpc(payload, bit_length)
        else:
            return decode_state_sync_layer(payload, bit_length)

    if msg_id in CONNECTION_MSG_NAMES:
        return {
            'type': 'connection',
            'rawHex': payload.hex(),
            'msgId': msg_id,
            'messageName': CONNECTION_MSG_NAMES[msg_id],
        }

    if msg_id in MASTER_SERVER_MSG_NAMES:
        return decode_master_server_layer(payload, msg_id)

    return {'type': 'unknown', 'rawHex': payload.hex(), 'msgId': msg_id}


def decode_rpc_layer(payload, bit_length, config):
    decoded = decode_rpc(payload, bit_length)

    method_name = decoded.get('method_name')
    if method_name and method_name.startswith('unknown'):
        method_name = None

    result = {
        'type': 'rpc',
        'rawHex': payload.hex(),
        'msgId': MSG_ID_RPC,
        'variant': 'first_use' if decoded.get('first_use') else 'subsequent_use',
        'timestampMs': decoded.get('timestamp_ms'),
        'rpcMode': RPCMode(decoded['rpc_mode']).name if isinstance(decoded.get('rpc_mode'), (int, RPCMode)) else str(decoded.get('rpc_mode', '')),
        'methodName': method_name,
    }

    target_view = decoded.get('target_view')
    if target_view is not None:
        result['targetView'] = target_view

    if decoded.get('first_use'):
        if 'class_guid' in decoded:
            result['classGuid'] = decoded['class_guid']
        if 'method_hash' in decoded:
            result['methodHash'] = decoded['method_hash']
        method_tag = decoded.get('method_tag')
        if method_tag is not None:
            result['methodTag'] = method_tag
            if method_name:
                expected_tag = compute_method_tag(method_name)
                result['methodTagExpected'] = expected_tag
                result['methodTagMatch'] = (method_tag == expected_tag)
    else:
        method_idx = decoded.get('method_index')
        if method_idx is not None:
            result['methodIndex'] = method_idx

    if 'params' in decoded:
        sig = _get_signature(decoded.get('method_name', ''), config)
        params = []
        for i, val in enumerate(decoded['params']):
            param_type = sig[i] if sig and i < len(sig) else 'unknown'
            params.append({
                'type': 'deserialized',
                'paramType': param_type,
                'value': _json_safe(val),
            })
        result['params'] = params
    else:
        remaining = _rpc_remaining_hex(payload, bit_length, decoded)
        result['params'] = [{
            'type': 'not_deserialized',
            'rawHex': remaining,
        }] if remaining else []

    return result



def _partial_rpc(payload, bit_length):
    """Best-effort RPC decode when decode_rpc() throws."""
    from protocol.bitstream import BitStream
    bs = BitStream(payload, bit_length)
    result = {
        'type': 'rpc',
        'rawHex': payload.hex(),
        'msgId': MSG_ID_RPC,
        'methodName': None,
        'params': [{'type': 'not_deserialized', 'rawHex': payload[1:].hex()}],
    }
    try:
        bs.read_u8()  # msg_id
        ts_hi = bs.read_bits(32)
        ts_lo = bs.read_bits(32)
        result['timestampMs'] = (ts_hi << 32) | ts_lo
        bs.read_bits(8)  # marker
        first_use = bs.read_bit()
        result['variant'] = 'first_use' if first_use else 'subsequent_use'
        if not first_use:
            bs.pos = 81
            low7 = bs.read_bits(7)
            bs.pos = 89
            ext_bit = bs.read_bit()
            result['methodIndex'] = low7 | (ext_bit << 7)
    except Exception:
        pass
    return result


def _get_signature(method_name, config):
    if method_name in METHOD_SIGNATURES:
        return METHOD_SIGNATURES[method_name]
    custom = config.get('methodSignatures', {})
    if method_name in custom:
        return custom[method_name]
    return None


def _rpc_remaining_hex(payload, bit_length, decoded):
    """Extract remaining payload bytes after the RPC header (mode + optional player bit)."""
    if decoded.get('first_use'):
        hash_hex = decoded.get('method_hash', '')
        hash_extra_bits = len(hash_hex) * 4
        mode_start = 160 + hash_extra_bits + 52
    else:
        header_extra = 4 if (decoded.get('method_index') or 0) >= 128 else 0
        mode_start = 136 + header_extra

    params_start_bit = mode_start + 4
    if decoded.get('rpc_mode') == RPCMode.Player:
        params_start_bit += 1

    params_start_byte = params_start_bit // 8
    total_bytes = math.ceil(bit_length / 8)
    if params_start_byte >= total_bytes:
        return ''
    return payload[params_start_byte:total_bytes].hex()


def decode_state_sync_layer(payload, bit_length):
    decoded = decode_state_sync(payload, bit_length)
    data_bits = decoded.get('data_bit_length', 0)
    data_start_byte = 12
    data_end_byte = math.ceil((96 + data_bits) / 8)
    data_hex = payload[data_start_byte:data_end_byte].hex() if data_bits > 0 else ''

    return {
        'type': 'state_sync',
        'rawHex': payload.hex(),
        'msgId': MSG_ID_RPC,
        'viewId': decoded.get('view_id'),
        'viewIdScope': decoded.get('view_id_scope'),
        'timestampMs': decoded.get('timestamp'),
        'isFirst': decoded.get('is_first', False),
        'data': {
            'type': 'not_deserialized',
            'rawHex': data_hex,
        },
    }


def decode_batch_index_layer(payload):
    decoded = decode_batch_index(payload)
    if decoded is None:
        return {
            'type': 'batch_index',
            'rawHex': payload.hex(),
            'msgId': MSG_ID_BATCH_INDEX,
            'methodName': None,
            'methodIndex': None,
            'error': 'decode failed',
        }
    return {
        'type': 'batch_index',
        'rawHex': payload.hex(),
        'msgId': MSG_ID_BATCH_INDEX,
        'methodName': decoded.get('method_name'),
        'methodIndex': decoded.get('method_index'),
    }


def decode_master_server_layer(payload, msg_id):
    result = {
        'type': 'master_server',
        'rawHex': payload.hex(),
        'msgId': msg_id,
        'messageName': MASTER_SERVER_MSG_NAMES[msg_id],
    }
    decoder = MASTER_SERVER_DECODERS.get(msg_id)
    if decoder:
        try:
            decoded = decoder(payload)
            result['decoded'] = _json_safe(decoded)
        except Exception as e:
            result['decodeError'] = str(e)
    return result


def _json_safe(val):
    """Make a value JSON-serializable."""
    if isinstance(val, bytes):
        return val.hex()
    if isinstance(val, (list, tuple)):
        return [_json_safe(v) for v in val]
    if isinstance(val, dict):
        return {k: _json_safe(v) for k, v in val.items()
                if not k.startswith('_') and k != 'data_stream'}
    if isinstance(val, float):
        if math.isnan(val) or math.isinf(val):
            return str(val)
        return val
    if isinstance(val, RPCMode):
        return val.name
    return val


def _view_name(view_id, config):
    if view_id is None:
        return None
    names = config.get('viewNames', {})
    return names.get(str(view_id))


def load_config(args):
    if args.config:
        with open(args.config) as f:
            return json.load(f)
    if not sys.stdin.isatty():
        text = sys.stdin.read().strip()
        if text:
            return json.loads(text)
    return {}


def main():
    parser = argparse.ArgumentParser(
        description='Decode pcap to structured JSON (RakNet → Unity → game)')
    parser.add_argument('pcap', help='Path to pcap/pcapng file')
    parser.add_argument('--config', help='Path to JSON config file')
    parser.add_argument('--compact', action='store_true',
                        help='Output compact JSON (no indentation)')
    args = parser.parse_args()

    config = load_config(args)
    server_port = config.get('serverPort')

    if config.get('methodSignatures'):
        for name, sig in config['methodSignatures'].items():
            if name not in METHOD_SIGNATURES:
                METHOD_SIGNATURES[name] = sig

    packets = []
    for i, (ts, src_port, dst_port, udp_payload) in enumerate(read_pcap(args.pcap)):
        if not udp_payload:
            continue

        if server_port is not None:
            if dst_port == server_port:
                direction = 'client_to_server'
            elif src_port == server_port:
                direction = 'server_to_client'
            else:
                direction = 'unknown'
        else:
            direction = 'unknown'

        packets.append({
            'index': i,
            'timestamp': ts,
            'direction': direction,
            'srcPort': src_port,
            'dstPort': dst_port,
            'rawHex': udp_payload.hex(),
            'raknet': decode_packet(udp_payload, config),
        })

    indent = None if args.compact else 2
    json.dump({'packets': packets}, sys.stdout, indent=indent)
    sys.stdout.write('\n')


if __name__ == '__main__':
    main()
