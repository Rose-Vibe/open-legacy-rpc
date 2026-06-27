import os
import random
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from protocol.master_serialization import encode_update_row, NUMERIC, STRING, BINARY
from .update_row import PRESET_TESTS
from ._master_common import random_cell, random_table_name, random_column_name

TYPE_INT = {'NUMERIC': NUMERIC, 'STRING': STRING, 'BINARY': BINARY}


def _encode(inp):
    cells = []
    for c in inp['cells']:
        val = c['value']
        if c['type'] == 'BINARY' and isinstance(val, str):
            val = bytes.fromhex(val)
        cells.append({'name': c['name'], 'type': TYPE_INT[c['type']], 'value': val})
    return encode_update_row(
        inp['tableName'], cells,
        update_mode=inp['updateMode'],
        row_id=inp['rowId'],
        password=inp['password'],
    )


def generate(mode, count=10, rng=None):
    if mode == 'basic':
        return _generate_basic()
    return _generate_random(count, rng or random.Random())


def _generate_basic():
    tests = []
    for preset in PRESET_TESTS:
        inp = {
            'tableName': preset['tableName'],
            'password': preset['password'],
            'updateMode': preset['updateMode'],
            'rowId': preset['rowId'],
            'cells': preset['cells'],
        }
        data = _encode(inp)
        tests.append({
            'testInfo': {
                'testId': str(uuid.uuid4()),
                'testName': f"updateRowDecode: {preset['name']}",
                'testDescription': preset['desc'],
                'category': 'updateRowDecode',
                'mode': 'basic',
            },
            'input': {'dataHex': data.hex()},
        })
    return tests


def _generate_random(count, rng):
    tests = []
    for i in range(count):
        num_cells = rng.randint(1, 6)
        cells = []
        for _ in range(num_cells):
            cell = random_cell(rng)
            cells.append({
                'name': random_column_name(rng),
                'type': cell['type'],
                'value': cell['value'],
            })
        inp = {
            'tableName': random_table_name(rng),
            'password': rng.choice([None, 'pw' + str(rng.randint(0, 9))]),
            'updateMode': rng.randint(0, 2),
            'rowId': rng.choice([None, rng.randint(0, 100)]),
            'cells': cells,
        }
        data = _encode(inp)
        tests.append({
            'testInfo': {
                'testId': str(uuid.uuid4()),
                'testName': f"updateRowDecode(random:{i})",
                'testDescription': f"Random decode with {num_cells} cells",
                'category': 'updateRowDecode',
                'mode': 'random',
            },
            'input': {'dataHex': data.hex()},
        })
    return tests
