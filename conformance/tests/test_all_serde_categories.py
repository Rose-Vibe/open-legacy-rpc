"""
Comprehensive tests for all 30 serde conformance categories.

Tests each category through the full generate → implement → validate pipeline
in both basic and random modes.
"""

import json
import random
import subprocess
import sys

import pytest

sys.path.insert(0, '.')
from conformance.generators.serde import GENERATORS
from conformance.validators.serde import VALIDATORS
from conformance.reference_implementer import PROCESSORS

ALL_CATEGORIES = sorted(GENERATORS.keys())


class TestAllCategoriesLoad:
    def test_30_generators_registered(self):
        assert len(GENERATORS) == 30

    def test_30_validators_registered(self):
        assert len(VALIDATORS) == 30

    def test_30_processors_registered(self):
        assert len(PROCESSORS) == 30

    def test_same_keys(self):
        assert set(GENERATORS.keys()) == set(VALIDATORS.keys()) == set(PROCESSORS.keys())


@pytest.mark.parametrize("category", ALL_CATEGORIES)
class TestBasicMode:
    def test_generates_nonempty(self, category):
        tests = GENERATORS[category]('basic')
        assert len(tests) > 0

    def test_has_required_fields(self, category):
        tests = GENERATORS[category]('basic')
        for t in tests:
            assert 'testInfo' in t
            assert 'input' in t
            assert t['testInfo']['category'] == category
            assert t['testInfo']['mode'] == 'basic'

    def test_pipeline_passes(self, category):
        tests = GENERATORS[category]('basic')
        for t in tests:
            out = PROCESSORS[category](t['input'])
            t['output'] = out
            result = VALIDATORS[category](t)
            assert result['pass'], (
                f"{t['testInfo']['testName']}: {result['failures']}"
            )


@pytest.mark.parametrize("category", ALL_CATEGORIES)
class TestRandomMode:
    def test_generates_requested_count(self, category):
        tests = GENERATORS[category]('random', count=5, rng=random.Random(99))
        assert len(tests) == 5

    def test_deterministic_with_seed(self, category):
        t1 = GENERATORS[category]('random', count=3, rng=random.Random(123))
        t2 = GENERATORS[category]('random', count=3, rng=random.Random(123))
        for a, b in zip(t1, t2):
            assert a['input'] == b['input']

    def test_pipeline_passes(self, category):
        tests = GENERATORS[category]('random', count=10, rng=random.Random(42))
        for t in tests:
            out = PROCESSORS[category](t['input'])
            t['output'] = out
            result = VALIDATORS[category](t)
            assert result['pass'], (
                f"{t['testInfo']['testName']}: {result['failures']}"
            )


@pytest.mark.parametrize("category", ALL_CATEGORIES)
class TestValidatorRejectsWrong:
    def test_missing_output_fails(self, category):
        tests = GENERATORS[category]('basic')
        result = VALIDATORS[category](tests[0])
        assert not result['pass']
        assert any('output' in f.lower() or 'missing' in f.lower()
                    for f in result['failures'])


class TestCLIListsAllCategories:
    def test_list_shows_30(self):
        r = subprocess.run(
            [sys.executable, '-m', 'conformance.serde_test_cli', 'list'],
            capture_output=True, text=True,
        )
        assert r.returncode == 0
        lines = [l.strip() for l in r.stdout.strip().split('\n') if l.strip()]
        assert len(lines) == 30

    def test_list_matches_registry(self):
        r = subprocess.run(
            [sys.executable, '-m', 'conformance.serde_test_cli', 'list'],
            capture_output=True, text=True,
        )
        listed = set(l.strip() for l in r.stdout.strip().split('\n') if l.strip())
        assert listed == set(ALL_CATEGORIES)


ROUNDTRIP_PAIRS = [
    ('writeCompressed', 'readCompressed'),
    ('huffman', 'huffmanDecode'),
    ('cell', 'cellDecode'),
    ('updateRow', 'updateRowDecode'),
    ('queryRequest', 'queryRequestDecode'),
    ('removeRow', 'removeRowDecode'),
    ('rpcEncode', 'rpcDecode'),
    ('rpcFirstUse', 'rpcFirstUseDecode'),
    ('stateSync', 'stateSyncDecode'),
    ('deltaStateSync', 'deltaSyncDecode'),
    ('addressEncode', 'addressDecode'),
]


@pytest.mark.parametrize("encode_cat,decode_cat", ROUNDTRIP_PAIRS)
class TestRoundtrip:
    def test_encode_decode_categories_exist(self, encode_cat, decode_cat):
        assert encode_cat in GENERATORS
        assert decode_cat in GENERATORS


class TestCLIPipeline:
    @pytest.mark.parametrize("category", ['writeCompressed', 'huffman', 'cell',
                                           'rpcEncode', 'stateSync', 'methodHash'])
    def test_cli_generate_validate_pipeline(self, category):
        gen = subprocess.run(
            [sys.executable, '-m', 'conformance.serde_test_cli',
             'generate', category, 'basic'],
            capture_output=True, text=True,
        )
        assert gen.returncode == 0
        tests = json.loads(gen.stdout)
        assert len(tests) > 0

        for t in tests:
            t['output'] = PROCESSORS[category](t['input'])

        val = subprocess.run(
            [sys.executable, '-m', 'conformance.serde_test_cli', 'validate'],
            input=json.dumps(tests), capture_output=True, text=True,
        )
        assert val.returncode == 0
