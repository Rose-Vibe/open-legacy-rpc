"""
RakNet 3.731 transport layer — construct and parse datagrams,
manage reliability, ACKs, and split packet reassembly.
"""
import struct
import time
import socket
from enum import IntEnum


OFFLINE_MAGIC = bytes([
    0x00, 0xFF, 0xFF, 0x00, 0xFE, 0xFE, 0xFE, 0xFE,
    0xFD, 0xFD, 0xFD, 0xFD, 0x12, 0x34, 0x56, 0x78
])

MTU_SIZE = 1464


class Reliability(IntEnum):
    UNRELIABLE = 0
    UNRELIABLE_SEQUENCED = 1
    RELIABLE = 2
    RELIABLE_ORDERED = 3
    RELIABLE_SEQUENCED = 4


class EncapsulatedMessage:
    __slots__ = ('reliability', 'bit_length', 'reliable_msg_number',
                 'ordering_index', 'ordering_channel',
                 'split_packet_count', 'split_packet_id', 'split_packet_index',
                 'payload')

    def __init__(self, payload=b'', reliability=Reliability.UNRELIABLE):
        self.reliability = reliability
        self.bit_length = len(payload) * 8
        self.reliable_msg_number = None
        self.ordering_index = None
        self.ordering_channel = 0
        self.split_packet_count = None
        self.split_packet_id = None
        self.split_packet_index = None
        self.payload = payload

    @property
    def has_split(self):
        return self.split_packet_count is not None

    @property
    def is_reliable(self):
        return self.reliability >= Reliability.RELIABLE

    @property
    def is_ordered(self):
        return self.reliability in (Reliability.UNRELIABLE_SEQUENCED,
                                    Reliability.RELIABLE_ORDERED,
                                    Reliability.RELIABLE_SEQUENCED)


def encode_u24_le(val):
    return bytes([val & 0xFF, (val >> 8) & 0xFF, (val >> 16) & 0xFF])


def decode_u24_le(data, offset=0):
    return data[offset] | (data[offset + 1] << 8) | (data[offset + 2] << 16)


def encode_address(ip, port):
    """Encode an IPv4 address in RakNet's bitwise-inverted format."""
    parts = [int(x) for x in ip.split('.')]
    inverted = bytes([p ^ 0xFF for p in parts])
    return inverted + struct.pack('>H', port)


def decode_address(data, offset=0):
    """Decode a RakNet bitwise-inverted IPv4 address."""
    parts = [data[offset + i] ^ 0xFF for i in range(4)]
    ip = '.'.join(str(p) for p in parts)
    port = struct.unpack('>H', data[offset + 4:offset + 6])[0]
    return ip, port


def pack_encapsulated(msg):
    """Pack an EncapsulatedMessage into bytes for inclusion in a datagram."""
    header_byte = (msg.reliability << 5)
    if msg.has_split:
        header_byte |= 0x10
    result = bytearray([header_byte])
    result += struct.pack('>H', msg.bit_length)

    if msg.is_reliable:
        result += encode_u24_le(msg.reliable_msg_number or 0)

    if msg.is_ordered:
        result += encode_u24_le(msg.ordering_index or 0)
        result.append(msg.ordering_channel)

    if msg.has_split:
        result += struct.pack('>I', msg.split_packet_count)
        result += struct.pack('>H', msg.split_packet_id)
        result += struct.pack('>I', msg.split_packet_index)

    result += msg.payload
    return bytes(result)


def unpack_encapsulated(data):
    """Unpack encapsulated messages from a datagram's message area."""
    messages = []
    pos = 0
    while pos < len(data) - 2:
        msg = EncapsulatedMessage()
        header_byte = data[pos]
        msg.reliability = (header_byte >> 5) & 0x07
        has_split = bool((header_byte >> 4) & 0x01)
        pos += 1

        if pos + 2 > len(data):
            break
        msg.bit_length = struct.unpack('>H', data[pos:pos + 2])[0]
        byte_length = (msg.bit_length + 7) // 8
        pos += 2

        if msg.is_reliable:
            if pos + 3 > len(data):
                break
            msg.reliable_msg_number = decode_u24_le(data, pos)
            pos += 3

        if msg.is_ordered:
            if pos + 4 > len(data):
                break
            msg.ordering_index = decode_u24_le(data, pos)
            pos += 3
            msg.ordering_channel = data[pos]
            pos += 1

        if has_split:
            if pos + 10 > len(data):
                break
            msg.split_packet_count = struct.unpack('>I', data[pos:pos + 4])[0]
            pos += 4
            msg.split_packet_id = struct.unpack('>H', data[pos:pos + 2])[0]
            pos += 2
            msg.split_packet_index = struct.unpack('>I', data[pos:pos + 4])[0]
            pos += 4

        end = pos + byte_length
        msg.payload = bytes(data[pos:min(end, len(data))])
        pos = end
        messages.append(msg)

    return messages


def pack_datagram(seq, messages, timestamp=0):
    """Pack a data datagram with the given sequence number and messages."""
    buf = bytearray()
    buf.append(0x84)  # data flag
    buf += struct.pack('>I', 0)  # B/AS statistics (always 0)
    buf += struct.pack('>I', timestamp)
    buf += encode_u24_le(seq)
    for msg in messages:
        buf += pack_encapsulated(msg)
    return bytes(buf)


def pack_ack(ranges, timestamp=0):
    """Pack an ACK datagram for the given sequence number ranges."""
    buf = bytearray()
    buf.append(0xC0)  # ACK flag
    buf += struct.pack('>I', 0)
    buf += struct.pack('>I', timestamp)
    buf += struct.pack('>H', len(ranges))
    for min_val, max_val in ranges:
        if min_val == max_val:
            buf.append(1)
            buf += encode_u24_le(min_val)
        else:
            buf.append(0)
            buf += encode_u24_le(min_val)
            buf += encode_u24_le(max_val)
    return bytes(buf)


def unpack_datagram(data):
    """Unpack a connected datagram.

    Returns one of:
      ('ack', timestamp, ranges)
      ('data', timestamp, seq, [EncapsulatedMessage, ...])
      ('offline', msg_id, data)
      ('unknown', data)
    """
    if not data or len(data) < 4:
        return ('unknown', data)

    first = data[0]

    if _is_offline(data):
        return ('offline', first, data)

    if len(data) < 9:
        return ('unknown', data)

    timestamp = struct.unpack('>I', data[5:9])[0]

    if (first & 0xC0) == 0xC0:
        ranges = _unpack_ack_ranges(data[9:])
        return ('ack', timestamp, ranges)

    if len(data) < 12:
        return ('unknown', data)

    seq = decode_u24_le(data, 9)
    messages = unpack_encapsulated(data[12:])
    return ('data', timestamp, seq, messages)


def _is_offline(data):
    if len(data) < 1:
        return False
    first = data[0]
    if first in (0x09, 0x0a):
        return True
    if first in (0x00, 0x01, 0x02, 0x05, 0x06, 0x07, 0x08):
        if len(data) <= 28:
            return True
    for offset in (1, 5, 9, 10, 25):
        end = offset + 16
        if end <= len(data) and data[offset:end] == OFFLINE_MAGIC:
            return True
    return False


def _unpack_ack_ranges(data):
    if len(data) < 2:
        return []
    count = struct.unpack('>H', data[0:2])[0]
    ranges = []
    pos = 2
    for _ in range(count):
        if pos >= len(data):
            break
        max_eq_min = data[pos]
        pos += 1
        if pos + 3 > len(data):
            break
        min_val = decode_u24_le(data, pos)
        pos += 3
        if max_eq_min:
            ranges.append((min_val, min_val))
        else:
            if pos + 3 > len(data):
                break
            max_val = decode_u24_le(data, pos)
            pos += 3
            ranges.append((min_val, max_val))
    return ranges


class SplitPacketAssembler:
    """Reassembles split (fragmented) encapsulated messages."""

    def __init__(self):
        self._pending = {}  # split_packet_id -> {index: payload, ...}
        self._counts = {}   # split_packet_id -> expected count

    def add(self, msg):
        """Add a split fragment. Returns the reassembled EncapsulatedMessage
        if all fragments have arrived, else None."""
        sid = msg.split_packet_id
        if sid not in self._pending:
            self._pending[sid] = {}
            self._counts[sid] = msg.split_packet_count
        self._pending[sid][msg.split_packet_index] = msg.payload

        if len(self._pending[sid]) == self._counts[sid]:
            parts = [self._pending[sid][i] for i in range(self._counts[sid])]
            full_payload = b''.join(parts)
            del self._pending[sid]
            del self._counts[sid]
            reassembled = EncapsulatedMessage(full_payload, msg.reliability)
            reassembled.reliable_msg_number = msg.reliable_msg_number
            reassembled.ordering_index = msg.ordering_index
            reassembled.ordering_channel = msg.ordering_channel
            reassembled.bit_length = len(full_payload) * 8
            return reassembled
        return None


class RakNetPeer:
    """Manages a RakNet connection: sequencing, ACKs, reliability."""

    def __init__(self, sock, remote_addr):
        self.sock = sock
        self.remote_addr = remote_addr
        self._send_seq = 0
        self._recv_seq_max = -1
        self._reliable_send_num = 0
        self._ordering_index = {}  # channel -> next ordering index
        self._connect_time = time.monotonic()
        self._split_assembler = SplitPacketAssembler()
        self._pending_acks = []
        self._unacked_reliable = {}  # datagram_seq -> (msg, send_time)

    def get_timestamp(self):
        return int((time.monotonic() - self._connect_time) * 1000) & 0xFFFFFFFF

    def send_raw(self, data):
        try:
            self.sock.sendto(data, self.remote_addr)
        except (OSError, AttributeError):
            pass

    def send_message(self, payload, reliability=Reliability.RELIABLE_ORDERED,
                     ordering_channel=0):
        """Send a Unity-layer message with the specified reliability."""
        msg = EncapsulatedMessage(payload, reliability)
        msg.bit_length = len(payload) * 8

        if msg.is_reliable:
            msg.reliable_msg_number = self._reliable_send_num
            self._reliable_send_num += 1

        if msg.is_ordered:
            ch = ordering_channel
            if ch not in self._ordering_index:
                self._ordering_index[ch] = 0
            msg.ordering_index = self._ordering_index[ch]
            self._ordering_index[ch] += 1
            msg.ordering_channel = ch

        seq = self._send_seq
        datagram = pack_datagram(seq, [msg], self.get_timestamp())
        self._send_seq += 1
        self.send_raw(datagram)

        if msg.is_reliable:
            self._unacked_reliable[seq] = (msg, time.monotonic())

    def send_unreliable(self, payload, ordering_channel=0):
        self.send_message(payload, Reliability.UNRELIABLE, ordering_channel)

    def send_unreliable_sequenced(self, payload, ordering_channel=0):
        self.send_message(payload, Reliability.UNRELIABLE_SEQUENCED, ordering_channel)

    def send_ack(self, seq):
        ack = pack_ack([(seq, seq)], self.get_timestamp())
        self.send_raw(ack)

    def flush_pending_acks(self):
        if not self._pending_acks:
            return
        ranges = []
        seqs = sorted(set(self._pending_acks))
        start = seqs[0]
        end = seqs[0]
        for s in seqs[1:]:
            if s == end + 1:
                end = s
            else:
                ranges.append((start, end))
                start = end = s
        ranges.append((start, end))
        ack = pack_ack(ranges, self.get_timestamp())
        self.send_raw(ack)
        self._pending_acks.clear()

    def handle_received(self, data):
        """Process a received UDP packet. Returns list of reassembled messages."""
        result = unpack_datagram(data)
        if result[0] == 'ack':
            _, timestamp, ranges = result
            self._handle_ack(ranges)
            return []
        elif result[0] == 'data':
            _, timestamp, seq, messages = result
            self._pending_acks.append(seq)
            if seq > self._recv_seq_max:
                self._recv_seq_max = seq
            return self._process_messages(messages)
        elif result[0] == 'offline':
            return [result]
        return []

    def _handle_ack(self, ranges):
        for min_val, max_val in ranges:
            for seq in range(min_val, max_val + 1):
                self._unacked_reliable.pop(seq, None)

    def _process_messages(self, messages):
        result = []
        for msg in messages:
            if msg.has_split:
                reassembled = self._split_assembler.add(msg)
                if reassembled is not None:
                    result.append(reassembled)
            else:
                result.append(msg)
        return result

    def check_retransmits(self, timeout=1.0):
        """Retransmit unacknowledged reliable messages after timeout."""
        now = time.monotonic()
        for old_seq, (msg, send_time) in list(self._unacked_reliable.items()):
            if now - send_time > timeout:
                new_seq = self._send_seq
                datagram = pack_datagram(new_seq, [msg], self.get_timestamp())
                self._send_seq += 1
                self.send_raw(datagram)
                del self._unacked_reliable[old_seq]
                self._unacked_reliable[new_seq] = (msg, now)
