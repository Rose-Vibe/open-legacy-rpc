import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from conformance.validators.serde._bitstream_exec import execute_read_ops


def _values_equal(expected, actual):
    if isinstance(expected, float) and isinstance(actual, (int, float)):
        if math.isnan(expected):
            return isinstance(actual, float) and math.isnan(actual)
        return expected == float(actual)
    if isinstance(expected, dict) and isinstance(actual, dict):
        return all(_values_equal(expected[k], actual.get(k)) for k in expected)
    return expected == actual


def validate(test_obj):
    failures = []
    inp = test_obj['input']
    out = test_obj.get('output')

    if out is None:
        return {'pass': False, 'failures': ['Missing output field']}

    try:
        expected = execute_read_ops(
            inp['dataHex'], inp['bitLength'], inp['operations']
        )
    except Exception as e:
        return {'pass': False, 'failures': [f"Reference read error: {e}"]}

    if 'values' not in out:
        failures.append("Missing output.values")
    elif len(out['values']) != len(expected):
        failures.append(
            f"values length mismatch: expected {len(expected)}, got {len(out['values'])}"
        )
    else:
        for i, (exp, act) in enumerate(zip(expected, out['values'])):
            if not _values_equal(exp, act):
                failures.append(
                    f"values[{i}] mismatch: expected {exp!r}, got {act!r}"
                )

    return {'pass': len(failures) == 0, 'failures': failures}
