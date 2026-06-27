"""
Tests for peer (live networking) conformance test categories.

Tests each category through the full generate → run pipeline.
"""

import random
import sys

import pytest

sys.path.insert(0, '.')
from conformance.generators.peer import GENERATORS
from conformance.peer_runner import run_scenario

ALL_CATEGORIES = sorted(GENERATORS.keys())


class TestPeerCategoriesLoad:
    def test_6_generators_registered(self):
        assert len(GENERATORS) == 6

    def test_expected_categories(self):
        expected = {'handshake', 'rpc', 'stateSync', 'masterServer',
                    'multiClient', 'edgeCases'}
        assert set(GENERATORS.keys()) == expected


@pytest.mark.parametrize("category", ALL_CATEGORIES)
class TestBasicMode:
    def test_generates_nonempty(self, category):
        tests = GENERATORS[category]('basic')
        assert len(tests) > 0

    def test_has_required_fields(self, category):
        tests = GENERATORS[category]('basic')
        for t in tests:
            assert 'testInfo' in t
            assert 'steps' in t
            assert t['testInfo']['category'] == category

    def test_all_presets_pass(self, category):
        tests = GENERATORS[category]('basic')
        for t in tests:
            result = run_scenario(t, timeout=5.0)
            assert result['validation']['pass'], (
                f"{t['testInfo']['testName']}: {result['validation']['failures']}"
            )


class TestRandomMode:
    @pytest.mark.parametrize("category", ['handshake', 'rpc', 'stateSync', 'masterServer'])
    def test_random_tests_pass(self, category):
        tests = GENERATORS[category]('random', count=3, rng=random.Random(42))
        for t in tests:
            result = run_scenario(t, timeout=5.0)
            assert result['validation']['pass'], (
                f"{t['testInfo']['testName']}: {result['validation']['failures']}"
            )

    @pytest.mark.parametrize("category", ['handshake', 'rpc', 'stateSync', 'masterServer'])
    def test_random_deterministic(self, category):
        t1 = GENERATORS[category]('random', count=2, rng=random.Random(99))
        t2 = GENERATORS[category]('random', count=2, rng=random.Random(99))
        for a, b in zip(t1, t2):
            assert a['steps'] == b['steps']
