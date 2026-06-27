"""Shared helpers for master server serde test generators."""

import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

CELL_TYPES = ['NUMERIC', 'STRING', 'BINARY']
TYPE_MAP = {'NUMERIC': 0, 'STRING': 1, 'BINARY': 2}


def random_cell(rng, cell_type=None):
    if cell_type is None:
        cell_type = rng.choice(CELL_TYPES)

    if cell_type == 'NUMERIC':
        if rng.random() < 0.1:
            value = None
        else:
            value = rng.uniform(-1e6, 1e6)
    elif cell_type == 'STRING':
        if rng.random() < 0.1:
            value = None
        else:
            length = rng.randint(0, 50)
            value = ''.join(chr(rng.randint(32, 126)) for _ in range(length))
    elif cell_type == 'BINARY':
        if rng.random() < 0.1:
            value = None
        else:
            length = rng.randint(0, 32)
            value = bytes(rng.randint(0, 255) for _ in range(length)).hex()
    return {'type': cell_type, 'value': value}


def random_table_name(rng):
    length = rng.randint(3, 20)
    return ''.join(chr(rng.randint(65, 90)) for _ in range(length))


def random_column_name(rng):
    names = ['Score', 'Level', 'Health', 'Name', 'Mode', 'Map', 'Region',
             'Version', 'Rank', 'Team', 'Status', 'Ping', 'Custom']
    return rng.choice(names) + str(rng.randint(0, 99))


def cell_to_json(cell_type, value):
    """Convert a cell value to JSON-safe representation."""
    if value is None:
        return None
    if cell_type == 'BINARY' and isinstance(value, bytes):
        return value.hex()
    return value


def cell_from_json(cell_type, value):
    """Convert from JSON representation back to internal."""
    if value is None:
        return None
    if cell_type == 'BINARY' and isinstance(value, str):
        return bytes.fromhex(value)
    return value
