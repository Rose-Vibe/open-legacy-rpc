#!/usr/bin/env python3
"""
Differential analysis tool for Unity legacy networking experiments.
Compares packets between pcaps or within a single pcap to find
the bytes that change when we vary one parameter.
"""
import sys
import struct
from .pcap_reader import read_pcap


def hexdump_line(data, offset=0):
    """Single line hex + ASCII."""
    hex_part = ' '.join(f'{b:02x}' for b in data)
    ascii_part = ''.join(chr(b) if 32 <= b < 127 else '.' for b in data)
    return f'{offset:04x}  {hex_part:<48s}  {ascii_part}'


def extract_payloads(pcap_path, server_port=7777):
    """Extract UDP payloads with direction info, skipping handshake."""
    packets = []
    for ts, src_port, dst_port, payload in read_pcap(pcap_path):
        if not payload:
            continue
        direction = 'C->S' if dst_port == server_port else 'S->C'
        packets.append({
            'ts': ts,
            'direction': direction,
            'src_port': src_port,
            'dst_port': dst_port,
            'payload': payload,
            'size': len(payload),
        })
    return packets


def classify_payload(payload):
    """Classify a UDP payload roughly."""
    if not payload:
        return 'empty'
    first = payload[0]

    # Offline / handshake
    if len(payload) >= 17:
        magic = bytes([0x00, 0xFF, 0xFF, 0x00, 0xFE, 0xFE, 0xFE, 0xFE,
                       0xFD, 0xFD, 0xFD, 0xFD, 0x12, 0x34, 0x56, 0x78])
        if payload[1:17] == magic or (len(payload) > 25 and payload[5:21] == magic):
            return 'handshake'

    if first == 0x05 or first == 0x06 or first == 0x07 or first == 0x08:
        return 'handshake'

    # Very short packets with high first byte are likely ACKs
    if len(payload) <= 8 and (first & 0x80):
        return 'ack'

    # Data packets - look at size to distinguish
    return 'data'


def show_packets(pcap_path, skip_handshake=True, skip_acks=True):
    """Show all packets with hex dumps, filtered."""
    print(f'\n=== {pcap_path} ===\n')
    packets = extract_payloads(pcap_path)
    for i, pkt in enumerate(packets):
        cls = classify_payload(pkt['payload'])
        if skip_handshake and cls == 'handshake':
            continue
        if skip_acks and cls == 'ack':
            continue

        print(f'Pkt {i+1}: {pkt["direction"]} {pkt["size"]}B [{cls}]')
        data = pkt['payload']
        for off in range(0, len(data), 16):
            print('  ' + hexdump_line(data[off:off+16], off))
        print()


def diff_payloads(payload_a, payload_b, label_a='A', label_b='B'):
    """Show byte-level diff between two payloads."""
    max_len = max(len(payload_a), len(payload_b))
    min_len = min(len(payload_a), len(payload_b))

    diffs = []
    for i in range(min_len):
        if payload_a[i] != payload_b[i]:
            diffs.append(i)

    if len(payload_a) != len(payload_b):
        print(f'  Length differs: {label_a}={len(payload_a)} {label_b}={len(payload_b)}')

    if not diffs and len(payload_a) == len(payload_b):
        print(f'  IDENTICAL ({len(payload_a)} bytes)')
        return

    print(f'  Differences at offsets: {diffs}')

    # Show the bytes around each diff
    for d in diffs:
        context_start = max(0, d - 2)
        context_end = min(max_len, d + 6)
        chunk_a = payload_a[context_start:context_end] if context_start < len(payload_a) else b''
        chunk_b = payload_b[context_start:context_end] if context_start < len(payload_b) else b''
        print(f'    @{d}: {label_a}=0x{payload_a[d]:02x} {label_b}=0x{payload_b[d]:02x}')
        print(f'      {label_a} ctx: {" ".join(f"{b:02x}" for b in chunk_a)}')
        print(f'      {label_b} ctx: {" ".join(f"{b:02x}" for b in chunk_b)}')


def find_value_in_payload(payload, value_bytes, label=''):
    """Find specific byte sequences in payload."""
    results = []
    for i in range(len(payload) - len(value_bytes) + 1):
        if payload[i:i+len(value_bytes)] == value_bytes:
            results.append(i)
    return results


def analyze_rpc_int(pcap_path):
    """Specifically analyze the RPC_Int experiment."""
    print(f'\n=== RPC Int Analysis: {pcap_path} ===\n')

    packets = extract_payloads(pcap_path)
    data_packets = [p for p in packets if classify_payload(p['payload']) == 'data']

    # Look for known int values in each data packet
    known_values = {
        0: struct.pack('<i', 0),
        1: struct.pack('<i', 1),
        42: struct.pack('<i', 42),
        -1: struct.pack('<i', -1),
        2147483647: struct.pack('<i', 2147483647),
    }

    for i, pkt in enumerate(data_packets):
        payload = pkt['payload']
        found = {}
        for val, val_bytes in known_values.items():
            offsets = find_value_in_payload(payload, val_bytes)
            # Filter out noise (0x00000000 appears everywhere)
            if val == 0 and len(offsets) > 3:
                continue
            if offsets:
                found[val] = offsets

        if found:
            print(f'Data pkt {i+1} ({pkt["direction"]} {len(payload)}B):')
            for off in range(0, len(payload), 16):
                print('  ' + hexdump_line(payload[off:off+16], off))
            for val, offsets in found.items():
                print(f'  ** int {val} found at offsets: {offsets}')
            print()


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Differential analysis of experiment pcaps')
    parser.add_argument('pcaps', nargs='+', help='pcap files to analyze')
    parser.add_argument('--mode', choices=['show', 'diff', 'rpc-int'], default='show',
                       help='Analysis mode')
    args = parser.parse_args()

    if args.mode == 'show':
        for path in args.pcaps:
            show_packets(path)
    elif args.mode == 'rpc-int':
        for path in args.pcaps:
            analyze_rpc_int(path)
    elif args.mode == 'diff':
        if len(args.pcaps) != 2:
            print('Diff mode requires exactly 2 pcap files')
            sys.exit(1)
        p1 = extract_payloads(args.pcaps[0])
        p2 = extract_payloads(args.pcaps[1])
        d1 = [p for p in p1 if classify_payload(p['payload']) == 'data']
        d2 = [p for p in p2 if classify_payload(p['payload']) == 'data']
        for i in range(min(len(d1), len(d2))):
            print(f'\nData packet {i+1}:')
            diff_payloads(d1[i]['payload'], d2[i]['payload'],
                         args.pcaps[0].split('/')[-1], args.pcaps[1].split('/')[-1])
