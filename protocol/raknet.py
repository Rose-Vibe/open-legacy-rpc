"""
RakNet 3.731 datagram and reliability layer parser.

Wire format (empirically determined from Unity 2018.1.6f1 captures):

OFFLINE MESSAGES: first byte is message ID, may contain offline magic.

CONNECTED DATAGRAMS:
  byte 0:     flags (0x84=data, 0xC0=ACK)
  bytes 1-4:  B/AS statistics (uint32, always 0 in practice)
  bytes 5-8:  sender timestamp (uint32 BE)

  DATA (0x84):
    bytes 9-11:  datagram sequence number (uint24 LE)
    bytes 12+:   encapsulated messages (byte-aligned)

  ACK (0xC0):
    bytes 9-10:  range count (uint16 BE)
    then ranges: for each range:
      1 byte:    max_equals_min (bool)
      3 bytes:   min sequence (uint24 LE)
      if !max_equals_min: 3 bytes max sequence (uint24 LE)

ENCAPSULATED MESSAGE (byte-aligned within message area):
  byte 0:     (reliability << 5) | (has_split << 4)
  bytes 1-2:  bit_length (uint16 BE)
  if reliable (reliability >= 2): 3 bytes reliable_msg_number (uint24 LE)
  if ordered/sequenced (reliability in {1,3,4}): 3 bytes ordering_index (uint24 LE) + 1 byte channel
  if split: 4 bytes split_count + 2 bytes split_id + 4 bytes split_index
  payload:    ceil(bit_length / 8) bytes
"""
import struct
from enum import IntEnum


OFFLINE_MESSAGE_MAGIC = bytes([
    0x00, 0xFF, 0xFF, 0x00, 0xFE, 0xFE, 0xFE, 0xFE,
    0xFD, 0xFD, 0xFD, 0xFD, 0x12, 0x34, 0x56, 0x78
])


class Reliability(IntEnum):
    UNRELIABLE = 0
    UNRELIABLE_SEQUENCED = 1
    RELIABLE = 2
    RELIABLE_ORDERED = 3
    RELIABLE_SEQUENCED = 4


class RakNetMessage:
    """A single encapsulated message within a RakNet datagram."""
    __slots__ = ('reliability', 'reliable_msg_number', 'ordering_channel',
                 'ordering_index', 'sequencing_index', 'split_packet_count',
                 'split_packet_id', 'split_packet_index', 'bit_length', 'payload')

    def __init__(self):
        self.reliability = None
        self.reliable_msg_number = None
        self.ordering_channel = None
        self.ordering_index = None
        self.sequencing_index = None
        self.split_packet_count = None
        self.split_packet_id = None
        self.split_packet_index = None
        self.bit_length = 0
        self.payload = b''

    def __repr__(self):
        r = Reliability(self.reliability).name if self.reliability is not None else '?'
        msg_id = f'0x{self.payload[0]:02x}' if self.payload else 'empty'
        s = f'RakNetMessage({msg_id}, {r}, {self.bit_length}bits/{len(self.payload)}B'
        if self.reliable_msg_number is not None:
            s += f', rel#{self.reliable_msg_number}'
        if self.ordering_index is not None:
            s += f', ord#{self.ordering_index}'
        if self.split_packet_count:
            s += f', split {self.split_packet_index}/{self.split_packet_count}'
        s += ')'
        return s


def is_offline_message(payload):
    """Check if a UDP payload is a RakNet offline/unconnected message."""
    if len(payload) < 1:
        return False
    first = payload[0]
    if first in (0x00, 0x01, 0x02, 0x05, 0x06, 0x07, 0x08):
        if len(payload) <= 28:
            return True
    for offset in (1, 5, 9, 10, 25):
        end = offset + 16
        if end <= len(payload) and payload[offset:end] == OFFLINE_MESSAGE_MAGIC:
            return True
    return False


def parse_datagram(payload):
    """
    Parse a RakNet 3.731 connected datagram (UDP payload).

    Returns one of:
      ('offline', first_byte, raw_payload)
      ('ack', timestamp, ranges)           -- ranges: list of (min, max) tuples
      ('data', timestamp, seq, [RakNetMessage, ...])
    """
    if not payload or len(payload) < 4:
        return ('empty',)

    if is_offline_message(payload):
        return ('offline', payload[0], payload)

    first = payload[0]

    if len(payload) < 9:
        return ('unknown', first, payload)

    _b_and_as = struct.unpack('>I', payload[1:5])[0]
    timestamp = struct.unpack('>I', payload[5:9])[0]

    is_ack = (first & 0xC0) == 0xC0
    is_nak = (first & 0xA0) == 0xA0 and not is_ack

    if is_ack or is_nak:
        ranges = _parse_ack_ranges(payload[9:])
        kind = 'ack' if is_ack else 'nak'
        return (kind, timestamp, ranges)

    if len(payload) < 12:
        return ('unknown', first, payload)

    seq = payload[9] | (payload[10] << 8) | (payload[11] << 16)
    messages = _parse_encapsulated_messages(payload[12:])
    return ('data', timestamp, seq, messages)


def _parse_ack_ranges(data):
    """Parse ACK/NAK range list from bytes."""
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
        min_val = data[pos] | (data[pos + 1] << 8) | (data[pos + 2] << 16)
        pos += 3
        if max_eq_min:
            ranges.append((min_val, min_val))
        else:
            if pos + 3 > len(data):
                break
            max_val = data[pos] | (data[pos + 1] << 8) | (data[pos + 2] << 16)
            pos += 3
            ranges.append((min_val, max_val))
    return ranges


def _parse_encapsulated_messages(data):
    """Parse encapsulated messages from the message area of a data datagram."""
    messages = []
    pos = 0

    while pos < len(data) - 2:
        try:
            msg = RakNetMessage()
            header_byte = data[pos]
            msg.reliability = (header_byte >> 5) & 0x07
            has_split = bool((header_byte >> 4) & 0x01)
            pos += 1

            if pos + 2 > len(data):
                break
            msg.bit_length = struct.unpack('>H', data[pos:pos + 2])[0]
            byte_length = (msg.bit_length + 7) // 8
            pos += 2

            if msg.reliability in (Reliability.RELIABLE, Reliability.RELIABLE_ORDERED,
                                   Reliability.RELIABLE_SEQUENCED):
                if pos + 3 > len(data):
                    break
                msg.reliable_msg_number = data[pos] | (data[pos + 1] << 8) | (data[pos + 2] << 16)
                pos += 3

            if msg.reliability in (Reliability.UNRELIABLE_SEQUENCED, Reliability.RELIABLE_ORDERED,
                                   Reliability.RELIABLE_SEQUENCED):
                if pos + 4 > len(data):
                    break
                msg.ordering_index = data[pos] | (data[pos + 1] << 8) | (data[pos + 2] << 16)
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
            if end > len(data):
                actual_len = len(data) - pos
                msg.payload = data[pos:]
                msg.bit_length = actual_len * 8
            else:
                msg.payload = data[pos:end]
            pos = end

            messages.append(msg)

        except (IndexError, struct.error):
            break

    return messages


def extract_unity_messages(pcap_path, server_port=7777):
    """
    High-level: read a pcap and yield parsed Unity-layer messages.

    Yields dicts with keys:
      ts, direction, datagram_seq, reliability, reliable_msg_num,
      ordering_index, msg_id, payload, bit_length
    """
    from pcap_reader import read_pcap

    for ts, src_port, dst_port, udp_payload in read_pcap(pcap_path):
        if not udp_payload:
            continue

        result = parse_datagram(udp_payload)
        if result[0] != 'data':
            continue

        _, timestamp, seq, messages = result
        direction = 'C->S' if dst_port == server_port else 'S->C'

        for msg in messages:
            if not msg.payload:
                continue
            yield {
                'ts': ts,
                'direction': direction,
                'datagram_seq': seq,
                'datagram_timestamp': timestamp,
                'reliability': msg.reliability,
                'reliable_msg_num': msg.reliable_msg_number,
                'ordering_index': msg.ordering_index,
                'ordering_channel': msg.ordering_channel,
                'msg_id': msg.payload[0],
                'payload': msg.payload,
                'bit_length': msg.bit_length,
            }
