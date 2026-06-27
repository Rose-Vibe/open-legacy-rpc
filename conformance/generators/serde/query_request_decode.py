import os
import random
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from protocol.master_serialization import encode_query_request, NUMERIC, STRING, BINARY
from .query_request import PRESET_TESTS, OP_MAP
from ._master_common import random_table_name, random_column_name

TYPE_INT = {'NUMERIC': NUMERIC, 'STRING': STRING, 'BINARY': BINARY}


def _encode(inp):
    filters = []
    for f in inp.get('filters', []):
        filt = {'name': f['name'], 'type': TYPE_INT[f['type']], 'operation': OP_MAP[f['operation']]}
        val = f.get('value')
        if val is not None and f['type'] == 'BINARY' and isinstance(val, str):
            val = bytes.fromhex(val)
        filt['value'] = val
        filters.append(filt)
    return encode_query_request(
        inp['tableName'],
        column_subset=inp.get('columnSubset') or None,
        filters=filters or None,
        row_ids=inp.get('rowIds') or None,
        password=inp.get('password'),
    )


def generate(mode, count=10, rng=None):
    if mode == 'basic':
        return _generate_basic()
    return _generate_random(count, rng or random.Random())


def _generate_basic():
    tests = []
    for preset in PRESET_TESTS:
        inp = {
            'tableName': preset['tableName'], 'password': preset['password'],
            'columnSubset': preset['columnSubset'], 'filters': preset['filters'],
            'rowIds': preset['rowIds'],
        }
        data = _encode(inp)
        tests.append({
            'testInfo': {
                'testId': str(uuid.uuid4()),
                'testName': f"queryRequestDecode: {preset['name']}",
                'testDescription': preset['desc'],
                'category': 'queryRequestDecode',
                'mode': 'basic',
            },
            'input': {'dataHex': data.hex()},
        })
    return tests


def _generate_random(count, rng):
    tests = []
    for i in range(count):
        num_filters = rng.randint(0, 3)
        filters = []
        for _ in range(num_filters):
            op_name = rng.choice(list(OP_MAP.keys()))
            f = {'name': random_column_name(rng), 'type': rng.choice(['NUMERIC', 'STRING']), 'operation': op_name}
            if op_name in ('IS_EMPTY', 'NOT_EMPTY'):
                f['value'] = None
            elif f['type'] == 'NUMERIC':
                f['value'] = rng.uniform(0, 10000)
            else:
                f['value'] = ''.join(chr(rng.randint(65, 90)) for _ in range(rng.randint(1, 10)))
            filters.append(f)
        inp = {
            'tableName': random_table_name(rng), 'password': None,
            'columnSubset': [random_column_name(rng) for _ in range(rng.randint(0, 2))],
            'filters': filters, 'rowIds': [],
        }
        data = _encode(inp)
        tests.append({
            'testInfo': {
                'testId': str(uuid.uuid4()),
                'testName': f"queryRequestDecode(random:{i})",
                'testDescription': f"Random query decode",
                'category': 'queryRequestDecode',
                'mode': 'random',
            },
            'input': {'dataHex': data.hex()},
        })
    return tests
