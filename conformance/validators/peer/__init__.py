from conformance.peer_runner import run_scenario

VALIDATORS = {
    'handshake': run_scenario,
    'rpc': run_scenario,
    'stateSync': run_scenario,
    'masterServer': run_scenario,
    'multiClient': run_scenario,
    'edgeCases': run_scenario,
}
