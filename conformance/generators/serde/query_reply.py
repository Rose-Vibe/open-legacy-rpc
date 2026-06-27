import os
import random
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from ._master_common import random_cell, random_column_name

PRESET_TESTS = [
    {
        'name': "Single row, 2 columns",
        'desc': "Minimal reply",
        'columns': [
            {'name': 'Game name', 'type': 'STRING'},
            {'name': 'Port', 'type': 'NUMERIC'},
        ],
        'rows': [{'key': 0, 'cells': {'Game name': 'Server 1', 'Port': 7777.0}}],
    },
    {
        'name': "Empty reply",
        'desc': "No columns, no rows",
        'columns': [],
        'rows': [],
    },
    {
        'name': "Multiple rows",
        'desc': "5-row reply",
        'columns': [
            {'name': 'Name', 'type': 'STRING'},
            {'name': 'Score', 'type': 'NUMERIC'},
        ],
        'rows': [
            {'key': i, 'cells': {'Name': f'Player{i}', 'Score': float(i * 100)}}
            for i in range(5)
        ],
    },
    {
        'name': "Full Unity schema",
        'desc': "13 columns, 1 row — real-world column set",
        'columns': [
            {'name': '__SystemAddress', 'type': 'BINARY'},
            {'name': '__SystemGuid', 'type': 'BINARY'},
            {'name': '__lastPingResponseTime', 'type': 'NUMERIC'},
            {'name': '__nextPingSendTime', 'type': 'NUMERIC'},
            {'name': 'NAT', 'type': 'NUMERIC'},
            {'name': 'Game name', 'type': 'STRING'},
            {'name': 'Connected players', 'type': 'NUMERIC'},
            {'name': 'Player limit', 'type': 'NUMERIC'},
            {'name': 'Password protected', 'type': 'NUMERIC'},
            {'name': 'IP address', 'type': 'BINARY'},
            {'name': 'Port', 'type': 'NUMERIC'},
            {'name': 'Comment', 'type': 'STRING'},
            {'name': 'GUID', 'type': 'STRING'},
        ],
        'rows': [{
            'key': 0,
            'cells': {
                'NAT': 0.0,
                'Game name': 'TestGame',
                'Connected players': 1.0,
                'Player limit': 16.0,
                'Password protected': 0.0,
                'IP address': '3139322e3136382e312e31303000000000',
                'Port': 7777.0,
                'Comment': 'hello',
                'GUID': '12345',
            },
        }],
    },
    {
        'name': "Sparse cells",
        'desc': "Not all columns populated",
        'columns': [
            {'name': 'A', 'type': 'NUMERIC'},
            {'name': 'B', 'type': 'STRING'},
            {'name': 'C', 'type': 'NUMERIC'},
        ],
        'rows': [{'key': 0, 'cells': {'A': 1.0}}],
    },
    {
        'name': "All-null cells",
        'desc': "Row with no populated cells",
        'columns': [
            {'name': 'X', 'type': 'NUMERIC'},
            {'name': 'Y', 'type': 'STRING'},
        ],
        'rows': [{'key': 0, 'cells': {}}],
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
                'category': 'queryReply',
                'mode': 'basic',
            },
            'input': {
                'columns': preset['columns'],
                'rows': preset['rows'],
            },
        })
    return tests


def _generate_random(count, rng):
    tests = []
    for i in range(count):
        num_cols = rng.randint(1, 8)
        columns = []
        for _ in range(num_cols):
            col_type = rng.choice(['NUMERIC', 'STRING', 'BINARY'])
            columns.append({'name': random_column_name(rng), 'type': col_type})

        num_rows = rng.randint(0, 5)
        rows = []
        for r in range(num_rows):
            cells = {}
            for col in columns:
                if rng.random() > 0.3:
                    cell = random_cell(rng, col['type'])
                    cells[col['name']] = cell['value']
            rows.append({'key': r, 'cells': cells})

        tests.append({
            'testInfo': {
                'testId': str(uuid.uuid4()),
                'testName': f"queryReply(random:{i})",
                'testDescription': f"Random {num_cols} cols, {num_rows} rows",
                'category': 'queryReply',
                'mode': 'random',
            },
            'input': {'columns': columns, 'rows': rows},
        })
    return tests
