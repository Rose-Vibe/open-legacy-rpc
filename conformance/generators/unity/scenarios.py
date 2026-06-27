"""
Unity conformance test scenarios.

Each scenario mirrors an M12c peer test but runs against a real Unity binary.
The steps use the same action vocabulary as the peer runner plus Unity-specific
actions (startUnityServer, startUnityClient, waitForUnityLog, etc.).
"""

import uuid


def _make_scenario(name, desc, category, steps):
    return {
        'testInfo': {
            'testId': str(uuid.uuid4()),
            'testName': f"unity: {name}",
            'testDescription': desc,
            'category': category,
            'mode': 'unity',
        },
        'steps': steps,
    }


SCENARIOS = {
    'unity-handshake': _make_scenario(
        'Basic handshake',
        'Python client connects to Unity server, verifies handshake completes',
        'unity-handshake',
        [
            {'action': 'startUnityServer', 'experiment': 'ConnectExperiment'},
            {'action': 'connectToUnity'},
            {'action': 'assertConnected'},
            {'action': 'waitForUnityLog', 'pattern': r'Player connected'},
            {'action': 'disconnect'},
        ],
    ),

    'unity-handshake-password': _make_scenario(
        'Password handshake',
        'Python client connects to Unity server with password',
        'unity-handshake-password',
        [
            {'action': 'startUnityServer', 'experiment': 'PasswordExperiment',
             'password': 'test123', 'extraArgs': ['test123']},
            {'action': 'connectToUnity', 'password': 'test123'},
            {'action': 'assertConnected'},
            {'action': 'waitForUnityLog', 'pattern': r'Player connected'},
            {'action': 'disconnect'},
        ],
    ),

    'unity-rpc-int': _make_scenario(
        'Int RPC to Unity',
        'Python client sends RPC_Int(42) to Unity server',
        'unity-rpc-int',
        [
            {'action': 'startUnityServer', 'experiment': 'RpcIntExperiment'},
            {'action': 'connectToUnity'},
            {'action': 'assertConnected'},
            {'action': 'sleep', 'duration': 0.5},
            {'action': 'sendRpc', 'methodName': 'RPC_Int',
             'params': [{'type': 'int', 'value': 42}], 'mode': 'Server'},
            {'action': 'waitForUnityLog', 'pattern': r'RPC_Int.*42'},
            {'action': 'disconnect'},
        ],
    ),

    'unity-rpc-string': _make_scenario(
        'String RPC to Unity',
        'Python client sends RPC_String("hello") to Unity server',
        'unity-rpc-string',
        [
            {'action': 'startUnityServer', 'experiment': 'RpcStringExperiment'},
            {'action': 'connectToUnity'},
            {'action': 'assertConnected'},
            {'action': 'sleep', 'duration': 0.5},
            {'action': 'sendRpc', 'methodName': 'RPC_String',
             'params': [{'type': 'string', 'value': 'hello'}], 'mode': 'Server'},
            {'action': 'waitForUnityLog', 'pattern': r'RPC_String.*hello'},
            {'action': 'disconnect'},
        ],
    ),

    'unity-rpc-bytes': _make_scenario(
        'Bytes RPC to Unity',
        'Python client sends RPC_Bytes to Unity server',
        'unity-rpc-bytes',
        [
            {'action': 'startUnityServer', 'experiment': 'RpcBytesExperiment'},
            {'action': 'connectToUnity'},
            {'action': 'assertConnected'},
            {'action': 'sleep', 'duration': 0.5},
            {'action': 'sendRpc', 'methodName': 'RPC_Bytes',
             'params': [{'type': 'bytes', 'value': 'deadbeef'}], 'mode': 'Server'},
            {'action': 'waitForUnityLog', 'pattern': r'RPC_Bytes.*4 bytes'},
            {'action': 'disconnect'},
        ],
    ),

    'unity-rpc-multitype': _make_scenario(
        'Multi-param RPC to Unity',
        'Python client sends RPC_IntFloatString(1, 2.0, "hi") to Unity server',
        'unity-rpc-multitype',
        [
            {'action': 'startUnityServer', 'experiment': 'RpcMultiParamExperiment'},
            {'action': 'connectToUnity'},
            {'action': 'assertConnected'},
            {'action': 'sleep', 'duration': 0.5},
            {'action': 'sendRpc', 'methodName': 'RPC_IntFloatString',
             'params': [
                 {'type': 'int', 'value': 1},
                 {'type': 'float', 'value': 2.0},
                 {'type': 'string', 'value': 'hi'},
             ], 'mode': 'Server'},
            {'action': 'waitForUnityLog', 'pattern': r'RPC_IntFloatString.*1.*2.*hi'},
            {'action': 'disconnect'},
        ],
    ),

    'unity-rpc-receive': _make_scenario(
        'RPC from Unity to Python',
        'Unity server sends RPC_Int to Python client',
        'unity-rpc-receive',
        [
            {'action': 'startUnityServer', 'experiment': 'InteropExperiment'},
            {'action': 'connectToUnity'},
            {'action': 'assertConnected'},
            {'action': 'expectRpc', 'methodName': 'RPC_Int',
             'params': [{'type': 'int', 'value': 777}], 'timeout': 10.0},
            {'action': 'disconnect'},
        ],
    ),

    'unity-state-sync': _make_scenario(
        'State sync from Unity',
        'Unity server sends OnSerializeNetworkView state, Python client receives',
        'unity-state-sync',
        [
            {'action': 'startUnityServer', 'experiment': 'SerializeBasicExperiment'},
            {'action': 'connectToUnity'},
            {'action': 'assertConnected'},
            {'action': 'sleep', 'duration': 2.0},
            {'action': 'disconnect'},
        ],
    ),

    'unity-state-sync-delta': _make_scenario(
        'Delta compressed state sync from Unity',
        'Unity server sends ReliableDeltaCompressed state, Python client receives',
        'unity-state-sync-delta',
        [
            {'action': 'startUnityServer', 'experiment': 'DeltaCompressedExperiment'},
            {'action': 'connectToUnity'},
            {'action': 'assertConnected'},
            {'action': 'sleep', 'duration': 2.0},
            {'action': 'disconnect'},
        ],
    ),

    'unity-master-register': _make_scenario(
        'Unity registers with Python master server',
        'Unity server calls MasterServer.RegisterHost, Python master server validates',
        'unity-master-register',
        [
            {'action': 'startMasterServer'},
            {'action': 'startUnityServer', 'experiment': 'MasterServerExperiment',
             'passMasterPort': True},
            {'action': 'expectMasterRegistration', 'timeout': 15.0},
            {'action': 'sleep', 'duration': 1.0},
        ],
    ),

    'unity-disconnect': _make_scenario(
        'Disconnect cleanup',
        'Python client connects to Unity server, disconnects cleanly',
        'unity-disconnect',
        [
            {'action': 'startUnityServer', 'experiment': 'ConnectExperiment'},
            {'action': 'connectToUnity'},
            {'action': 'assertConnected'},
            {'action': 'waitForUnityLog', 'pattern': r'Player connected'},
            {'action': 'disconnect'},
            {'action': 'sleep', 'duration': 1.0},
            {'action': 'waitForUnityLog', 'pattern': r'EXPERIMENT_DONE',
             'timeout': 10.0},
        ],
    ),
}


def get_scenario(name):
    """Get a scenario by name, returning a fresh copy with a new testId."""
    import copy
    s = copy.deepcopy(SCENARIOS[name])
    s['testInfo']['testId'] = str(uuid.uuid4())
    return s


def list_scenarios():
    """List all available Unity scenario names."""
    return sorted(SCENARIOS.keys())
