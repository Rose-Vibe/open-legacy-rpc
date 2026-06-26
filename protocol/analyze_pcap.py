#!/usr/bin/env python3
"""
Analyze pcap files from Unity legacy networking experiments.
Dumps UDP payloads with hex + ASCII, identifies RakNet framing,
and highlights potential Unity-layer messages.
"""
import sys
import struct
from .pcap_reader import read_pcap


def hexdump(data, prefix='  '):
    """Hex + ASCII dump."""
    lines = []
    for i in range(0, len(data), 16):
        chunk = data[i:i+16]
        hex_part = ' '.join(f'{b:02x}' for b in chunk)
        ascii_part = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
        lines.append(f'{prefix}{i:04x}  {hex_part:<48s}  {ascii_part}')
    return '\n'.join(lines)


# RakNet offline message magic
OFFLINE_MAGIC = bytes([
    0x00, 0xFF, 0xFF, 0x00, 0xFE, 0xFE, 0xFE, 0xFE,
    0xFD, 0xFD, 0xFD, 0xFD, 0x12, 0x34, 0x56, 0x78
])


def classify_packet(payload):
    """Classify a UDP payload into RakNet packet types."""
    if not payload:
        return 'empty', {}

    first = payload[0]

    # Offline messages
    if first == 0x05 and len(payload) > 17 and payload[1:17] == OFFLINE_MAGIC:
        return 'open_connection_request', {'protocol_version': payload[17] if len(payload) > 17 else None}
    if first == 0x06 and len(payload) > 17 and payload[1:17] == OFFLINE_MAGIC:
        return 'open_connection_reply', {}
    if first == 0x09 and len(payload) > 17:
        return 'open_connection_request_2', {}

    # Connected datagrams: check bitflags
    # Bit 7 (MSB): is_ack
    is_ack = (first >> 7) & 1
    is_nak = (first >> 6) & 1 if not is_ack else 0

    if is_ack:
        return 'ack', {}
    if is_nak:
        return 'nak', {}

    # Data datagram - try to parse encapsulated messages
    return 'data', {'raw': payload}


def find_known_patterns(payload, context=''):
    """Look for known byte patterns in the payload."""
    findings = []

    # Look for float values we sent
    for i in range(len(payload) - 3):
        chunk = payload[i:i+4]

        # Check for known int values (little-endian)
        try:
            val_le = struct.unpack('<i', chunk)[0]
            val_be = struct.unpack('>i', chunk)[0]
            if val_le in (0, 1, 42, -1, 2147483647, 10, 20, 30, 40, 99):
                findings.append((i, f'int32_le={val_le}'))
            if val_be in (0, 1, 42, -1, 2147483647, 10, 20, 30, 40, 99) and val_be != val_le:
                findings.append((i, f'int32_be={val_be}'))
        except struct.error:
            pass

        # Check for known float values (little-endian)
        try:
            fval_le = struct.unpack('<f', chunk)[0]
            fval_be = struct.unpack('>f', chunk)[0]
            for known in [1.0, 3.14159, -1.0, 2.0, 3.0, -100.5, 0.001, 999.999, 3.14, 45.0, 90.0, 180.0]:
                if abs(fval_le - known) < 0.001:
                    findings.append((i, f'float_le={fval_le:.6f}'))
                if abs(fval_be - known) < 0.001 and abs(fval_be - fval_le) > 0.001:
                    findings.append((i, f'float_be={fval_be:.6f}'))
        except struct.error:
            pass

    # Look for known strings
    for s in [b'Hello', b'Hello World', b'hello', b'A']:
        idx = payload.find(s)
        if idx >= 0:
            findings.append((idx, f'string="{s.decode()}"'))

    # Look for known byte patterns
    idx = payload.find(b'\xDE\xAD\xBE\xEF')
    if idx >= 0:
        findings.append((idx, 'bytes=DEADBEEF'))

    return findings


def analyze_pcap(path):
    """Full analysis of a pcap file."""
    print(f'\n{"="*70}')
    print(f'Analyzing: {path}')
    print(f'{"="*70}\n')

    server_port = 7777
    packets = list(read_pcap(path))

    for i, (ts, src_port, dst_port, payload) in enumerate(packets):
        direction = 'C→S' if dst_port == server_port else 'S→C'
        ptype, info = classify_packet(payload)

        print(f'Packet {i+1}: {direction} ({src_port}→{dst_port}) {len(payload)}B  [{ptype}]')

        # Show hex dump
        print(hexdump(payload))

        # Show any found patterns
        findings = find_known_patterns(payload)
        if findings:
            print(f'  ** Found: {", ".join(f"@{off}: {desc}" for off, desc in findings)}')

        print()


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(f'Usage: {sys.argv[0]} <pcap-file> [pcap-file ...]')
        sys.exit(1)

    for path in sys.argv[1:]:
        analyze_pcap(path)
