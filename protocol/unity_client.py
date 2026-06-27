"""
High-level Unity legacy networking client.
Connects to a Unity server, sends/receives RPCs and state sync.
"""
import logging
import time

log = logging.getLogger(__name__)

from .raknet_connection import (
    RakNetClient, ConnectionState,
    ID_UNITY_RPC_OR_SYNC,
)
from .raknet_transport import Reliability
from .unity_protocol import (
    RPCMode, encode_rpc_first_use, encode_rpc_subsequent,
    decode_rpc, decode_state_sync, METHOD_SIGNATURES, is_rpc,
)
from .bitstream import BitStream


class UnityClient:
    """Client that speaks Unity's legacy networking protocol."""

    def __init__(self):
        self._raknet = RakNetClient()
        self._rpc_handlers = {}
        self._state_sync_handlers = {}
        # Pre-register all known methods so we always use subsequent-use
        # encoding (which has a known-correct wire format). First-use
        # encoding has unresolved metadata fields.
        self._rpc_sent_methods = set(METHOD_SIGNATURES.keys())
        self._rpc_counter = 0
        self._viewid_counter = 0

    @property
    def connected(self):
        return self._raknet.state == ConnectionState.CONNECTED

    @property
    def player_index(self):
        return self._raknet.player_index

    @property
    def viewid_base(self):
        return self._raknet.viewid_base

    def allocate_view_id(self):
        """Allocate a ViewID from the server-assigned range."""
        if not self.connected:
            return 0
        alloc_start = getattr(self._raknet, '_viewid_alloc_start', self._raknet.viewid_base)
        view_id = alloc_start + self._viewid_counter
        self._viewid_counter += 1
        return view_id

    def connect(self, host, port, timeout=5.0, password=''):
        self._raknet.connect(host, port, timeout, password=password)

    def disconnect(self):
        self._raknet.disconnect()

    def on_rpc(self, method_name, handler):
        """Register a handler for incoming RPCs.
        handler receives the parameter list: handler(*params)"""
        self._rpc_handlers[method_name] = handler

    def on_state_sync(self, view_id, handler):
        """Register a handler for incoming state sync.
        handler receives a BitStream positioned at the data start.
        Pass view_id=None to handle all views."""
        self._state_sync_handlers[view_id] = handler

    def send_rpc(self, method_name, params=None, view_id=1,
                 mode=RPCMode.Server, user_rpc_constant=None,
                 relay=False):
        """Send an RPC to the server."""
        params = params or []
        counter = self._rpc_counter
        self._rpc_counter += 1

        if method_name not in self._rpc_sent_methods:
            payload, bits = encode_rpc_first_use(
                method_name, params, view_id, counter, mode,
                user_rpc_constant=user_rpc_constant, relay=relay)
            self._rpc_sent_methods.add(method_name)
        else:
            payload, bits = encode_rpc_subsequent(
                method_name, params, view_id, counter, mode,
                user_rpc_constant=user_rpc_constant, relay=relay)

        msg = _make_bit_message(payload, bits, Reliability.RELIABLE_ORDERED)
        self._raknet.send_message(msg.payload, msg.reliability)

    def poll(self, timeout=0.0):
        """Poll for incoming messages. Dispatches to registered handlers."""
        messages = self._raknet.poll(timeout)
        for msg_id, payload, reliability, bit_length in messages:
            if msg_id == ID_UNITY_RPC_OR_SYNC:
                if reliability == Reliability.UNRELIABLE_SEQUENCED:
                    self._handle_state_sync(payload, bit_length)
                elif reliability == Reliability.RELIABLE_ORDERED:
                    if is_rpc(payload):
                        self._handle_rpc(payload, bit_length)
                    else:
                        self._handle_state_sync(payload, bit_length)

    def run(self, duration=None, tick_rate=15):
        """Run the client poll loop."""
        interval = 1.0 / tick_rate
        start = time.monotonic()
        while self.connected:
            if duration and (time.monotonic() - start) >= duration:
                break
            self.poll(interval)
            self._raknet.peer.check_retransmits()

    def _handle_rpc(self, payload, bit_length):
        try:
            result = decode_rpc(payload, bit_length)
        except Exception:
            log.warning("Failed to decode RPC (%d bytes)", len(payload),
                        exc_info=True)
            return
        method = result.get('method_name', '')
        if method in self._rpc_handlers:
            params = result.get('params', [])
            self._rpc_handlers[method](*params)

    def _handle_state_sync(self, payload, bit_length):
        try:
            result = decode_state_sync(payload, bit_length)
        except Exception:
            log.warning("Failed to decode state sync (%d bytes)", len(payload),
                        exc_info=True)
            return
        view_id = result['view_id']
        handler = self._state_sync_handlers.get(view_id) or \
                  self._state_sync_handlers.get(None)
        if handler:
            handler(result)


class _BitMessage:
    def __init__(self, payload, bit_length, reliability):
        self.payload = payload
        self.bit_length = bit_length
        self.reliability = reliability


def _make_bit_message(payload, bit_length, reliability):
    return _BitMessage(payload, bit_length, reliability)
