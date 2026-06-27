import os
import random
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from protocol.master_serialization import encode_query_reply, NUMERIC, STRING, BINARY
from .query_reply import PRESET_TESTS
from ._master_common import random_cell, random_column_name

TYPE_INT = {'NUMERIC': NUMERIC, 'STRING': STRING, 'BINARY': BINARY}


def _encode(inp):
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
    return encode_query_reply(columns, rows)


def generate(mode, count=10, rng=None):
    if mode == 'basic':
        return _generate_basic()
    return _generate_random(count, rng or random.Random())


def _generate_basic():
    tests = []
    for preset in PRESET_TESTS:
        inp = {'columns': preset['columns'], 'rows': preset['rows']}
        data = _encode(inp)
        tests.append({
            'testInfo': {
                'testId': str(uuid.uuid4()),
                'testName': f"queryReplyDecode: {preset['name']}",
                'testDescription': preset['desc'],
                'category': 'queryReplyDecode',
                'mode': 'basic',
            },
            'input': {'dataHex': data.hex()},
        })
    return tests


def _generate_random(count, rng):
    tests = []
    for i in range(count):
        num_cols = rng.randint(1, 6)
        columns = [{'name': random_column_name(rng), 'type': rng.choice(['NUMERIC', 'STRING', 'BINARY'])}
                    for _ in range(num_cols)]
        num_rows = rng.randint(0, 3)
        rows = []
        for r in range(num_rows):
            cells = {}
            for col in columns:
                if rng.random() > 0.3:
                    cell = random_cell(rng, col['type'])
                    cells[col['name']] = cell['value']
            rows.append({'key': r, 'cells': cells})
        inp = {'columns': columns, 'rows': rows}
        data = _encode(inp)
        tests.append({
            'testInfo': {
                'testId': str(uuid.uuid4()),
                'testName': f"queryReplyDecode(random:{i})",
                'testDescription': f"Random reply decode",
                'category': 'queryReplyDecode',
                'mode': 'random',
            },
            'input': {'dataHex': data.hex()},
        })
    return tests
