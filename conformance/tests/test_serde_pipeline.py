"""
End-to-end tests for the serde conformance test pipeline.

Tests the full generate → implement → validate flow for each category.
"""

import json
import os
import random
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from conformance.generators.serde import GENERATORS
from conformance.validators.serde import VALIDATORS
from conformance.reference_implementer import PROCESSORS


CLI_PATH = os.path.join(os.path.dirname(__file__), '..', 'serde_test_cli.py')
REF_PATH = os.path.join(os.path.dirname(__file__), '..', 'reference_implementer.py')


class TestSerdeGenerators(unittest.TestCase):
    """Test that generators produce well-formed test objects."""

    def test_writeCompressed_basic_generates(self):
        tests = GENERATORS['writeCompressed']('basic')
        self.assertEqual(len(tests), 11)
        for t in tests:
            self.assertIn('testInfo', t)
            self.assertIn('input', t)
            self.assertEqual(t['testInfo']['category'], 'writeCompressed')
            self.assertEqual(t['testInfo']['mode'], 'basic')
            self.assertIn('value', t['input'])
            self.assertIsInstance(t['input']['value'], int)

    def test_writeCompressed_random_generates(self):
        rng = random.Random(42)
        tests = GENERATORS['writeCompressed']('random', count=5, rng=rng)
        self.assertEqual(len(tests), 5)
        for t in tests:
            self.assertEqual(t['testInfo']['mode'], 'random')
            v = t['input']['value']
            self.assertGreaterEqual(v, 0)
            self.assertLessEqual(v, 0xFFFFFFFF)

    def test_writeCompressed_random_seed_deterministic(self):
        rng1 = random.Random(99)
        rng2 = random.Random(99)
        tests1 = GENERATORS['writeCompressed']('random', count=5, rng=rng1)
        tests2 = GENERATORS['writeCompressed']('random', count=5, rng=rng2)
        for t1, t2 in zip(tests1, tests2):
            self.assertEqual(t1['input']['value'], t2['input']['value'])

    def test_readCompressed_basic_generates(self):
        tests = GENERATORS['readCompressed']('basic')
        self.assertEqual(len(tests), 11)
        for t in tests:
            self.assertEqual(t['testInfo']['category'], 'readCompressed')
            self.assertIn('dataHex', t['input'])
            self.assertIn('bitLength', t['input'])

    def test_readCompressed_random_generates(self):
        rng = random.Random(42)
        tests = GENERATORS['readCompressed']('random', count=5, rng=rng)
        self.assertEqual(len(tests), 5)


class TestSerdeValidators(unittest.TestCase):
    """Test that validators correctly accept/reject outputs."""

    def test_writeCompressed_correct_output(self):
        tests = GENERATORS['writeCompressed']('basic')
        for t in tests:
            output = PROCESSORS['writeCompressed'](t['input'])
            t['output'] = output
            result = VALIDATORS['writeCompressed'](t)
            self.assertTrue(result['pass'],
                            f"Failed for {t['input']}: {result['failures']}")

    def test_writeCompressed_wrong_output(self):
        t = GENERATORS['writeCompressed']('basic')[0]
        t['output'] = {'dataHex': 'deadbeef', 'bitLength': 32}
        result = VALIDATORS['writeCompressed'](t)
        self.assertFalse(result['pass'])
        self.assertGreater(len(result['failures']), 0)

    def test_writeCompressed_missing_output(self):
        t = GENERATORS['writeCompressed']('basic')[0]
        result = VALIDATORS['writeCompressed'](t)
        self.assertFalse(result['pass'])

    def test_readCompressed_correct_output(self):
        tests = GENERATORS['readCompressed']('basic')
        for t in tests:
            output = PROCESSORS['readCompressed'](t['input'])
            t['output'] = output
            result = VALIDATORS['readCompressed'](t)
            self.assertTrue(result['pass'],
                            f"Failed for {t['input']}: {result['failures']}")

    def test_readCompressed_wrong_output(self):
        t = GENERATORS['readCompressed']('basic')[0]
        t['output'] = {'value': 99999}
        result = VALIDATORS['readCompressed'](t)
        self.assertFalse(result['pass'])


class TestSerdePipeline(unittest.TestCase):
    """Test the full generate → implement → validate pipeline."""

    def _run_pipeline(self, category, mode, seed=42, count=5):
        """Run the full pipeline in-process and return results."""
        rng = random.Random(seed)
        kwargs = {'count': count, 'rng': rng} if mode == 'random' else {}
        tests = GENERATORS[category](mode, **kwargs)

        for t in tests:
            t['output'] = PROCESSORS[category](t['input'])

        results = []
        for t in tests:
            validation = VALIDATORS[category](t)
            t['validation'] = validation
            results.append(t)

        return results

    def test_writeCompressed_basic_pipeline(self):
        results = self._run_pipeline('writeCompressed', 'basic')
        for r in results:
            self.assertTrue(r['validation']['pass'],
                            f"Failed: {r['testInfo']['testName']}: "
                            f"{r['validation']['failures']}")

    def test_writeCompressed_random_pipeline(self):
        results = self._run_pipeline('writeCompressed', 'random')
        for r in results:
            self.assertTrue(r['validation']['pass'],
                            f"Failed: {r['testInfo']['testName']}: "
                            f"{r['validation']['failures']}")

    def test_readCompressed_basic_pipeline(self):
        results = self._run_pipeline('readCompressed', 'basic')
        for r in results:
            self.assertTrue(r['validation']['pass'],
                            f"Failed: {r['testInfo']['testName']}: "
                            f"{r['validation']['failures']}")

    def test_readCompressed_random_pipeline(self):
        results = self._run_pipeline('readCompressed', 'random')
        for r in results:
            self.assertTrue(r['validation']['pass'],
                            f"Failed: {r['testInfo']['testName']}: "
                            f"{r['validation']['failures']}")

    def test_all_results_have_complete_structure(self):
        results = self._run_pipeline('writeCompressed', 'basic')
        for r in results:
            self.assertIn('testInfo', r)
            self.assertIn('input', r)
            self.assertIn('output', r)
            self.assertIn('validation', r)
            self.assertIn('testId', r['testInfo'])
            self.assertIn('testName', r['testInfo'])
            self.assertIn('category', r['testInfo'])
            self.assertIn('pass', r['validation'])
            self.assertIn('failures', r['validation'])


class TestSerdeCLI(unittest.TestCase):
    """Test the CLI entry points via subprocess."""

    def test_generate_writeCompressed_basic(self):
        result = subprocess.run(
            [sys.executable, CLI_PATH, 'generate', 'writeCompressed', 'basic'],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        tests = json.loads(result.stdout)
        self.assertEqual(len(tests), 11)

    def test_generate_writeCompressed_random_with_seed(self):
        r1 = subprocess.run(
            [sys.executable, CLI_PATH, 'generate', 'writeCompressed', 'random',
             '--seed', '42', '--count', '3'],
            capture_output=True, text=True,
        )
        r2 = subprocess.run(
            [sys.executable, CLI_PATH, 'generate', 'writeCompressed', 'random',
             '--seed', '42', '--count', '3'],
            capture_output=True, text=True,
        )
        self.assertEqual(r1.returncode, 0)
        t1 = json.loads(r1.stdout)
        t2 = json.loads(r2.stdout)
        for a, b in zip(t1, t2):
            self.assertEqual(a['input']['value'], b['input']['value'])

    def test_generate_unknown_category(self):
        result = subprocess.run(
            [sys.executable, CLI_PATH, 'generate', 'nonexistent', 'basic'],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 2)

    def test_full_cli_pipeline(self):
        gen = subprocess.run(
            [sys.executable, CLI_PATH, 'generate', 'writeCompressed', 'basic'],
            capture_output=True, text=True,
        )
        self.assertEqual(gen.returncode, 0)

        impl = subprocess.run(
            [sys.executable, REF_PATH],
            input=gen.stdout, capture_output=True, text=True,
        )
        self.assertEqual(impl.returncode, 0, impl.stderr)

        val = subprocess.run(
            [sys.executable, CLI_PATH, 'validate'],
            input=impl.stdout, capture_output=True, text=True,
        )
        self.assertEqual(val.returncode, 0, val.stderr)
        results = json.loads(val.stdout)
        for r in results:
            self.assertTrue(r['validation']['pass'],
                            f"Failed: {r['testInfo']['testName']}")

    def test_validate_ndjson_input(self):
        tests = GENERATORS['writeCompressed']('basic')[:2]
        for t in tests:
            t['output'] = PROCESSORS['writeCompressed'](t['input'])
        ndjson = '\n'.join(json.dumps(t) for t in tests)

        val = subprocess.run(
            [sys.executable, CLI_PATH, 'validate'],
            input=ndjson, capture_output=True, text=True,
        )
        self.assertEqual(val.returncode, 0, val.stderr)
        results = json.loads(val.stdout)
        self.assertEqual(len(results), 2)

    def test_validate_returns_1_on_failure(self):
        tests = GENERATORS['writeCompressed']('basic')[:1]
        tests[0]['output'] = {'dataHex': 'ff', 'bitLength': 8}
        inp = json.dumps(tests)

        val = subprocess.run(
            [sys.executable, CLI_PATH, 'validate'],
            input=inp, capture_output=True, text=True,
        )
        self.assertEqual(val.returncode, 1)

    def test_list_categories(self):
        result = subprocess.run(
            [sys.executable, CLI_PATH, 'list'],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0)
        categories = result.stdout.strip().split('\n')
        self.assertIn('writeCompressed', categories)
        self.assertIn('readCompressed', categories)


class TestSchemaValidation(unittest.TestCase):
    """Test that generated objects match the JSON schema."""

    def test_envelope_structure(self):
        tests = GENERATORS['writeCompressed']('basic')
        for t in tests:
            self.assertIn('testInfo', t)
            info = t['testInfo']
            self.assertIn('testId', info)
            self.assertIn('testName', info)
            self.assertIn('testDescription', info)
            self.assertIn('category', info)
            self.assertIn('mode', info)
            self.assertIn('input', t)

    def test_writeCompressed_input_schema(self):
        tests = GENERATORS['writeCompressed']('basic')
        for t in tests:
            self.assertIn('value', t['input'])
            v = t['input']['value']
            self.assertIsInstance(v, int)
            self.assertGreaterEqual(v, 0)
            self.assertLessEqual(v, 0xFFFFFFFF)

    def test_writeCompressed_output_schema(self):
        tests = GENERATORS['writeCompressed']('basic')
        for t in tests:
            t['output'] = PROCESSORS['writeCompressed'](t['input'])
            out = t['output']
            self.assertIn('dataHex', out)
            self.assertIn('bitLength', out)
            self.assertIsInstance(out['dataHex'], str)
            self.assertIsInstance(out['bitLength'], int)
            # Verify hex string is valid
            bytes.fromhex(out['dataHex'])


if __name__ == '__main__':
    unittest.main()
