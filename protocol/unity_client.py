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
    MSG_ID_BATCH_INDEX, encode_batch_index, decode_batch_index,
)
from .bitstream import BitStream


class UnityClient:
    """Client that speaks Unity's legacy networking protocol."""

    def __init__(self):
        self._raknet = RakNetClient()
        self._rpc_handlers = {}
        self._state_sync_handlers = {}
        self._epoch = time.monotonic()
        self._viewid_counter = 0
        self._server_indices = {}  # method_name -> server's index
        self._sent_first_use = set()  # method names already sent first-use
        self._our_indices = {}  # method_name -> our assigned index
        self._our_index_reverse = {}  # our index -> method_name
        self._next_our_index = 4

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
                 mode=RPCMode.Server, *, target_view,
                 relay=False):
        """Send an RPC to the server."""
        params = params or []
        uptime_ms = int((time.monotonic() - self._epoch) * 1000)

        server_idx = self._server_indices.get(method_name)
        if server_idx is not None:
            payload, bits = encode_rpc_subsequent(
                method_name, params, view_id, uptime_ms, mode,
                target_view=target_view, relay=relay,
                method_index=server_idx)
        else:
            if method_name in self._sent_first_use:
                log.warning(
                    "Re-sending first-use RPC for %r to the same peer — "
                    "method_index is not yet registered/learned for this method, so "
                    "this send repeats the (possibly colliding) method_tag instead of "
                    "switching to subsequent-use encoding. If this persists, the method "
                    "is permanently stuck on first-use encoding.", method_name)
            self._sent_first_use.add(method_name)
            payload, bits = encode_rpc_first_use(
                method_name, params, view_id, uptime_ms, mode,
                target_view=target_view, relay=relay)

        self._raknet.send_message(payload, Reliability.RELIABLE_ORDERED,
                                  bit_length=bits)

    def poll(self, timeout=0.0):
        """Poll for incoming messages. Dispatches to registered handlers."""
        messages = self._raknet.poll(timeout)
        for msg_id, payload, reliability, bit_length in messages:
            if msg_id == MSG_ID_BATCH_INDEX:
                self._handle_batch_index(payload)
            elif msg_id == ID_UNITY_RPC_OR_SYNC:
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
            if self._raknet.peer:
                self._raknet.peer.check_retransmits()

    def _handle_rpc(self, payload, bit_length):
        try:
            result = decode_rpc(payload, bit_length,
                                 index_overrides=self._our_index_reverse)
        except Exception:
            log.warning("Failed to decode RPC (%d bytes)", len(payload),
                        exc_info=True)
            return

        if result.get('first_use'):
            method = result.get('method_name', '')
            if method and method != 'unknown':
                if method not in self._our_indices:
                    idx = self._next_our_index
                    self._next_our_index += 4
                    self._our_indices[method] = idx
                    self._our_index_reverse[idx] = method
                our_idx = self._our_indices[method]
                batch_payload, batch_bits = encode_batch_index(method, our_idx)
                self._raknet.send_message(batch_payload,
                                          Reliability.UNRELIABLE,
                                          bit_length=batch_bits)

        method = result.get('method_name', '')
        if method in self._rpc_handlers:
            params = result.get('params', [])
            self._rpc_handlers[method](*params)

    def _handle_batch_index(self, payload):
        decoded = decode_batch_index(payload)
        if not decoded or not decoded.get('method_name'):
            return
        self._server_indices[decoded['method_name']] = decoded['method_index']

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


