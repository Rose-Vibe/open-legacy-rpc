import os
import random
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from ._master_common import random_cell, random_table_name, random_column_name

STANDARD_CELLS = [
    {'name': 'NAT', 'type': 'NUMERIC', 'value': 0.0},
    {'name': 'Game name', 'type': 'STRING', 'value': 'My Server'},
    {'name': 'Connected players', 'type': 'NUMERIC', 'value': 3.0},
    {'name': 'Player limit', 'type': 'NUMERIC', 'value': 16.0},
    {'name': 'Password protected', 'type': 'NUMERIC', 'value': 0.0},
    {'name': 'IP address', 'type': 'BINARY', 'value': '302e302e302e3000000000000000000000'},
    {'name': 'Port', 'type': 'NUMERIC', 'value': 7777.0},
    {'name': 'Comment', 'type': 'STRING', 'value': 'test server'},
]

PRESET_TESTS = [
    {
        'name': "Standard Unity registration (8 cells)",
        'desc': "Golden path with all standard columns",
        'tableName': 'TestGame',
        'password': None,
        'updateMode': 1,
        'rowId': None,
        'cells': STANDARD_CELLS,
    },
    {
        'name': "Single cell",
        'desc': "Minimal UpdateRow",
        'tableName': 'Mini',
        'password': None,
        'updateMode': 1,
        'rowId': None,
        'cells': [{'name': 'Score', 'type': 'NUMERIC', 'value': 100.0}],
    },
    {
        'name': "With password",
        'desc': "Password field encoding",
        'tableName': 'Secure',
        'password': 'secret123',
        'updateMode': 1,
        'rowId': None,
        'cells': [{'name': 'Name', 'type': 'STRING', 'value': 'private'}],
    },
    {
        'name': "With explicit rowId",
        'desc': "hasRowId=true",
        'tableName': 'TestGame',
        'password': None,
        'updateMode': 0,
        'rowId': 42,
        'cells': [{'name': 'Score', 'type': 'NUMERIC', 'value': 99.0}],
    },
    {
        'name': "ADD_NEW_ROW mode",
        'desc': "updateMode=2",
        'tableName': 'TestGame',
        'password': None,
        'updateMode': 2,
        'rowId': None,
        'cells': [{'name': 'Name', 'type': 'STRING', 'value': 'new'}],
    },
    {
        'name': "All cell types mixed",
        'desc': "NUMERIC + STRING + BINARY in one message",
        'tableName': 'Mixed',
        'password': None,
        'updateMode': 1,
        'rowId': None,
        'cells': [
            {'name': 'Num', 'type': 'NUMERIC', 'value': 3.14},
            {'name': 'Str', 'type': 'STRING', 'value': 'hello'},
            {'name': 'Bin', 'type': 'BINARY', 'value': 'cafebabe'},
        ],
    },
    {
        'name': "Empty string values",
        'desc': "Edge case for Huffman",
        'tableName': 'EdgeCase',
        'password': None,
        'updateMode': 1,
        'rowId': None,
        'cells': [
            {'name': 'Empty', 'type': 'STRING', 'value': ''},
            {'name': 'Also empty', 'type': 'STRING', 'value': ''},
        ],
    },
    {
        'name': "Binary cell with alignment",
        'desc': "WriteAlignedBytes in full message context",
        'tableName': 'BinTest',
        'password': None,
        'updateMode': 1,
        'rowId': None,
        'cells': [
            {'name': 'Flag', 'type': 'NUMERIC', 'value': 1.0},
            {'name': 'Data', 'type': 'BINARY', 'value': 'ff00ff00ff'},
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
                'category': 'updateRow',
                'mode': 'basic',
            },
            'input': {
                'tableName': preset['tableName'],
                'password': preset['password'],
                'updateMode': preset['updateMode'],
                'rowId': preset['rowId'],
                'cells': preset['cells'],
            },
        })
    return tests


def _generate_random(count, rng):
    tests = []
    for i in range(count):
        num_cells = rng.randint(1, 8)
        cells = []
        for _ in range(num_cells):
            cell = random_cell(rng)
            cells.append({
                'name': random_column_name(rng),
                'type': cell['type'],
                'value': cell['value'],
            })
        tests.append({
            'testInfo': {
                'testId': str(uuid.uuid4()),
                'testName': f"updateRow(random:{i})",
                'testDescription': f"Random {num_cells} cells",
                'category': 'updateRow',
                'mode': 'random',
            },
            'input': {
                'tableName': random_table_name(rng),
                'password': rng.choice([None, 'pass' + str(rng.randint(0, 99))]),
                'updateMode': rng.randint(0, 2),
                'rowId': rng.choice([None, rng.randint(0, 1000)]),
                'cells': cells,
            },
        })
    return tests
