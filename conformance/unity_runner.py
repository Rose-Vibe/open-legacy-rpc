"""
Unity peer test runner for conformance testing.

Manages Unity binary processes and validates behavior by parsing
Unity's log output and observing protocol traffic from the Python side.
"""

import logging
import os
import re
import signal
import subprocess
import tempfile
import threading
import time
import uuid

from protocol.unity_client import UnityClient
from protocol.unity_server import UnityServer
from protocol.unity_protocol import RPCMode
from protocol.bitstream import BitStream

log = logging.getLogger(__name__)

DEFAULT_UNITY_PATH = os.path.join(
    os.path.dirname(__file__), '..', 'UnityProject', 'Builds', 'Linux', 'Player.x86_64')

_port_counter = 19800


def _next_port():
    global _port_counter
    _port_counter += 1
    return _port_counter


class UnityProcess:
    """Manages a Unity headless process."""

    def __init__(self, unity_path, experiment, role, port=7777,
                 address=None, extra_args=None, log_dir=None):
        self.unity_path = os.path.abspath(unity_path)
        self.experiment = experiment
        self.role = role
        self.port = port
        self.address = address
        self.extra_args = extra_args or []
        self.log_dir = log_dir or tempfile.mkdtemp(prefix='unity_test_')
        self.process = None
        self.log_path = os.path.join(self.log_dir, 'output_log.txt')
        self._log_lines = []
        self._log_thread = None

    def start(self):
        cmd = [
            self.unity_path, '-batchmode', '-nographics',
            '-logFile', self.log_path,
            '--', f'--{self.role}',
            '--experiment', self.experiment,
            '--port', str(self.port),
        ]
        if self.address:
            cmd.extend(['--address', self.address])
        cmd.extend(self.extra_args)

        log.info("Starting Unity: %s", ' '.join(cmd))
        self.process = subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self._log_thread = threading.Thread(target=self._tail_log, daemon=True)
        self._log_thread.start()

    def _tail_log(self):
        while self.process and self.process.poll() is None:
            try:
                if os.path.exists(self.log_path):
                    with open(self.log_path, 'r', errors='replace') as f:
                        lines = f.readlines()
                        self._log_lines = [l.rstrip() for l in lines]
            except Exception:
                pass
            time.sleep(0.2)
        if os.path.exists(self.log_path):
            try:
                with open(self.log_path, 'r', errors='replace') as f:
                    self._log_lines = [l.rstrip() for l in f.readlines()]
            except Exception:
                pass

    def wait_for_log(self, pattern, timeout=10.0):
        regex = re.compile(pattern)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for line in self._log_lines:
                if regex.search(line):
                    return line
            time.sleep(0.2)
        return None

    def get_experiment_logs(self):
        return [l for l in self._log_lines if '[Experiment]' in l]

    @property
    def log_lines(self):
        return list(self._log_lines)

    def stop(self, timeout=5.0):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2.0)

    @property
    def running(self):
        return self.process is not None and self.process.poll() is None


def find_unity_binary(path=None):
    """Find the Unity binary, return path or None."""
    if path and os.path.isfile(path):
        return path
    default = os.path.abspath(DEFAULT_UNITY_PATH)
    if os.path.isfile(default):
        return default
    return None


MODE_MAP = {
    'Server': RPCMode.Server, 'Others': RPCMode.Others, 'All': RPCMode.All,
    'OthersBuffered': RPCMode.OthersBuffered, 'AllBuffered': RPCMode.AllBuffered,
}


class UnityTestRunner:
    """Runs a conformance test scenario against a real Unity binary."""

    def __init__(self, scenario, unity_path=None, timeout=15.0):
        self.scenario = scenario
        self.unity_path = find_unity_binary(unity_path)
        self.timeout = timeout
        self.failures = []
        self.unity = None
        self.server = None
        self.client = None
        self.server_thread = None
        self.port = _next_port()
        self._server_connected = []
        self._server_rpcs = {}
        self._client_rpcs = {}

    def run(self):
        if not self.unity_path:
            return {
                'testInfo': self.scenario['testInfo'],
                'validation': {
                    'pass': False,
                    'failures': ['Unity binary not found'],
                    'skipped': True,
                },
            }

        try:
            for step in self.scenario.get('steps', []):
                self._execute_step(step)
                if self.failures:
                    break
        except Exception as e:
            self.failures.append(f"Step execution error: {e}")
        finally:
            self._cleanup()

        return {
            'testInfo': self.scenario['testInfo'],
            'validation': {
                'pass': len(self.failures) == 0,
                'failures': self.failures,
            },
        }

    def _cleanup(self):
        if self.client:
            try:
                self.client.disconnect()
            except Exception:
                pass
        if self.server:
            try:
                self.server.stop()
            except Exception:
                pass
        if self.server_thread and self.server_thread.is_alive():
            self.server_thread.join(timeout=2.0)
        if self.unity:
            self.unity.stop()

    def _execute_step(self, step):
        action = step['action']
        handler = getattr(self, f'_action_{action}', None)
        if handler is None:
            self.failures.append(f"Unknown action: {action}")
            return
        handler(step)

    def _action_startUnityServer(self, step):
        experiment = step['experiment']
        password_args = []
        if step.get('password'):
            password_args = ['--password', step['password']]
        self.unity = UnityProcess(
            self.unity_path, experiment, 'server',
            port=self.port, extra_args=password_args)
        self.unity.start()
        log_line = self.unity.wait_for_log(r'Server ready|Server initialized|Listening',
                                           timeout=self.timeout)
        if log_line is None:
            self.failures.append("Unity server did not become ready")

    def _action_startUnityClient(self, step):
        experiment = step['experiment']
        self.unity = UnityProcess(
            self.unity_path, experiment, 'client',
            port=self.port, address='127.0.0.1')
        self.unity.start()

    def _action_startPythonServer(self, step):
        password = step.get('password', '')
        self.server = UnityServer(port=self.port, password=password)
        self.server.start()
        self.server.on_connect(
            lambda addr, idx: self._server_connected.append({'addr': addr, 'index': idx}))
        for s in self.scenario.get('steps', []):
            method = s.get('methodName')
            if method and method not in self._server_rpcs:
                self._server_rpcs[method] = []
                m = method
                self.server.on_rpc(m, lambda addr, *args, _m=m: self._server_rpcs[_m].append(list(args)))
        self.server_thread = threading.Thread(
            target=self.server.run, args=(self.timeout + 5,), daemon=True)
        self.server_thread.start()
        time.sleep(0.1)

    def _action_connectToUnity(self, step):
        password = step.get('password', '')
        self.client = UnityClient()
        try:
            self.client.connect('127.0.0.1', self.port,
                               timeout=self.timeout, password=password)
        except TimeoutError:
            self.failures.append("Connect to Unity timed out")

    def _action_assertConnected(self, step):
        if not self.client or not self.client.connected:
            self.failures.append("Python client is not connected")

    def _action_waitForUnityLog(self, step):
        pattern = step['pattern']
        timeout = step.get('timeout', self.timeout)
        line = self.unity.wait_for_log(pattern, timeout=timeout)
        if line is None:
            self.failures.append(
                f"Unity log did not match pattern: {pattern}")

    def _action_sendRpc(self, step):
        method = step['methodName']
        params = self._decode_params(step.get('params', []))
        mode = MODE_MAP.get(step.get('mode', 'Server'), RPCMode.Server)
        view_id = step.get('viewId', 1)
        if self.client:
            self.client.send_rpc(method, params, view_id=view_id, mode=mode)
            for _ in range(5):
                self.client.poll(0.02)

    def _action_expectRpc(self, step):
        method = step['methodName']
        timeout = step.get('timeout', 5.0)

        if method not in self._client_rpcs:
            self._client_rpcs[method] = []
            m = method
            self.client.on_rpc(m, lambda *args, _m=m: self._client_rpcs[_m].append(list(args)))

        queue = self._client_rpcs[method]
        deadline = time.monotonic() + timeout
        while not queue and time.monotonic() < deadline:
            self.client.poll(0.05)

        if not queue:
            self.failures.append(f"Did not receive RPC '{method}' from Unity")
            return

        received = queue.pop(0)
        expected_params = step.get('params')
        if expected_params is not None:
            decoded = self._decode_params(expected_params)
            for i, (exp, act) in enumerate(zip(decoded, received)):
                if isinstance(exp, float):
                    if abs(exp - act) > 1e-5:
                        self.failures.append(
                            f"RPC param[{i}]: expected {exp}, got {act}")
                elif exp != act:
                    self.failures.append(
                        f"RPC param[{i}]: expected {exp!r}, got {act!r}")

    def _action_expectServerRpc(self, step):
        method = step['methodName']
        timeout = step.get('timeout', 5.0)
        queue = self._server_rpcs.setdefault(method, [])
        deadline = time.monotonic() + timeout
        while not queue and time.monotonic() < deadline:
            time.sleep(0.05)
        if not queue:
            self.failures.append(
                f"Python server did not receive RPC '{method}' from Unity")

    def _action_waitForUnityConnect(self, step):
        timeout = step.get('timeout', self.timeout)
        deadline = time.monotonic() + timeout
        while not self._server_connected and time.monotonic() < deadline:
            time.sleep(0.1)
        if not self._server_connected:
            self.failures.append("Unity client did not connect to Python server")

    def _action_disconnect(self, step):
        if self.client and self.client.connected:
            self.client.disconnect()
            time.sleep(0.3)

    def _action_sleep(self, step):
        time.sleep(step.get('duration', 0.5))

    def _decode_params(self, params):
        result = []
        for p in params:
            if isinstance(p, dict):
                if p['type'] == 'bytes':
                    result.append(bytes.fromhex(p['value']))
                elif p['type'] in ('Vector3', 'Quaternion'):
                    result.append(tuple(p['value']))
                else:
                    result.append(p['value'])
            else:
                result.append(p)
        return result


def run_unity_scenario(scenario, unity_path=None, timeout=15.0):
    """Run a single Unity peer test scenario."""
    runner = UnityTestRunner(scenario, unity_path=unity_path, timeout=timeout)
    return runner.run()
