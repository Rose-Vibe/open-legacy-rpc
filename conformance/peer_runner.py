"""
Step-driven peer test runner for conformance testing.

Executes test scenarios where a Python server/client pair runs through
a sequence of steps. For reference-vs-reference testing, both sides
are Python. For external implementation testing, the runner communicates
impl steps via stdin/stdout JSON lines.
"""

import logging
import struct
import threading
import time
import uuid

from protocol.unity_client import UnityClient
from protocol.unity_server import UnityServer
from protocol.unity_protocol import RPCMode
from protocol.bitstream import BitStream
from protocol.master_server import MasterServer
from protocol.master_client import MasterClient

log = logging.getLogger(__name__)

_port_counter = 18800

MODE_MAP = {
    'Server': RPCMode.Server, 'Others': RPCMode.Others, 'All': RPCMode.All,
    'OthersBuffered': RPCMode.OthersBuffered, 'AllBuffered': RPCMode.AllBuffered,
}


def _next_port():
    global _port_counter
    _port_counter += 1
    return _port_counter


SERVER_ACTIONS = {'startServer', 'assertServerConnections', 'expectServerDisconnect'}
CLIENT_ACTIONS = {
    'connect', 'disconnect', 'assertConnected', 'assertDisconnected',
    'assertPlayerIndex', 'expectConnectTimeout',
}
BOTH_ACTIONS = {'sleep', 'poll'}

SKIP_WAIT = {
    'startServer': 3.0, 'connect': 1.0, 'disconnect': 0.3,
    'sendRpc': 0.1, 'expectRpc': 0.1, 'sendStateSync': 0.1,
    'expectStateSync': 0.1, 'assertConnected': 0, 'assertDisconnected': 0,
    'assertPlayerIndex': 0, 'assertServerConnections': 0.2,
    'expectServerDisconnect': 0.5,
}


def _step_role(step):
    """Determine whether a step belongs to 'server', 'client', or 'both'."""
    action = step['action']
    if action in BOTH_ACTIONS:
        return 'both'
    if action in SERVER_ACTIONS:
        return 'server'
    if action in CLIENT_ACTIONS:
        return 'client'
    if action in ('sendRpc', 'sendStateSync'):
        return 'server' if step.get('from') == 'server' else 'client'
    if action in ('expectRpc', 'expectStateSync'):
        return 'server' if step.get('on') == 'server' else 'client'
    return 'both'


class PeerTestRunner:
    """Runs a step-driven peer test with Python-as-both-sides."""

    def __init__(self, scenario, timeout=5.0, role=None):
        self.scenario = scenario
        self.timeout = timeout
        self.role = role
        self.failures = []
        self.server = None
        self.clients = {}
        self.server_thread = None
        self.port = scenario.get('port') or _next_port()
        self._server_connected = []
        self._server_disconnected = []
        self._server_rpcs = {}
        self._client_rpcs = {}
        self._server_syncs = {}
        self._client_syncs = {}
        self._client_addrs = {}

    def run(self):
        """Execute the scenario and return validation result."""
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
        for name, client in self.clients.items():
            try:
                if client.connected:
                    client.disconnect()
            except Exception:
                pass
        if self.server:
            try:
                self.server.stop()
            except Exception:
                pass
        if self.server_thread and self.server_thread.is_alive():
            self.server_thread.join(timeout=2.0)

    def _execute_step(self, step):
        action = step['action']
        if self.role is not None:
            sr = _step_role(step)
            if sr != 'both' and sr != self.role:
                self._skip_step(step)
                return
        handler = getattr(self, f'_action_{action}', None)
        if handler is None:
            self.failures.append(f"Unknown action: {action}")
            return
        handler(step)

    def _skip_step(self, step):
        """Wait appropriately when skipping a step that belongs to the other role."""
        action = step['action']

        if self.role == 'server':
            if action == 'connect':
                client_name = step.get('client', 'default')
                expected = len(self._server_connected) + 1
                deadline = time.monotonic() + self.timeout
                while len(self._server_connected) < expected and time.monotonic() < deadline:
                    time.sleep(0.05)
                if len(self._server_connected) >= expected:
                    last = self._server_connected[-1]
                    self._client_addrs[client_name] = last['addr']
                return
            if action == 'disconnect':
                expected = len(self._server_disconnected) + 1
                deadline = time.monotonic() + self.timeout
                while len(self._server_disconnected) < expected and time.monotonic() < deadline:
                    time.sleep(0.05)
                return
            if action == 'expectConnectTimeout':
                time.sleep(step.get('timeout', 3.0))
                return

        if self.role == 'client' and action == 'startServer':
            time.sleep(3.0)
            return

        wait = SKIP_WAIT.get(action, 0.1)
        if wait > 0:
            time.sleep(wait)

    def _get_or_create_client(self, name='default'):
        if name not in self.clients:
            self.clients[name] = UnityClient()
        return self.clients[name]

    def _action_startServer(self, step):
        password = step.get('password', '')
        self.server = UnityServer(port=self.port, password=password)
        self.server.start()
        self.server.on_connect(
            lambda addr, idx: self._server_connected.append({'addr': addr, 'index': idx}))
        self.server.on_disconnect(
            lambda addr, idx: self._server_disconnected.append({'addr': addr, 'index': idx}))
        for s in self.scenario.get('steps', []):
            method = s.get('methodName')
            if method and method not in self._server_rpcs:
                self._server_rpcs[method] = []
                m = method
                self.server.on_rpc(m, lambda addr, *args, _m=m: self._server_rpcs[_m].append(list(args)))
        self.server_thread = threading.Thread(
            target=self.server.run, args=(self.timeout + 2,), daemon=True)
        self.server_thread.start()
        time.sleep(0.05)

    def _pre_register_client_handlers(self, client_name, client):
        """Eagerly register RPC and state sync handlers so messages aren't dropped."""
        for s in self.scenario.get('steps', []):
            if s['action'] == 'expectRpc':
                on = s.get('on', 'server')
                step_client = s.get('client', on)
                target_name = 'default' if step_client == 'client' else step_client
                if target_name != client_name or on == 'server':
                    continue
                method = s['methodName']
                client_key = (client_name, method)
                if client_key not in self._client_rpcs:
                    self._client_rpcs[client_key] = []
                    ck = client_key
                    m = method
                    client.on_rpc(m, lambda *args, _ck=ck: self._client_rpcs[_ck].append(list(args)))

            if s['action'] == 'expectStateSync':
                on = s.get('on', 'client')
                step_client = s.get('client', 'default') if on != 'server' else None
                target_name = 'default' if step_client == 'client' else step_client
                if target_name != client_name or on == 'server':
                    continue
                sync_key = (client_name, 'stateSync')
                if sync_key not in self._client_syncs:
                    self._client_syncs[sync_key] = []
                    sk = sync_key
                    client.on_state_sync(None, lambda result, _sk=sk: self._client_syncs[_sk].append(result))

    def _action_connect(self, step):
        client_name = step.get('client', 'default')
        password = step.get('password', '')
        client = self._get_or_create_client(client_name)
        self._pre_register_client_handlers(client_name, client)
        try:
            client.connect('127.0.0.1', self.port, timeout=self.timeout, password=password)
        except TimeoutError:
            self.failures.append(f"Connect timed out for {client_name}")
            return
        time.sleep(0.15)
        if self.server and self._server_connected:
            last = self._server_connected[-1]
            self._client_addrs[client_name] = last['addr']

    def _action_assertConnected(self, step):
        client_name = step.get('client', 'default')
        client = self.clients.get(client_name)
        if client is None:
            self.failures.append(f"No client '{client_name}' to assert")
            return
        if not client.connected:
            self.failures.append(f"Client '{client_name}' is not connected")

    def _action_assertDisconnected(self, step):
        client_name = step.get('client', 'default')
        client = self.clients.get(client_name)
        if client is None:
            return
        if client.connected:
            self.failures.append(f"Client '{client_name}' is still connected")

    def _action_assertServerConnections(self, step):
        expected = step['count']
        actual = len(self._server_connected) - len(self._server_disconnected)
        if actual != expected:
            self.failures.append(
                f"Expected {expected} server connections, got {actual}")

    def _action_assertPlayerIndex(self, step):
        client_name = step.get('client', 'default')
        expected = step['index']
        client = self.clients.get(client_name)
        if client is None:
            self.failures.append(f"No client '{client_name}'")
            return
        if client.player_index != expected:
            self.failures.append(
                f"Player index: expected {expected}, got {client.player_index}")

    def _action_disconnect(self, step):
        client_name = step.get('client', 'default')
        client = self.clients.get(client_name)
        if client and client.connected:
            client.disconnect()
            time.sleep(0.2)

    def _action_expectConnectTimeout(self, step):
        client_name = step.get('client', 'default')
        password = step.get('password', '')
        client = self._get_or_create_client(client_name)
        try:
            client.connect('127.0.0.1', self.port, timeout=step.get('timeout', 2.0),
                          password=password)
            self.failures.append(f"Expected connect to time out for {client_name}")
        except TimeoutError:
            pass

    def _action_sendRpc(self, step):
        sender = step.get('from', 'client')
        client_name = step.get('client', 'default')
        method = step['methodName']
        params = self._decode_params(step.get('params', []))
        mode = MODE_MAP.get(step.get('mode', 'Server'), RPCMode.Server)
        view_id = step.get('viewId', 1)

        target_view = step.get('targetView', 0x2000)

        if sender == 'server':
            target_client = step.get('target', client_name)
            addr = self._client_addrs.get(target_client)
            if addr and self.server:
                self.server.send_rpc(method, params, target=addr,
                                     view_id=view_id, mode=mode,
                                     target_view=target_view)
        else:
            client = self.clients.get(client_name)
            if client:
                client.send_rpc(method, params, view_id=view_id, mode=mode,
                                target_view=target_view)
                for _ in range(5):
                    client.poll(0.02)

    def _action_expectRpc(self, step):
        receiver = step.get('on', 'server')
        method = step['methodName']
        expected_params = step.get('params')
        timeout = step.get('timeout', 2.0)

        received = []

        if receiver == 'server':
            queue = self._server_rpcs.setdefault(method, [])
            deadline = time.monotonic() + timeout
            while not queue and time.monotonic() < deadline:
                time.sleep(0.05)
            if queue:
                received.append(queue.pop(0))
        else:
            client_name = step.get('client', receiver)
            client = self.clients.get(client_name)
            if client is None:
                self.failures.append(f"No client '{client_name}' for expectRpc")
                return
            client_key = (client_name, method)
            if client_key not in self._client_rpcs:
                self._client_rpcs[client_key] = []
                m = method
                ck = client_key
                client.on_rpc(m, lambda *args, _ck=ck: self._client_rpcs[_ck].append(list(args)))
            queue = self._client_rpcs[client_key]
            deadline = time.monotonic() + timeout
            while not queue and time.monotonic() < deadline:
                client.poll(0.05)
            if queue:
                received.append(queue.pop(0))

        if not received:
            self.failures.append(f"Did not receive RPC '{method}' within {timeout}s")
            return

        if expected_params is not None:
            decoded_expected = self._decode_params(expected_params)
            actual = received[0]
            if len(actual) != len(decoded_expected):
                self.failures.append(
                    f"RPC '{method}' param count: expected {len(decoded_expected)}, got {len(actual)}")
                return
            for i, (exp, act) in enumerate(zip(decoded_expected, actual)):
                if isinstance(exp, float):
                    if abs(exp - act) > 1e-5:
                        self.failures.append(
                            f"RPC '{method}' param[{i}]: expected {exp}, got {act}")
                elif isinstance(exp, (list, tuple)):
                    for j, (e, a) in enumerate(zip(exp, act)):
                        if isinstance(e, float) and abs(e - a) > 1e-5:
                            self.failures.append(
                                f"RPC '{method}' param[{i}][{j}]: expected {e}, got {a}")
                            break
                elif exp != act:
                    self.failures.append(
                        f"RPC '{method}' param[{i}]: expected {exp!r}, got {act!r}")

    def _action_sendStateSync(self, step):
        sender = step.get('from', 'server')
        view_id = step.get('viewId', 1)
        fields = step.get('fields', [])

        data_bs = BitStream()
        for f in fields:
            ftype, val = f['type'], f['value']
            if ftype == 'int':
                data_bs.write_i32_be(val)
            elif ftype == 'float':
                data_bs.write_float_be(val)
            elif ftype == 'Vector3':
                for v in val:
                    data_bs.write_float_be(v)
            elif ftype == 'Quaternion':
                for v in val:
                    data_bs.write_float_be(v)
            elif ftype == 'short':
                data_bs.write_bits(val & 0xFFFF, 16)

        if sender == 'server':
            client_name = step.get('target', 'default')
            addr = self._client_addrs.get(client_name)
            if self.server and addr:
                self.server.send_state_sync(view_id, data_bs, target=addr)
        else:
            client_name = step.get('client', 'default')
            client = self.clients.get(client_name)
            if client:
                pass  # Client-to-server state sync not typically used

    def _action_expectStateSync(self, step):
        receiver = step.get('on', 'client')
        view_id = step.get('viewId', 1)
        expected_fields = step.get('fields', [])
        timeout = step.get('timeout', 2.0)

        received = []

        if receiver == 'client' or receiver in self.clients:
            client_name = receiver if receiver in self.clients else 'default'
            client = self.clients.get(client_name)
            if client is None:
                self.failures.append(f"No client '{client_name}' for expectStateSync")
                return

            sync_key = (client_name, 'stateSync')
            queue = self._client_syncs.get(sync_key)
            if queue is not None:
                deadline = time.monotonic() + timeout
                while not queue and time.monotonic() < deadline:
                    client.poll(0.05)
                for item in queue:
                    if item.get('view_id') == view_id:
                        received.append(item)
                        queue.remove(item)
                        break
            else:
                def handler(result):
                    received.append(result)
                client.on_state_sync(view_id, handler)
                deadline = time.monotonic() + timeout
                while not received and time.monotonic() < deadline:
                    client.poll(0.05)
                client.on_state_sync(view_id, lambda r: None)

        if not received:
            self.failures.append(
                f"Did not receive state sync for view {view_id} within {timeout}s")
            return

        if expected_fields:
            data = received[0].get('data_stream')
            if data is None:
                self.failures.append("State sync has no data_stream")
                return
            for i, f in enumerate(expected_fields):
                ftype = f['type']
                expected_val = f['value']
                try:
                    if ftype == 'int':
                        actual = data.read_i32_be()
                    elif ftype == 'float':
                        actual = data.read_float_be()
                    elif ftype == 'Vector3':
                        actual = [data.read_float_be() for _ in range(3)]
                    elif ftype == 'Quaternion':
                        actual = [data.read_float_be() for _ in range(4)]
                    elif ftype == 'short':
                        actual = data.read_bits(16)
                    else:
                        continue
                except Exception as e:
                    self.failures.append(f"Failed to read field[{i}]: {e}")
                    return

                if isinstance(expected_val, float):
                    if abs(expected_val - actual) > 1e-5:
                        self.failures.append(
                            f"State sync field[{i}]: expected {expected_val}, got {actual}")
                elif isinstance(expected_val, list):
                    for j, (e, a) in enumerate(zip(expected_val, actual)):
                        if isinstance(e, float) and abs(e - a) > 1e-5:
                            self.failures.append(
                                f"State sync field[{i}][{j}]: expected {e}, got {a}")
                            break
                elif expected_val != actual:
                    self.failures.append(
                        f"State sync field[{i}]: expected {expected_val}, got {actual}")

    def _action_sleep(self, step):
        time.sleep(step.get('duration', 0.1))

    def _action_poll(self, step):
        client_name = step.get('client', 'default')
        duration = step.get('duration', 0.2)
        client = self.clients.get(client_name)
        if client:
            deadline = time.monotonic() + duration
            while time.monotonic() < deadline:
                client.poll(0.05)

    def _action_expectServerDisconnect(self, step):
        client_name = step.get('client', 'default')
        expected_count = step.get('count', 1)
        timeout = step.get('timeout', 2.0)
        deadline = time.monotonic() + timeout
        while len(self._server_disconnected) < expected_count and time.monotonic() < deadline:
            time.sleep(0.05)
        if len(self._server_disconnected) < expected_count:
            self.failures.append(
                f"Expected {expected_count} server disconnect(s), got {len(self._server_disconnected)}")

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


class MasterServerTestRunner:
    """Runs master server peer tests with Python-as-both-sides."""

    def __init__(self, scenario, timeout=5.0):
        self.scenario = scenario
        self.timeout = timeout
        self.failures = []
        self.master = None
        self.master_thread = None
        self.clients = {}
        self.port = _next_port()
        self._row_ids = {}
        self._host_lists = {}

    def run(self):
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
        for name, client in self.clients.items():
            try:
                if client.connected:
                    client.disconnect()
            except Exception:
                pass
        if self.master:
            try:
                self.master.stop()
            except Exception:
                pass
        if self.master_thread and self.master_thread.is_alive():
            self.master_thread.join(timeout=2.0)

    def _execute_step(self, step):
        action = step['action']
        handler = getattr(self, f'_action_{action}', None)
        if handler is None:
            self.failures.append(f"Unknown action: {action}")
            return
        handler(step)

    def _get_or_create_client(self, name='default'):
        if name not in self.clients:
            self.clients[name] = MasterClient()
        return self.clients[name]

    def _action_startMasterServer(self, step):
        self.master = MasterServer(port=self.port)
        self.master.start()
        self.master_thread = threading.Thread(
            target=self._run_master, daemon=True)
        self.master_thread.start()
        time.sleep(0.1)

    def _run_master(self):
        deadline = time.monotonic() + self.timeout + 5
        while time.monotonic() < deadline:
            try:
                self.master.tick(timeout=0.05)
            except Exception:
                break

    def _action_connectMaster(self, step):
        client_name = step.get('client', 'default')
        client = self._get_or_create_client(client_name)
        try:
            client.connect('127.0.0.1', self.port, timeout=self.timeout)
        except TimeoutError:
            self.failures.append(f"Master connect timed out for {client_name}")

    def _action_registerHost(self, step):
        client_name = step.get('client', 'default')
        client = self.clients.get(client_name)
        if client is None:
            self.failures.append(f"No client '{client_name}' for registerHost")
            return
        try:
            row_id = client.register_host(
                game_type=step['gameType'],
                name=step.get('name', 'TestServer'),
                comment=step.get('comment', ''),
                player_count=step.get('playerCount', 0),
                player_limit=step.get('playerLimit', 4),
                port=step.get('port', 7777),
                timeout=self.timeout,
            )
            reg_key = step.get('regKey', client_name)
            self._row_ids[reg_key] = row_id
        except Exception as e:
            self.failures.append(f"registerHost failed: {e}")

    def _action_requestHostList(self, step):
        client_name = step.get('client', 'default')
        client = self.clients.get(client_name)
        if client is None:
            self.failures.append(f"No client '{client_name}' for requestHostList")
            return
        try:
            hosts = client.request_host_list(
                step['gameType'], timeout=self.timeout)
            result_key = step.get('resultKey', 'default')
            self._host_lists[result_key] = hosts
        except TimeoutError:
            self._host_lists[step.get('resultKey', 'default')] = []
            if not step.get('allowEmpty', False):
                self.failures.append("requestHostList timed out")

    def _action_assertHostCount(self, step):
        result_key = step.get('resultKey', 'default')
        hosts = self._host_lists.get(result_key, [])
        expected = step['count']
        if len(hosts) != expected:
            self.failures.append(
                f"Expected {expected} hosts, got {len(hosts)}")

    def _action_assertHostField(self, step):
        result_key = step.get('resultKey', 'default')
        hosts = self._host_lists.get(result_key, [])
        idx = step.get('index', 0)
        if idx >= len(hosts):
            self.failures.append(
                f"Host index {idx} out of range (have {len(hosts)})")
            return
        field = step['field']
        expected = step['value']
        actual = hosts[idx].get(field)
        if actual != expected:
            self.failures.append(
                f"Host[{idx}].{field}: expected {expected!r}, got {actual!r}")

    def _action_unregisterHost(self, step):
        client_name = step.get('client', 'default')
        client = self.clients.get(client_name)
        if client is None:
            self.failures.append(f"No client '{client_name}' for unregisterHost")
            return
        reg_key = step.get('regKey', client_name)
        row_id = self._row_ids.get(reg_key)
        try:
            client.unregister_host(step['gameType'], row_id=row_id)
            time.sleep(0.2)
        except Exception as e:
            self.failures.append(f"unregisterHost failed: {e}")

    def _action_disconnectMaster(self, step):
        client_name = step.get('client', 'default')
        client = self.clients.get(client_name)
        if client and client.connected:
            client.disconnect()
            time.sleep(0.3)

    def _action_sleep(self, step):
        time.sleep(step.get('duration', 0.1))


def run_scenario(scenario, timeout=5.0, role=None):
    """Run a single peer test scenario and return the result."""
    category = scenario.get('testInfo', {}).get('category', '')
    if category == 'masterServer':
        runner = MasterServerTestRunner(scenario, timeout=timeout)
    else:
        runner = PeerTestRunner(scenario, timeout=timeout, role=role)
    return runner.run()
