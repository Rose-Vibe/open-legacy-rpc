"""
Tests for Unity conformance test infrastructure.

Since Unity binaries may not be available, these tests verify:
- Scenario definitions are well-formed
- The runner handles missing binaries gracefully
- CLI integration works
- Scenarios have the expected steps
"""

import json
import subprocess
import sys

import pytest

sys.path.insert(0, '.')
from conformance.generators.unity.scenarios import SCENARIOS, get_scenario, list_scenarios
from conformance.unity_runner import UnityTestRunner, find_unity_binary, UnityProcess


class TestScenarioDefinitions:
    def test_11_scenarios_defined(self):
        assert len(SCENARIOS) == 11

    def test_expected_scenarios(self):
        expected = {
            'unity-handshake', 'unity-handshake-password',
            'unity-rpc-int', 'unity-rpc-string', 'unity-rpc-bytes',
            'unity-rpc-multitype', 'unity-rpc-receive',
            'unity-state-sync', 'unity-state-sync-delta',
            'unity-master-register', 'unity-disconnect',
        }
        assert set(SCENARIOS.keys()) == expected

    def test_all_have_required_fields(self):
        for name, scenario in SCENARIOS.items():
            assert 'testInfo' in scenario, f"{name} missing testInfo"
            assert 'steps' in scenario, f"{name} missing steps"
            assert len(scenario['steps']) > 0, f"{name} has no steps"
            assert scenario['testInfo']['category'] == name

    def test_all_steps_have_action(self):
        for name, scenario in SCENARIOS.items():
            for i, step in enumerate(scenario['steps']):
                assert 'action' in step, f"{name} step {i} missing action"

    def test_get_scenario_returns_copy(self):
        s1 = get_scenario('unity-handshake')
        s2 = get_scenario('unity-handshake')
        assert s1['testInfo']['testId'] != s2['testInfo']['testId']
        assert s1['steps'] == s2['steps']

    def test_list_scenarios_sorted(self):
        names = list_scenarios()
        assert names == sorted(names)
        assert len(names) == 11


class TestRunnerWithoutUnity:
    def test_missing_binary_reports_skipped(self, monkeypatch):
        monkeypatch.setattr(
            'conformance.unity_runner.DEFAULT_UNITY_PATH', '/nonexistent/default')
        scenario = get_scenario('unity-handshake')
        runner = UnityTestRunner(scenario, unity_path='/nonexistent/path')
        result = runner.run()
        assert not result['validation']['pass']
        assert result['validation'].get('skipped', False)
        assert 'not found' in result['validation']['failures'][0].lower()


class TestUnityProcess:
    def test_init(self):
        p = UnityProcess('/fake/path', 'TestExperiment', 'server', port=7777)
        assert p.experiment == 'TestExperiment'
        assert p.role == 'server'
        assert p.port == 7777
        assert not p.running


class TestCLI:
    def test_list_unity_scenarios(self):
        r = subprocess.run(
            [sys.executable, '-m', 'conformance.peer_test_cli', 'list', '--unity'],
            capture_output=True, text=True,
        )
        assert r.returncode == 0
        lines = [l.strip() for l in r.stdout.strip().split('\n') if l.strip()]
        assert len(lines) == 11
        assert 'unity-handshake' in lines

    def test_list_peer_categories(self):
        r = subprocess.run(
            [sys.executable, '-m', 'conformance.peer_test_cli', 'list'],
            capture_output=True, text=True,
        )
        assert r.returncode == 0
        lines = [l.strip() for l in r.stdout.strip().split('\n') if l.strip()]
        assert len(lines) == 6

    def test_unity_unknown_scenario(self):
        r = subprocess.run(
            [sys.executable, '-m', 'conformance.peer_test_cli',
             'unity', 'nonexistent', '--unity-path', '/nonexistent'],
            capture_output=True, text=True,
        )
        assert r.returncode == 2

    def test_run_peer_test_via_cli(self):
        r = subprocess.run(
            [sys.executable, '-m', 'conformance.peer_test_cli',
             'generate', 'handshake', 'basic'],
            capture_output=True, text=True,
        )
        assert r.returncode == 0
        scenarios = json.loads(r.stdout)
        assert len(scenarios) > 0

        one = json.dumps(scenarios[0])
        r2 = subprocess.run(
            [sys.executable, '-m', 'conformance.peer_test_cli', 'run'],
            input=one, capture_output=True, text=True, timeout=30,
        )
        assert r2.returncode == 0
        results = json.loads(r2.stdout)
        assert results[0]['validation']['pass']


class TestScenarioMirrorsM12c:
    """Verify each Unity scenario mirrors the corresponding M12c test."""

    def test_handshake_has_connect_step(self):
        s = get_scenario('unity-handshake')
        actions = [step['action'] for step in s['steps']]
        assert 'startUnityServer' in actions
        assert 'connectToUnity' in actions
        assert 'assertConnected' in actions

    def test_rpc_int_sends_42(self):
        s = get_scenario('unity-rpc-int')
        send_steps = [step for step in s['steps'] if step.get('action') == 'sendRpc']
        assert len(send_steps) == 1
        assert send_steps[0]['methodName'] == 'RPC_Int'
        assert send_steps[0]['params'][0]['value'] == 42

    def test_rpc_receive_expects_from_unity(self):
        s = get_scenario('unity-rpc-receive')
        expect_steps = [step for step in s['steps'] if step.get('action') == 'expectRpc']
        assert len(expect_steps) == 1
        assert expect_steps[0]['methodName'] == 'RPC_Int'

    def test_disconnect_checks_unity_log(self):
        s = get_scenario('unity-disconnect')
        log_steps = [step for step in s['steps'] if step.get('action') == 'waitForUnityLog']
        patterns = [step['pattern'] for step in log_steps]
        assert any('disconnected' in p.lower() for p in patterns)
