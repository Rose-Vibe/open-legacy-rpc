"""
Serialization layer for the Unity Master Server protocol.

Handles RakNet LightweightDatabase message encoding/decoding using
BitStream and Huffman StringCompressor.
"""

import struct
from .bitstream import BitStream
from .huffman import get_tree, encode_string_for_wire

_tree = get_tree()

# Column types (DS_Table.h ColumnType enum)
NUMERIC = 0
STRING = 1
BINARY = 2
POINTER = 3

# Message IDs
ID_DATABASE_QUERY_REQUEST = 75
ID_DATABASE_UPDATE_ROW = 76
ID_DATABASE_REMOVE_ROW = 77
ID_DATABASE_QUERY_REPLY = 78
ID_DATABASE_UNKNOWN_TABLE = 79
ID_DATABASE_INCORRECT_PASSWORD = 80
ID_DATABASE_ROWID = 200
ID_MASTERSERVER_REDIRECT = 201
ID_MASTERSERVER_MSG = 202

# Update modes
RUM_UPDATE_EXISTING_ROW = 0
RUM_UPDATE_OR_ADD_ROW = 1
RUM_ADD_NEW_ROW = 2

# Filter operations
QF_EQUAL = 0
QF_NOT_EQUAL = 1
QF_GREATER_THAN = 2
QF_GREATER_THAN_EQ = 3
QF_LESS_THAN = 4
QF_LESS_THAN_EQ = 5
QF_IS_EMPTY = 6
QF_NOT_EMPTY = 7

VERSION = bytes([2, 0, 0])


def read_huffman_string(bs):
    bit_length = bs.read_compressed_u32()
    if bit_length == 0:
        return ""
    end_pos = bs.pos + bit_length
    chars = []
    node = _tree
    for _ in range(bit_length):
        if bs.remaining <= 0:
            break
        bit = bs.read_bit()
        node = node.right if bit else node.left
        if node.left is None and node.right is None:
            chars.append(chr(node.char))
            node = _tree
    bs.pos = end_pos
    return ''.join(chars)


def write_huffman_string(bs, s):
    if s is None or len(s) == 0:
        bs.write_compressed_u32(0)
        return
    padded_bits = encode_string_for_wire(s)
    bs.write_compressed_u32(len(padded_bits))
    for b in padded_bits:
        bs.write_bit(1 if b == '1' else 0)


def read_cell(bs, col_type):
    is_empty = bs.read_bool()
    if is_empty:
        return None
    if col_type == NUMERIC:
        return bs.read_double_be()
    elif col_type == STRING:
        return read_huffman_string(bs)
    elif col_type == BINARY:
        length = bs.read_u32_be()
        return bs.read_aligned_bytes(length)
    elif col_type == POINTER:
        return bs.read_bits(64)
    return None


def write_cell(bs, value, col_type):
    if value is None:
        bs.write_bool(True)
        return
    bs.write_bool(False)
    if col_type == NUMERIC:
        bs.write_double_be(float(value))
    elif col_type == STRING:
        write_huffman_string(bs, str(value))
    elif col_type == BINARY:
        data = bytes(value) if not isinstance(value, bytes) else value
        bs.write_u32_be(len(data))
        bs.write_aligned_bytes(data)
    elif col_type == POINTER:
        bs.write_bits(value, 64)


def read_client_header(bs):
    version = bs.read_bytes(3)
    table_name = read_huffman_string(bs)
    has_password = bs.read_bool()
    password = read_huffman_string(bs) if has_password else None
    return version, table_name, password


def write_client_header(bs, table_name, password=None):
    bs.write_bytes(VERSION)
    write_huffman_string(bs, table_name)
    if password:
        bs.write_bool(True)
        write_huffman_string(bs, password)
    else:
        bs.write_bool(False)


def decode_update_row(payload):
    bs = BitStream(payload)
    msg_id = bs.read_u8()
    if msg_id != ID_DATABASE_UPDATE_ROW:
        raise ValueError(f"expected msg_id {ID_DATABASE_UPDATE_ROW}, got {msg_id}")
    version, table_name, password = read_client_header(bs)

    update_mode = bs.read_u8()
    has_row_id = bs.read_bool()
    row_id = bs.read_u32_be() if has_row_id else None
    num_updates = bs.read_u8()

    cells = []
    for _ in range(num_updates):
        col_name = read_huffman_string(bs)
        col_type = bs.read_u8()
        value = read_cell(bs, col_type)
        cells.append({'name': col_name, 'type': col_type, 'value': value})

    return {
        'version': version,
        'table': table_name,
        'password': password,
        'update_mode': update_mode,
        'row_id': row_id,
        'cells': cells,
    }


def encode_update_row(table_name, cells, update_mode=RUM_UPDATE_OR_ADD_ROW,
                      row_id=None, password=None):
    bs = BitStream()
    bs.write_u8(ID_DATABASE_UPDATE_ROW)
    write_client_header(bs, table_name, password)
    bs.write_u8(update_mode)
    if row_id is not None:
        bs.write_bool(True)
        bs.write_u32_be(row_id)
    else:
        bs.write_bool(False)
    bs.write_u8(len(cells))
    for cell in cells:
        write_huffman_string(bs, cell['name'])
        bs.write_u8(cell['type'])
        write_cell(bs, cell['value'], cell['type'])
    return bs.to_bytes()


def decode_query_request(payload):
    bs = BitStream(payload)
    msg_id = bs.read_u8()
    if msg_id != ID_DATABASE_QUERY_REQUEST:
        raise ValueError(f"expected msg_id {ID_DATABASE_QUERY_REQUEST}, got {msg_id}")
    version, table_name, password = read_client_header(bs)

    num_col_subset = bs.read_u8()
    column_subset = [read_huffman_string(bs) for _ in range(num_col_subset)]

    num_filters = bs.read_u8()
    filters = []
    for _ in range(num_filters):
        col_name = read_huffman_string(bs)
        col_type = bs.read_u8()
        operation = bs.read_u8()
        value = None
        if operation not in (QF_IS_EMPTY, QF_NOT_EMPTY):
            value = read_cell(bs, col_type)
        filters.append({
            'name': col_name, 'type': col_type,
            'operation': operation, 'value': value,
        })

    num_row_ids = bs.read_u8()
    row_ids = [bs.read_u32_be() for _ in range(num_row_ids)]

    return {
        'version': version,
        'table': table_name,
        'password': password,
        'column_subset': column_subset,
        'filters': filters,
        'row_ids': row_ids,
    }


def encode_query_request(table_name, column_subset=None, filters=None,
                         row_ids=None, password=None):
    bs = BitStream()
    bs.write_u8(ID_DATABASE_QUERY_REQUEST)
    write_client_header(bs, table_name, password)

    cols = column_subset or []
    bs.write_u8(len(cols))
    for col in cols:
        write_huffman_string(bs, col)

    filt = filters or []
    bs.write_u8(len(filt))
    for f in filt:
        write_huffman_string(bs, f['name'])
        bs.write_u8(f['type'])
        bs.write_u8(f['operation'])
        if f['operation'] not in (QF_IS_EMPTY, QF_NOT_EMPTY):
            write_cell(bs, f['value'], f['type'])

    rids = row_ids or []
    bs.write_u8(len(rids))
    for rid in rids:
        bs.write_u32_be(rid)

    return bs.to_bytes()


def decode_remove_row(payload):
    bs = BitStream(payload)
    msg_id = bs.read_u8()
    if msg_id != ID_DATABASE_REMOVE_ROW:
        raise ValueError(f"expected msg_id {ID_DATABASE_REMOVE_ROW}, got {msg_id}")
    table_name = read_huffman_string(bs)
    has_password = bs.read_bool()
    password = read_huffman_string(bs) if has_password else None
    row_id = bs.read_u32_be()
    return {
        'table': table_name,
        'password': password,
        'row_id': row_id,
    }


def encode_remove_row(table_name, row_id, password=None):
    bs = BitStream()
    bs.write_u8(ID_DATABASE_REMOVE_ROW)
    write_huffman_string(bs, table_name)
    if password:
        bs.write_bool(True)
        write_huffman_string(bs, password)
    else:
        bs.write_bool(False)
    bs.write_u32_be(row_id)
    return bs.to_bytes()


def decode_query_reply(payload):
    bs = BitStream(payload)
    msg_id = bs.read_u8()
    if msg_id != ID_DATABASE_QUERY_REPLY:
        raise ValueError(f"expected msg_id {ID_DATABASE_QUERY_REPLY}, got {msg_id}")

    if bs.remaining < 32:
        return {'columns': [], 'rows': []}

    num_columns = bs.read_u32_be()
    columns = []
    for _ in range(num_columns):
        name = read_huffman_string(bs)
        col_type = bs.read_u8()
        columns.append({'name': name, 'type': col_type})

    num_rows = bs.read_u32_be()
    rows = []
    for _ in range(num_rows):
        key = bs.read_u32_be()
        num_entries = bs.read_u32_be()
        cells = {}
        for _ in range(num_entries):
            cell_idx = bs.read_u32_be()
            if cell_idx >= len(columns):
                raise ValueError(f"cell_idx {cell_idx} out of range (have {len(columns)} columns)")
            col = columns[cell_idx]
            value = read_cell(bs, col['type'])
            cells[col['name']] = value
        rows.append({'key': key, 'cells': cells})

    return {'columns': columns, 'rows': rows}


def encode_query_reply(columns, rows):
    bs = BitStream()
    bs.write_u8(ID_DATABASE_QUERY_REPLY)

    if not columns:
        return bs.to_bytes()

    bs.write_u32_be(len(columns))
    for col in columns:
        write_huffman_string(bs, col['name'])
        bs.write_u8(col['type'])

    bs.write_u32_be(len(rows))
    for row in rows:
        bs.write_u32_be(row['key'])
        entries = row.get('cells', {})
        col_entries = []
        for idx, col in enumerate(columns):
            if col['name'] in entries:
                col_entries.append((idx, col, entries[col['name']]))
        bs.write_u32_be(len(col_entries))
        for idx, col, value in col_entries:
            bs.write_u32_be(idx)
            write_cell(bs, value, col['type'])

    return bs.to_bytes()


def encode_rowid(row_id):
    bs = BitStream()
    bs.write_u8(ID_DATABASE_ROWID)
    bs.write_u32_be(row_id)
    return bs.to_bytes()


def encode_unknown_table():
    return bytes([ID_DATABASE_UNKNOWN_TABLE])


def encode_incorrect_password():
    return bytes([ID_DATABASE_INCORRECT_PASSWORD])
