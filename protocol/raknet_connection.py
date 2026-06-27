"""
RakNet 3.731 connection lifecycle — offline handshake, connected handshake,
ping/pong, disconnect. Manages state machine for a single connection.
"""
import logging
import os
import socket
import struct
import time
import select

log = logging.getLogger(__name__)

from .raknet_transport import (
    OFFLINE_MAGIC, MTU_SIZE, Reliability, EncapsulatedMessage,
    RakNetPeer, encode_address, decode_address, unpack_datagram,
    pack_datagram, pack_ack, pack_encapsulated,
)

RAKNET_PROTOCOL_VERSION = 0x0b


# RakNet message IDs
ID_INTERNAL_PING = 0x00
ID_CONNECTED_PONG = 0x03
ID_CONNECTION_REQUEST = 0x04
ID_OPEN_CONNECTION_REQUEST = 0x09
ID_OPEN_CONNECTION_REPLY = 0x0A
ID_CONNECTION_REQUEST_ACCEPTED = 0x0E
ID_NEW_INCOMING_CONNECTION = 0x11
ID_DISCONNECTION_NOTIFICATION = 0x15
ID_DISCONNECTION_NOTIFICATION_LEGACY = 0x13

# Unity message IDs
ID_UNITY_RPC_OR_SYNC = 0x1B
ID_UNITY_PLAYER_ASSIGNMENT = 0x81
ID_UNITY_PLAYER_READY = 0x83


class ConnectionState:
    DISCONNECTED = 'disconnected'
    CONNECTING = 'connecting'
    CONNECTED = 'connected'


class RakNetClient:
    """Client-side RakNet connection to a server."""

    def __init__(self, unity_protocol=True):
        self.sock = None
        self.peer = None
        self.state = ConnectionState.DISCONNECTED
        self.player_index = None
        self.viewid_base = 0
        self.server_addr = None
        self.local_addr = None
        self._unity_protocol = unity_protocol
        self._guid = struct.unpack('>Q', os.urandom(8))[0]
        self._message_handlers = {}
        self._queued_messages = []

    def connect(self, host, port, timeout=5.0, password=''):
        """Connect to a RakNet server. Blocks until connected or timeout."""
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setblocking(False)
        self.sock.bind(('', 0))
        self.local_addr = self.sock.getsockname()
        self.server_addr = (host, port)
        self._password = password
        self.peer = RakNetPeer(self.sock, self.server_addr)
        self.state = ConnectionState.CONNECTING

        self._send_open_connection_request()

        deadline = time.monotonic() + timeout
        while self.state != ConnectionState.CONNECTED:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Connection timed out")
            msgs = self._poll(min(remaining, 0.1))
            self._queued_messages.extend(msgs)

    def disconnect(self):
        if self.peer and self.state == ConnectionState.CONNECTED:
            payload = bytes([ID_DISCONNECTION_NOTIFICATION])
            self.peer.send_message(payload, Reliability.RELIABLE_ORDERED)
        self.state = ConnectionState.DISCONNECTED
        if self.sock:
            self.sock.close()
            self.sock = None

    def send_message(self, payload, reliability=Reliability.RELIABLE_ORDERED,
                     ordering_channel=0):
        if self.peer:
            self.peer.send_message(payload, reliability, ordering_channel)

    def poll(self, timeout=0.0):
        """Poll for incoming messages. Returns list of (msg_id, payload, reliability, bit_length) tuples."""
        messages = self._queued_messages
        self._queued_messages = []
        messages.extend(self._poll(timeout))
        return messages

    def on_message(self, msg_id, handler):
        self._message_handlers[msg_id] = handler

    def _poll(self, timeout=0.0):
        messages = []
        ready, _, _ = select.select([self.sock], [], [], timeout)
        if not ready:
            return messages

        while True:
            try:
                data, addr = self.sock.recvfrom(65535)
            except (BlockingIOError, OSError):
                break

            if not data:
                continue

            if data[0] == ID_OPEN_CONNECTION_REPLY:
                self._handle_open_connection_reply(data)
                continue

            results = self.peer.handle_received(data)
            self.peer.flush_pending_acks()

            for item in results:
                if isinstance(item, tuple) and item[0] == 'offline':
                    continue
                msg = item
                if not msg.payload:
                    continue

                msg_id = msg.payload[0]
                handled = self._handle_internal(msg_id, msg.payload)
                if not handled:
                    messages.append((msg_id, msg.payload, msg.reliability,
                                     msg.bit_length))
                    if msg_id in self._message_handlers:
                        self._message_handlers[msg_id](msg.payload)

        return messages

    def _handle_internal(self, msg_id, payload):
        if msg_id == ID_CONNECTION_REQUEST_ACCEPTED:
            self._handle_connection_accepted(payload)
            return True
        elif msg_id == ID_INTERNAL_PING:
            self._handle_ping(payload)
            return True
        elif msg_id == ID_CONNECTED_PONG:
            return True
        elif msg_id == ID_UNITY_PLAYER_ASSIGNMENT:
            self._handle_player_assignment(payload)
            return True
        elif msg_id in (ID_DISCONNECTION_NOTIFICATION, ID_DISCONNECTION_NOTIFICATION_LEGACY):
            self.state = ConnectionState.DISCONNECTED
            return True
        return False

    def _send_open_connection_request(self):
        buf = bytearray(MTU_SIZE)
        buf[0] = ID_OPEN_CONNECTION_REQUEST
        buf[1] = RAKNET_PROTOCOL_VERSION
        struct.pack_into('>Q', buf, 2, self._guid)
        buf[10:26] = OFFLINE_MAGIC
        buf[26:32] = encode_address(self.server_addr[0], self.server_addr[1])
        self.sock.sendto(bytes(buf), self.server_addr)

    def _handle_open_connection_reply(self, data):
        self._send_connection_request()

    def _send_connection_request(self):
        buf = bytearray()
        buf.append(ID_CONNECTION_REQUEST)
        buf += OFFLINE_MAGIC
        buf += struct.pack('>Q', self._guid)
        if self._password:
            buf += self._password.encode('ascii')
        self.peer.send_message(bytes(buf), Reliability.RELIABLE)

    def _handle_connection_accepted(self, payload):
        local_ip = self.local_addr[0] if self.local_addr[0] != '0.0.0.0' else '127.0.0.1'
        local_port = self.local_addr[1]
        server_ip = self.server_addr[0]
        server_port = self.server_addr[1]

        # Extract external address from accepted message
        # Format: msg_id(1) + client_addr(6) + index(2) + server_addrs(10*6)
        external_addr = payload[15:21] if len(payload) > 20 else encode_address('0.0.0.0', 0)

        buf = bytearray()
        buf.append(ID_NEW_INCOMING_CONNECTION)
        buf += encode_address(server_ip, server_port)
        buf += encode_address(local_ip, local_port)
        buf += external_addr
        for _ in range(8):
            buf += encode_address('0.0.0.0', 65535)

        self.peer.send_message(bytes(buf), Reliability.RELIABLE_ORDERED)

        if self._unity_protocol:
            ready = struct.pack('>BI', ID_UNITY_PLAYER_READY, 1)
            self.peer.send_message(ready, Reliability.RELIABLE_ORDERED)
        else:
            self.state = ConnectionState.CONNECTED

    def _handle_player_assignment(self, payload):
        if len(payload) < 13:
            log.warning("Player assignment too short for player_index: %d bytes",
                        len(payload))
        if len(payload) >= 13:
            self.player_index = struct.unpack('>I', payload[9:13])[0]
        if len(payload) >= 17:
            self.viewid_base = struct.unpack('>I', payload[13:17])[0]
        if len(payload) >= 25:
            block_start = struct.unpack('>I', payload[21:25])[0]
            self._viewid_alloc_start = block_start * self.viewid_base
        else:
            self._viewid_alloc_start = self.viewid_base
        self._viewid_next = self._viewid_alloc_start
        self.state = ConnectionState.CONNECTED

    def _handle_ping(self, payload):
        if len(payload) < 5:
            return
        ping_time = struct.unpack('>I', payload[1:5])[0]
        buf = bytearray()
        buf.append(ID_CONNECTED_PONG)
        buf += struct.pack('>I', ping_time)
        buf += struct.pack('>I', self.peer.get_timestamp())
        # Pad to expected size
        while len(buf) < 17:
            buf.append(0)
        self.peer.send_message(bytes(buf), Reliability.UNRELIABLE)


class RakNetServer:
    """Server-side RakNet listener that accepts connections."""

    def __init__(self, port=7777, max_connections=4, viewid_stride=50,
                 password='', unity_protocol=True):
        self.port = port
        self.max_connections = max_connections
        self._password = password
        self.viewid_stride = viewid_stride
        self._unity_protocol = unity_protocol
        self.sock = None
        self.peers = {}  # addr -> RakNetPeer
        self.player_indices = {}  # addr -> player_index
        self._next_player_index = 1
        self._message_handlers = {}
        self._connect_handler = None
        self._disconnect_handler = None

    def start(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setblocking(False)
        self.sock.bind(('', self.port))

    def stop(self):
        for addr, peer in list(self.peers.items()):
            try:
                payload = bytes([ID_DISCONNECTION_NOTIFICATION])
                peer.send_message(payload, Reliability.RELIABLE_ORDERED)
            except OSError:
                pass
        if self.sock:
            self.sock.close()
            self.sock = None
        self.peers.clear()
        self.player_indices.clear()

    def on_connect(self, handler):
        self._connect_handler = handler

    def on_disconnect(self, handler):
        self._disconnect_handler = handler

    def on_message(self, msg_id, handler):
        self._message_handlers[msg_id] = handler

    def send_to(self, addr, payload, reliability=Reliability.RELIABLE_ORDERED,
                ordering_channel=0):
        if addr in self.peers:
            self.peers[addr].send_message(payload, reliability, ordering_channel)

    def broadcast(self, payload, reliability=Reliability.RELIABLE_ORDERED,
                  exclude=None, ordering_channel=0):
        for addr, peer in self.peers.items():
            if addr != exclude:
                peer.send_message(payload, reliability, ordering_channel)

    def poll(self, timeout=0.0):
        """Poll for incoming messages. Returns list of (addr, msg_id, payload, reliability, bit_length) tuples."""
        messages = []
        if self.sock is None:
            return messages
        try:
            ready, _, _ = select.select([self.sock], [], [], timeout)
        except (ValueError, OSError):
            return messages
        if not ready:
            return messages

        while True:
            if self.sock is None:
                break
            try:
                data, addr = self.sock.recvfrom(65535)
            except (BlockingIOError, OSError, AttributeError):
                break

            if not data:
                continue

            if data[0] == ID_OPEN_CONNECTION_REQUEST:
                self._handle_open_connection_request(addr, data)
                continue

            if addr not in self.peers:
                continue

            peer = self.peers[addr]
            results = peer.handle_received(data)
            peer.flush_pending_acks()

            for item in results:
                if isinstance(item, tuple) and item[0] == 'offline':
                    continue
                msg = item
                if not msg.payload:
                    continue

                msg_id = msg.payload[0]
                handled = self._handle_internal(addr, msg_id, msg.payload)
                if not handled:
                    messages.append((addr, msg_id, msg.payload, msg.reliability,
                                     msg.bit_length))
                    if msg_id in self._message_handlers:
                        self._message_handlers[msg_id](addr, msg.payload)

        return messages

    def _handle_internal(self, addr, msg_id, payload):
        if msg_id == ID_CONNECTION_REQUEST:
            self._handle_connection_request(addr, payload)
            return True
        elif msg_id == ID_NEW_INCOMING_CONNECTION:
            if not self._unity_protocol and self._connect_handler:
                self._connect_handler(addr, None)
            return True
        elif msg_id == ID_INTERNAL_PING:
            self._handle_ping(addr, payload)
            return True
        elif msg_id == ID_CONNECTED_PONG:
            return True
        elif msg_id == ID_UNITY_PLAYER_READY:
            if self._unity_protocol:
                self._handle_player_ready(addr, payload)
            return True
        elif msg_id in (ID_DISCONNECTION_NOTIFICATION, ID_DISCONNECTION_NOTIFICATION_LEGACY):
            self._handle_disconnect(addr)
            return True
        return False

    def _handle_open_connection_request(self, addr, data):
        if addr not in self.peers and len(self.peers) >= self.max_connections:
            log.info("Rejected connection from %s: at capacity (%d/%d)",
                     addr, len(self.peers), self.max_connections)
            return

        # Parse: msg_id(1) + version(1) + guid(8) + OFFLINE_MAGIC(16) + server_addr(6)
        # Extract client guid for cookie echo
        client_guid_upper = data[2:6] if len(data) >= 6 else b'\x00\x00\x00\x00'

        buf = bytearray(MTU_SIZE)
        buf[0] = ID_OPEN_CONNECTION_REPLY
        buf[1:17] = OFFLINE_MAGIC
        buf[17:21] = client_guid_upper
        server_nonce = os.urandom(4)
        buf[21:25] = server_nonce
        buf[25:31] = encode_address(addr[0], addr[1])
        self.sock.sendto(bytes(buf), addr)

        if addr not in self.peers:
            self.peers[addr] = RakNetPeer(self.sock, addr)

    def _handle_connection_request(self, addr, payload):
        if self._password:
            # Password follows the OFFLINE_MAGIC(16) + guid(8) in the 0x04 request
            pw_offset = 1 + 16 + 8  # msg_id + magic + guid
            client_pw = payload[pw_offset:].decode('ascii', errors='ignore')
            if client_pw != self._password:
                log.info("Rejected connection from %s: wrong password", addr)
                self.peers.pop(addr, None)
                return

        peer = self.peers[addr]
        local_ip = '127.0.0.1'
        local_port = self.port
        remote_ip, remote_port = addr

        buf = bytearray()
        buf.append(ID_CONNECTION_REQUEST_ACCEPTED)
        buf += encode_address(remote_ip, remote_port)
        buf += b'\x00\x00'  # padding
        buf += encode_address(local_ip, local_port)
        buf += encode_address(local_ip, local_port)  # external
        buf += encode_address(local_ip, local_port)  # second external
        # 8 empty address slots
        for _ in range(8):
            buf += encode_address('0.0.0.0', 65535)

        peer.send_message(bytes(buf), Reliability.RELIABLE_ORDERED)

    def _handle_player_ready(self, addr, payload):
        player_idx = self._next_player_index
        self._next_player_index += 1
        self.player_indices[addr] = player_idx

        # 0x81 format (from multi-client captures):
        #   bytes 1-4:  constant 1 (scene/level marker)
        #   bytes 5-8:  constant 0
        #   bytes 9-12: player_index (1-based, increments per client)
        #   bytes 13-16: viewid_stride (ViewIDs per block, default 50)
        #   bytes 17-20: constant 2
        #   bytes 21-24: viewid_block_start (player*2-1)
        #   bytes 25-28: viewid_block_end (player*2)
        # Client computes allocation start as: viewid_block_start * viewid_stride
        block_start = player_idx * 2 - 1
        block_end = player_idx * 2
        buf = struct.pack('>BIIIIIII',
                          ID_UNITY_PLAYER_ASSIGNMENT,
                          1, 0, player_idx, self.viewid_stride,
                          2, block_start, block_end)
        self.peers[addr].send_message(buf, Reliability.RELIABLE_ORDERED)

        if self._connect_handler:
            self._connect_handler(addr, player_idx)

    def _handle_disconnect(self, addr):
        player_idx = self.player_indices.pop(addr, None)
        self.peers.pop(addr, None)
        if self._disconnect_handler:
            self._disconnect_handler(addr, player_idx)

    def _handle_ping(self, addr, payload):
        if addr not in self.peers or len(payload) < 5:
            return
        peer = self.peers[addr]
        ping_time = struct.unpack('>I', payload[1:5])[0]
        buf = bytearray()
        buf.append(ID_CONNECTED_PONG)
        buf += struct.pack('>I', ping_time)
        buf += struct.pack('>I', peer.get_timestamp())
        while len(buf) < 17:
            buf.append(0)
        peer.send_message(bytes(buf), Reliability.UNRELIABLE)
