from .handshake import generate as generate_handshake
from .rpc import generate as generate_rpc
from .state_sync import generate as generate_stateSync
from .master_server import generate as generate_masterServer
from .multi_client import generate as generate_multiClient
from .edge_cases import generate as generate_edgeCases

GENERATORS = {
    'handshake': generate_handshake,
    'rpc': generate_rpc,
    'stateSync': generate_stateSync,
    'masterServer': generate_masterServer,
    'multiClient': generate_multiClient,
    'edgeCases': generate_edgeCases,
}
