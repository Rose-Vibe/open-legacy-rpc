"""
High-level Unity legacy networking server.
Accepts Unity clients, sends/receives RPCs and state sync.
"""
import logging
import time

log = logging.getLogger(__name__)

from .raknet_connection import (
    RakNetServer, ID_UNITY_RPC_OR_SYNC,
)
from .raknet_transport import Reliability
from .unity_protocol import (
    RPCMode, encode_rpc_first_use, encode_rpc_subsequent,
    decode_rpc, decode_state_sync, encode_state_sync,
    encode_delta_state_sync,
    METHOD_SIGNATURES, is_rpc,
)
from .bitstream import BitStream


class UnityServer:
    """Server that speaks Unity's legacy networking protocol."""

    def __init__(self, port=7777, tick_rate=15, viewid_stride=50, password=''):
        self._raknet = RakNetServer(port=port, viewid_stride=viewid_stride,
                                    password=password)
        self._tick_rate = tick_rate
        self._viewid_stride = viewid_stride
        self._rpc_handlers = {}
        self._connect_handler = None
        self._disconnect_handler = None
        self._rpc_sent_methods = {}  # addr -> set of method names
        self._rpc_counters = {}  # addr -> counter
        self._sync_timestamp = 0
        self._view_groups = {}  # view_id -> group (default 0)
        self._send_groups = {}  # addr -> set of disabled group numbers
        self._recv_groups = {}  # addr -> set of disabled group numbers
        self._allocated_views = {}  # addr -> list of allocated view_ids
        self._view_counters = {}  # addr -> next allocation offset
        self._delta_state = {}  # (addr, view_id) -> list of prev field values
        self._view_id_scopes = {}  # view_id -> 'scene' or 'allocated'

    def start(self):
        self._raknet.start()

    def stop(self):
        self._raknet.stop()

    @property
    def peers(self):
        return dict(self._raknet.player_indices)

    def on_connect(self, handler):
        """handler(addr, player_index)"""
        def wrapped(addr, player_idx):
            self._rpc_sent_methods[addr] = set(METHOD_SIGNATURES.keys())
            self._rpc_counters[addr] = 0
            self._send_groups[addr] = set()
            self._recv_groups[addr] = set()
            self._allocated_views[addr] = []
            self._view_counters[addr] = 0
            handler(addr, player_idx)
        self._raknet.on_connect(wrapped)

    def on_disconnect(self, handler):
        """handler(addr, player_index)"""
        def wrapped(addr, player_idx):
            self._rpc_sent_methods.pop(addr, None)
            self._rpc_counters.pop(addr, None)
            self._send_groups.pop(addr, None)
            self._recv_groups.pop(addr, None)
            for vid in self._allocated_views.pop(addr, []):
                self._view_groups.pop(vid, None)
            self._view_counters.pop(addr, None)
            for key in list(self._delta_state):
                if key[0] == addr:
                    del self._delta_state[key]
            handler(addr, player_idx)
        self._raknet.on_disconnect(wrapped)

    def on_rpc(self, method_name, handler):
        """Register handler for incoming RPCs.
        handler(addr, *params)"""
        self._rpc_handlers[method_name] = handler

    def get_viewid_base(self, addr):
        """Get the ViewID allocation start for a client."""
        player_idx = self._raknet.player_indices.get(addr, 0)
        block_start = player_idx * 2 - 1
        return block_start * self._viewid_stride

    def allocate_view_id(self, addr, group=0):
        """Allocate a ViewID for a client. Returns the allocated view_id."""
        player_idx = self._raknet.player_indices.get(addr)
        if player_idx is None:
            raise ValueError(f"Unknown client: {addr}")
        base = self.get_viewid_base(addr)
        offset = self._view_counters.get(addr, 0)
        view_id = base + offset
        self._view_counters[addr] = offset + 1
        if addr not in self._allocated_views:
            self._allocated_views[addr] = []
        self._allocated_views[addr].append(view_id)
        self._view_groups[view_id] = group
        return view_id

    def get_allocated_views(self, addr):
        """Get all ViewIDs allocated for a client."""
        return list(self._allocated_views.get(addr, []))

    def set_view_group(self, view_id, group):
        """Assign a NetworkView to a group."""
        self._view_groups[view_id] = group

    def set_sending_enabled(self, addr, group, enabled):
        """Enable or disable sending messages from a group to a client."""
        if addr not in self._send_groups:
            self._send_groups[addr] = set()
        if enabled:
            self._send_groups[addr].discard(group)
        else:
            self._send_groups[addr].add(group)

    def set_receiving_enabled(self, addr, group, enabled):
        """Enable or disable receiving messages from a group from a client."""
        if addr not in self._recv_groups:
            self._recv_groups[addr] = set()
        if enabled:
            self._recv_groups[addr].discard(group)
        else:
            self._recv_groups[addr].add(group)

    def _is_send_enabled(self, addr, view_id):
        """Check if sending is enabled for this view's group to this client."""
        group = self._view_groups.get(view_id, 0)
        disabled = self._send_groups.get(addr, set())
        return group not in disabled

    def _is_recv_enabled(self, addr, view_id):
        """Check if receiving is enabled for this view's group from this client."""
        group = self._view_groups.get(view_id, 0)
        disabled = self._recv_groups.get(addr, set())
        return group not in disabled

    def send_rpc(self, method_name, params=None, target=None,
                 mode=RPCMode.All, view_id=0):
        """Send an RPC to one or all clients. Respects group filtering."""
        params = params or []

        if target:
            if self._is_send_enabled(target, view_id):
                self._send_rpc_to(target, method_name, params, view_id, mode)
        else:
            for addr in list(self._raknet.peers.keys()):
                if self._is_send_enabled(addr, view_id):
                    self._send_rpc_to(addr, method_name, params, view_id, mode)

    def send_state_sync(self, view_id, data_bs, target=None, is_first=False,
                        view_id_scope='scene'):
        """Send a state sync message to one or all clients. Respects group filtering."""
        self._sync_timestamp = (self._sync_timestamp + 83) & 0xFFFF
        payload, bits = encode_state_sync(
            view_id, self._sync_timestamp, data_bs, is_first,
            view_id_scope=view_id_scope)

        if target:
            if self._is_send_enabled(target, view_id):
                self._raknet.send_to(target, payload,
                                     Reliability.UNRELIABLE_SEQUENCED)
        else:
            for addr in list(self._raknet.peers.keys()):
                if self._is_send_enabled(addr, view_id):
                    self._raknet.send_to(addr, payload,
                                         Reliability.UNRELIABLE_SEQUENCED)

    def send_delta_state_sync(self, view_id, field_values, field_widths,
                              target=None, view_id_scope='scene'):
        """Send a ReliableDeltaCompressed state sync message.

        field_values: list of current field values
        field_widths: list of bit widths per field (typically all 32)
        Tracks previous state per-client for dirty flag computation.
        """
        self._sync_timestamp = (self._sync_timestamp + 83) & 0xFFFF
        self._view_id_scopes[view_id] = view_id_scope

        if target:
            if self._is_send_enabled(target, view_id):
                self._send_delta_to(target, view_id, field_values, field_widths)
        else:
            for addr in list(self._raknet.peers.keys()):
                if self._is_send_enabled(addr, view_id):
                    self._send_delta_to(addr, view_id, field_values, field_widths)

    def _send_delta_to(self, addr, view_id, field_values, field_widths):
        key = (addr, view_id)
        prev = self._delta_state.get(key)
        is_first = prev is None
        if is_first:
            prev = [0] * len(field_values)

        scope = self._view_id_scopes.get(view_id, 'scene')
        payload, bits = encode_delta_state_sync(
            view_id, self._sync_timestamp, field_values, prev,
            field_widths, is_first, view_id_scope=scope)

        self._delta_state[key] = list(field_values)
        self._raknet.send_to(addr, payload, Reliability.RELIABLE_ORDERED)

    def poll(self, timeout=0.0):
        """Poll for incoming messages. Dispatches to registered handlers."""
        messages = self._raknet.poll(timeout)
        for addr, msg_id, payload, reliability, bit_length in messages:
            if msg_id == ID_UNITY_RPC_OR_SYNC:
                if reliability == Reliability.UNRELIABLE_SEQUENCED:
                    pass  # state sync from client (not typical)
                elif reliability == Reliability.RELIABLE_ORDERED:
                    if is_rpc(payload):
                        self._handle_rpc(addr, payload, bit_length)
                    # else: ReliableDeltaCompressed state sync — not handled server-side

    def run(self, duration=None):
        """Run the server poll loop."""
        interval = 1.0 / self._tick_rate
        start = time.monotonic()
        while self._raknet.sock is not None:
            if duration and (time.monotonic() - start) >= duration:
                break
            self.poll(interval)
            for peer in list(self._raknet.peers.values()):
                peer.check_retransmits()

    def _send_rpc_to(self, addr, method_name, params, view_id, mode):
        if addr not in self._rpc_sent_methods:
            self._rpc_sent_methods[addr] = set()
        if addr not in self._rpc_counters:
            self._rpc_counters[addr] = 0

        counter = self._rpc_counters[addr]
        self._rpc_counters[addr] += 1

        sent = self._rpc_sent_methods[addr]
        if method_name not in sent:
            payload, bits = encode_rpc_first_use(
                method_name, params, view_id, counter, mode)
            sent.add(method_name)
        else:
            payload, bits = encode_rpc_subsequent(
                method_name, params, view_id, counter, mode)

        self._raknet.send_to(addr, payload, Reliability.RELIABLE_ORDERED)

    def _handle_rpc(self, addr, payload, bit_length):
        try:
            result = decode_rpc(payload, bit_length)
        except Exception:
            log.warning("Failed to decode RPC from %s (%d bytes)", addr,
                        len(payload), exc_info=True)
            return
        view_id = result.get('view_id', 0)
        if not self._is_recv_enabled(addr, view_id):
            return
        method = result.get('method_name', '')
        handler = self._rpc_handlers.get(method)
        if handler:
            params = result.get('params', [])
            handler(addr, *params)
