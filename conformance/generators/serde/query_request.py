import os
import random
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from ._master_common import random_table_name, random_column_name

PRESET_TESTS = [
    {
        'name': "No filters, no subset, no row IDs",
        'desc': "Simplest query",
        'tableName': 'TestGame', 'password': None,
        'columnSubset': [], 'filters': [], 'rowIds': [],
    },
    {
        'name': "Column subset",
        'desc': "3-column subset",
        'tableName': 'TestGame', 'password': None,
        'columnSubset': ['Game name', 'Port', 'Comment'],
        'filters': [], 'rowIds': [],
    },
    {
        'name': "EQUAL filter on NUMERIC",
        'desc': "Basic filter",
        'tableName': 'TestGame', 'password': None,
        'columnSubset': [],
        'filters': [{'name': 'Port', 'type': 'NUMERIC', 'operation': 'EQUAL', 'value': 7777.0}],
        'rowIds': [],
    },
    {
        'name': "NOT_EQUAL filter on STRING",
        'desc': "String comparison filter",
        'tableName': 'TestGame', 'password': None,
        'columnSubset': [],
        'filters': [{'name': 'Game name', 'type': 'STRING', 'operation': 'NOT_EQUAL', 'value': 'test'}],
        'rowIds': [],
    },
    {
        'name': "IS_EMPTY filter",
        'desc': "No-value filter variant",
        'tableName': 'TestGame', 'password': None,
        'columnSubset': [],
        'filters': [{'name': 'Comment', 'type': 'STRING', 'operation': 'IS_EMPTY', 'value': None}],
        'rowIds': [],
    },
    {
        'name': "Multiple filters",
        'desc': "Combined filtering",
        'tableName': 'TestGame', 'password': None,
        'columnSubset': [],
        'filters': [
            {'name': 'Port', 'type': 'NUMERIC', 'operation': 'GREATER_THAN', 'value': 7000.0},
            {'name': 'Game name', 'type': 'STRING', 'operation': 'NOT_EMPTY', 'value': None},
        ],
        'rowIds': [],
    },
    {
        'name': "Specific row IDs",
        'desc': "Row ID list",
        'tableName': 'TestGame', 'password': None,
        'columnSubset': [], 'filters': [],
        'rowIds': [0, 5, 42],
    },
    {
        'name': "All filter operations",
        'desc': "One of each filter type",
        'tableName': 'AllFilters', 'password': None,
        'columnSubset': [],
        'filters': [
            {'name': 'A', 'type': 'NUMERIC', 'operation': 'EQUAL', 'value': 1.0},
            {'name': 'B', 'type': 'NUMERIC', 'operation': 'NOT_EQUAL', 'value': 2.0},
            {'name': 'C', 'type': 'NUMERIC', 'operation': 'GREATER_THAN', 'value': 3.0},
            {'name': 'D', 'type': 'NUMERIC', 'operation': 'GREATER_THAN_EQ', 'value': 4.0},
            {'name': 'E', 'type': 'NUMERIC', 'operation': 'LESS_THAN', 'value': 5.0},
            {'name': 'F', 'type': 'NUMERIC', 'operation': 'LESS_THAN_EQ', 'value': 6.0},
            {'name': 'G', 'type': 'STRING', 'operation': 'IS_EMPTY', 'value': None},
            {'name': 'H', 'type': 'STRING', 'operation': 'NOT_EMPTY', 'value': None},
        ],
        'rowIds': [],
    },
]

OP_MAP = {
    'EQUAL': 0, 'NOT_EQUAL': 1, 'GREATER_THAN': 2, 'GREATER_THAN_EQ': 3,
    'LESS_THAN': 4, 'LESS_THAN_EQ': 5, 'IS_EMPTY': 6, 'NOT_EMPTY': 7,
}


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
                'category': 'queryRequest',
                'mode': 'basic',
            },
            'input': {
                'tableName': preset['tableName'],
                'password': preset['password'],
                'columnSubset': preset['columnSubset'],
                'filters': preset['filters'],
                'rowIds': preset['rowIds'],
            },
        })
    return tests


def _generate_random(count, rng):
    tests = []
    for i in range(count):
        num_filters = rng.randint(0, 3)
        filters = []
        for _ in range(num_filters):
            op_name = rng.choice(list(OP_MAP.keys()))
            f = {
                'name': random_column_name(rng),
                'type': rng.choice(['NUMERIC', 'STRING']),
                'operation': op_name,
            }
            if op_name in ('IS_EMPTY', 'NOT_EMPTY'):
                f['value'] = None
            elif f['type'] == 'NUMERIC':
                f['value'] = rng.uniform(0, 10000)
            else:
                f['value'] = ''.join(chr(rng.randint(65, 90)) for _ in range(rng.randint(1, 10)))
            filters.append(f)

        tests.append({
            'testInfo': {
                'testId': str(uuid.uuid4()),
                'testName': f"queryRequest(random:{i})",
                'testDescription': f"Random query with {num_filters} filters",
                'category': 'queryRequest',
                'mode': 'random',
            },
            'input': {
                'tableName': random_table_name(rng),
                'password': None,
                'columnSubset': [random_column_name(rng) for _ in range(rng.randint(0, 3))],
                'filters': filters,
                'rowIds': [rng.randint(0, 100) for _ in range(rng.randint(0, 2))],
            },
        })
    return tests
