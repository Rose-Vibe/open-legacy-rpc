#!/usr/bin/env python3
"""
Reference implementer for serde conformance tests.

Reads test cases from stdin, uses the Python reference implementation
to produce output, writes completed test objects to stdout.

Usage:
  legacy-net-serde-test generate writeCompressed basic | \
    python conformance/reference_implementer.py | \
    legacy-net-serde-test validate
"""

import json
import struct
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from protocol.bitstream import BitStream
from protocol.huffman import encode_string_for_wire, decode_string, get_tree
from protocol.master_serialization import (
    write_cell, read_cell, encode_update_row, decode_update_row,
    encode_query_request, decode_query_request, encode_query_reply,
    decode_query_reply, encode_remove_row, decode_remove_row,
    NUMERIC, STRING, BINARY,
)
from protocol.unity_protocol import (
    compute_method_id, compute_method_index,
    encode_rpc_subsequent, encode_rpc_first_use, decode_rpc,
    encode_view_id, encode_view_id_16,
    encode_state_sync, decode_state_sync,
    encode_delta_state_sync, decode_delta_state_sync,
    encode_batch_index, decode_batch_index,
    RPCMode, METHOD_INDEX_MAP, METHOD_SIGNATURES,
)
from protocol.raknet_transport import encode_address, decode_address
from conformance.validators.serde._bitstream_exec import execute_ops, execute_read_ops

TYPE_INT = {'NUMERIC': NUMERIC, 'STRING': STRING, 'BINARY': BINARY}
TYPE_STR = {NUMERIC: 'NUMERIC', STRING: 'STRING', BINARY: 'BINARY'}
MODE_MAP = {
    'Server': RPCMode.Server, 'Others': RPCMode.Others, 'All': RPCMode.All,
    'Player': RPCMode.Player, 'OthersBuffered': RPCMode.OthersBuffered,
    'AllBuffered': RPCMode.AllBuffered,
}
OP_INT = {
    'EQUAL': 0, 'NOT_EQUAL': 1, 'GREATER_THAN': 2, 'GREATER_THAN_EQ': 3,
    'LESS_THAN': 4, 'LESS_THAN_EQ': 5, 'IS_EMPTY': 6, 'NOT_EMPTY': 7,
}
OP_STR = {v: k for k, v in OP_INT.items()}


def process_writeCompressed(inp):
    bs = BitStream()
    bs.write_compressed_u32(inp['value'])
    return {'dataHex': bs.to_bytes().hex(), 'bitLength': bs.bit_length}


def process_readCompressed(inp):
    bs = BitStream(bytes.fromhex(inp['dataHex']), bit_length=inp['bitLength'])
    return {'value': bs.read_compressed_u32()}


def process_huffman(inp):
    s = bytes.fromhex(inp['stringHex']).decode('latin-1')
    if s == '':
        return {'dataHex': '', 'bitLength': 0}
    bits = encode_string_for_wire(s)
    data = int(bits, 2).to_bytes((len(bits) + 7) // 8, 'big')
    return {'dataHex': data.hex(), 'bitLength': len(bits)}


def process_huffmanDecode(inp):
    if inp['bitLength'] == 0:
        return {'stringHex': ''}
    data = bytes.fromhex(inp['dataHex'])
    bit_str = bin(int.from_bytes(data, 'big'))[2:].zfill(len(data) * 8)
    bit_str = bit_str[:inp['bitLength']]
    decoded = decode_string(bit_str, get_tree())
    return {'stringHex': decoded.hex()}


def process_bitstream(inp):
    hex_str, bits = execute_ops(inp['operations'])
    return {'dataHex': hex_str, 'bitLength': bits}


def process_bitstreamRead(inp):
    values = execute_read_ops(inp['dataHex'], inp['bitLength'], inp['operations'])
    return {'values': values}


def process_cell(inp):
    val = inp['value']
    ct = inp['cellType']
    if ct == 'BINARY' and isinstance(val, str):
        val = bytes.fromhex(val) if val else b''
    bs = BitStream()
    write_cell(bs, val, TYPE_INT[ct])
    return {'dataHex': bs.to_bytes().hex(), 'bitLength': bs.bit_length}


def process_cellDecode(inp):
    bs = BitStream(bytes.fromhex(inp['dataHex']), bit_length=inp['bitLength'])
    val = read_cell(bs, TYPE_INT[inp['cellType']])
    if isinstance(val, bytes):
        val = val.hex()
    return {'value': val}


def _cells_to_internal(cells):
    result = []
    for c in cells:
        val = c['value']
        if c['type'] == 'BINARY' and isinstance(val, str):
            val = bytes.fromhex(val)
        result.append({'name': c['name'], 'type': TYPE_INT[c['type']], 'value': val})
    return result


def process_updateRow(inp):
    cells = _cells_to_internal(inp['cells'])
    data = encode_update_row(inp['tableName'], cells, update_mode=inp['updateMode'],
                             row_id=inp['rowId'], password=inp['password'])
    return {'dataHex': data.hex()}


def process_updateRowDecode(inp):
    d = decode_update_row(bytes.fromhex(inp['dataHex']))
    cells = []
    for c in d['cells']:
        val = c['value']
        if isinstance(val, bytes):
            val = val.hex()
        cells.append({'name': c['name'], 'type': TYPE_STR[c['type']], 'value': val})
    return {
        'tableName': d['table'], 'updateMode': d['update_mode'],
        'rowId': d['row_id'], 'cells': cells,
    }


def process_queryRequest(inp):
    filters = []
    for f in inp.get('filters', []):
        filt = {'name': f['name'], 'type': TYPE_INT[f['type']], 'operation': OP_INT[f['operation']]}
        val = f.get('value')
        if val is not None and f['type'] == 'BINARY' and isinstance(val, str):
            val = bytes.fromhex(val)
        filt['value'] = val
        filters.append(filt)
    data = encode_query_request(
        inp['tableName'], column_subset=inp.get('columnSubset') or None,
        filters=filters or None, row_ids=inp.get('rowIds') or None,
        password=inp.get('password'),
    )
    return {'dataHex': data.hex()}


def process_queryRequestDecode(inp):
    d = decode_query_request(bytes.fromhex(inp['dataHex']))
    filters = []
    for f in d.get('filters', []):
        val = f.get('value')
        if isinstance(val, bytes):
            val = val.hex()
        filters.append({
            'name': f['name'], 'type': TYPE_STR.get(f['type'], str(f['type'])),
            'operation': OP_STR.get(f['operation'], str(f['operation'])), 'value': val,
        })
    return {
        'tableName': d['table'], 'columnSubset': d.get('column_subset', []),
        'filters': filters, 'rowIds': d.get('row_ids', []),
    }


def process_queryReply(inp):
    columns = [{'name': c['name'], 'type': TYPE_INT[c['type']]} for c in inp['columns']]
    rows = []
    for row in inp['rows']:
        cells = {}
        for col in inp['columns']:
            if col['name'] in row['cells']:
                val = row['cells'][col['name']]
                if col['type'] == 'BINARY' and isinstance(val, str):
                    val = bytes.fromhex(val)
                cells[col['name']] = val
        rows.append({'key': row['key'], 'cells': cells})
    data = encode_query_reply(columns, rows)
    return {'dataHex': data.hex()}


def process_queryReplyDecode(inp):
    d = decode_query_reply(bytes.fromhex(inp['dataHex']))
    columns = [{'name': c['name'], 'type': TYPE_STR[c['type']]} for c in d['columns']]
    rows = []
    for row in d['rows']:
        cells = {}
        for k, v in row['cells'].items():
            cells[k] = v.hex() if isinstance(v, bytes) else v
        rows.append({'key': row['key'], 'cells': cells})
    return {'columns': columns, 'rows': rows}


def process_removeRow(inp):
    data = encode_remove_row(inp['tableName'], inp['rowId'], password=inp.get('password'))
    return {'dataHex': data.hex()}


def process_removeRowDecode(inp):
    d = decode_remove_row(bytes.fromhex(inp['dataHex']))
    return {'tableName': d['table'], 'rowId': d['row_id']}


def _input_to_rpc_params(inp):
    params = []
    for p in inp['params']:
        if p['type'] == 'bytes':
            params.append(bytes.fromhex(p['value']))
        elif p['type'] in ('Vector3', 'Quaternion'):
            params.append(tuple(p['value']))
        else:
            params.append(p['value'])
    return params


def _view_id_int(vid):
    return vid['id'] if vid['scope'] == 'scene' else (0x100000000 | vid['id'])


def process_rpcEncode(inp):
    params = _input_to_rpc_params(inp)
    mode = MODE_MAP[inp['rpcMode']]
    data, bits = encode_rpc_subsequent(
        inp['methodName'], params, view_id=_view_id_int(inp['viewId']),
        timestamp_ms=inp['timestampMs'], mode=mode, target_view=0x2000,
    )
    return {'dataHex': data.hex(), 'bitLength': bits}


def process_rpcDecode(inp):
    d = decode_rpc(bytes.fromhex(inp['dataHex']), inp['bitLength'])
    return {
        'methodName': d.get('method_name', ''),
        'timestampMs': d.get('timestamp_ms', 0),
        'rpcMode': d['rpc_mode'].name if 'rpc_mode' in d else '',
    }


def process_rpcFirstUse(inp):
    params = _input_to_rpc_params(inp)
    mode = MODE_MAP[inp['rpcMode']]
    data, bits = encode_rpc_first_use(
        inp['methodName'], params, view_id=_view_id_int(inp['viewId']),
        timestamp_ms=inp['timestampMs'], mode=mode, target_view=0x2000,
    )
    return {'dataHex': data.hex(), 'bitLength': bits}


def process_rpcFirstUseDecode(inp):
    d = decode_rpc(bytes.fromhex(inp['dataHex']), inp['bitLength'])
    return {
        'methodName': d.get('method_name', ''),
        'rpcMode': d['rpc_mode'].name if 'rpc_mode' in d else '',
    }


def process_methodHash(inp):
    guid, mhash = compute_method_id(inp['methodName'])
    return {'classGuidHex': guid.hex(), 'methodHashHex': mhash.hex()}


def process_methodIndex(inp):
    idx = compute_method_index(inp['methodRid'], inp['interfaceMethodCount'])
    return {'methodIndex': idx}


def process_viewId(inp):
    vid = inp['id'] if inp['scope'] == 'scene' else (0x100000000 | inp['id'])
    return {'dataHex': encode_view_id(vid).hex()}


def process_viewIdParam(inp):
    return {'value16': encode_view_id_16(inp['scope'], inp['id'])}


def process_addressEncode(inp):
    return {'dataHex': encode_address(inp['ip'], inp['port']).hex()}


def process_addressDecode(inp):
    ip, port = decode_address(bytes.fromhex(inp['dataHex']))
    return {'ip': ip, 'port': port}


def _build_data_bs(fields):
    bs = BitStream()
    for f in fields:
        ftype, val = f['type'], f['value']
        if ftype == 'int':
            v = val
            if v < 0:
                v += 0x100000000
            bs.write_bits(v & 0xFFFFFFFF, 32)
        elif ftype == 'float':
            bs.write_float_be(val)
        elif ftype == 'bool':
            bs.write_bit(1 if val else 0)
        elif ftype == 'short':
            bs.write_bits(val & 0xFFFF, 16)
        elif ftype == 'char':
            bs.write_bits(val & 0xFF, 8)
        elif ftype == 'Vector3':
            for v in val: bs.write_float_be(v)
        elif ftype == 'Quaternion':
            for v in val: bs.write_float_be(v)
    return bs


def process_stateSync(inp):
    data_bs = _build_data_bs(inp['fields'])
    vid = inp['viewId']
    data, bits = encode_state_sync(
        vid['id'], inp['timestamp'], data_bs,
        is_first=inp['isFirst'], view_id_scope=vid['scope'],
    )
    return {'dataHex': data.hex(), 'bitLength': bits}


def process_stateSyncDecode(inp):
    d = decode_state_sync(bytes.fromhex(inp['dataHex']), inp['bitLength'])
    return {
        'timestamp': d['timestamp'], 'isFirst': d['is_first'],
        'viewIdScope': d['view_id_scope'], 'viewId': d['view_id'],
    }


def process_deltaStateSync(inp):
    vid = inp['viewId']
    data, bits = encode_delta_state_sync(
        vid['id'], inp['timestamp'],
        inp['fieldValues'], inp['prevValues'], inp['fieldWidths'],
        is_first=inp['isFirst'], view_id_scope=vid['scope'],
    )
    return {'dataHex': data.hex(), 'bitLength': bits}


def process_deltaSyncDecode(inp):
    d = decode_delta_state_sync(
        bytes.fromhex(inp['dataHex']), inp['bitLength'],
        inp['fieldCount'], inp['fieldWidths'], inp['prevValues'],
    )
    return {
        'timestamp': d['timestamp'], 'isFirst': d['is_first'],
        'dirtyFlags': d.get('dirty_flags', []),
        'fieldValues': d.get('field_values', []),
    }


def process_batchIndexEncode(inp):
    data, bits = encode_batch_index(inp['methodName'], inp['methodIndex'])
    return {'dataHex': data.hex(), 'bitLength': bits}


def process_batchIndexDecode(inp):
    payload = bytes.fromhex(inp['dataHex'])
    result = decode_batch_index(payload)
    if result is None:
        return {'methodName': None, 'methodIndex': 0}
    return {
        'methodName': result['method_name'],
        'methodIndex': result['method_index'],
    }


PROCESSORS = {
    'writeCompressed': process_writeCompressed,
    'readCompressed': process_readCompressed,
    'huffman': process_huffman,
    'huffmanDecode': process_huffmanDecode,
    'bitstream': process_bitstream,
    'bitstreamRead': process_bitstreamRead,
    'cell': process_cell,
    'cellDecode': process_cellDecode,
    'updateRow': process_updateRow,
    'updateRowDecode': process_updateRowDecode,
    'queryRequest': process_queryRequest,
    'queryRequestDecode': process_queryRequestDecode,
    'queryReply': process_queryReply,
    'queryReplyDecode': process_queryReplyDecode,
    'removeRow': process_removeRow,
    'removeRowDecode': process_removeRowDecode,
    'rpcEncode': process_rpcEncode,
    'rpcDecode': process_rpcDecode,
    'rpcFirstUse': process_rpcFirstUse,
    'rpcFirstUseDecode': process_rpcFirstUseDecode,
    'methodHash': process_methodHash,
    'methodIndex': process_methodIndex,
    'stateSync': process_stateSync,
    'stateSyncDecode': process_stateSyncDecode,
    'deltaStateSync': process_deltaStateSync,
    'deltaSyncDecode': process_deltaSyncDecode,
    'viewId': process_viewId,
    'viewIdParam': process_viewIdParam,
    'addressEncode': process_addressEncode,
    'addressDecode': process_addressDecode,
    'batchIndexEncode': process_batchIndexEncode,
    'batchIndexDecode': process_batchIndexDecode,
}


def main():
    raw = sys.stdin.read().strip()
    if not raw:
        print("No input on stdin", file=sys.stderr)
        sys.exit(2)

    if raw.startswith('['):
        test_objects = json.loads(raw)
    else:
        test_objects = [json.loads(line) for line in raw.split('\n') if line.strip()]

    results = []
    for obj in test_objects:
        category = obj['testInfo']['category']
        if category not in PROCESSORS:
            print(f"Unknown category: {category}", file=sys.stderr)
            sys.exit(2)
        output = PROCESSORS[category](obj['input'])
        result = dict(obj)
        result['output'] = output
        results.append(result)

    json.dump(results, sys.stdout, indent=2)
    sys.stdout.write('\n')


if __name__ == '__main__':
    main()
