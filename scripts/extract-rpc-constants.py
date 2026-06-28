#!/usr/bin/env python3
"""
Extract target_view from Unity RPC pcap captures.

Usage:
    python3 scripts/extract-rpc-constants.py <pcap-file> [<pcap-file>...]

Parses pcaps, decodes RPCs, and prints the constant field for each RPC
along with view ID, method name, and first-use status.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from protocol.raknet_transport import unpack_datagram
from protocol.unity_protocol import decode_rpc, compute_method_id
from protocol.bitstream import BitStream


def load_pcap_udp_payloads(pcap_path):
    try:
        from scapy.all import rdpcap, UDP
    except ImportError:
        print("ERROR: scapy not installed. Run: pip install scapy")
        sys.exit(1)

    payloads = []
    packets = rdpcap(pcap_path)
    for pkt in packets:
        if not pkt.haslayer(UDP):
            continue
        udp = pkt[UDP]
        raw_payload = bytes(udp.payload)
        if not raw_payload:
            continue
        src = (pkt.sprintf('%IP.src%'), udp.sport)
        dst = (pkt.sprintf('%IP.dst%'), udp.dport)
        payloads.append((src, dst, raw_payload))
    return payloads


def extract_constant(raw, bit_length, decoded):
    all_bits = ''.join(f'{b:08b}' for b in raw)
    method_name = decoded.get('method_name', 'unknown')

    if decoded['first_use']:
        if method_name == 'unknown':
            return None
        try:
            guid, hash_val = compute_method_id(method_name)
            method_id_bits = (len(guid) + len(hash_val)) * 8
            hash_extra_bits = method_id_bits - 48
            const_start = 160 + hash_extra_bits + 36
        except Exception:
            return None
    else:
        const_start = 120

    if const_start + 16 > len(all_bits):
        return None

    return int(all_bits[const_start:const_start + 16], 2)


def process_pcap(pcap_path):
    print(f"\n{'='*60}")
    print(f"File: {pcap_path}")
    print(f"{'='*60}")

    payloads = load_pcap_udp_payloads(pcap_path)
    print(f"  {len(payloads)} UDP packets")

    results = []
    for src, dst, data in payloads:
        result = unpack_datagram(data)
        if result[0] != 'data':
            continue

        _, timestamp, seq, messages = result
        for msg in messages:
            if not msg.payload or msg.payload[0] != 0x1b:
                continue
            if len(msg.payload) < 10 or msg.payload[9] != 0x0b:
                continue

            try:
                decoded = decode_rpc(msg.payload, msg.bit_length)
            except Exception as e:
                print(f"  [WARN] Failed to decode RPC: {e}")
                continue

            const = extract_constant(msg.payload, msg.bit_length, decoded)

            view_id = decoded['view_id']
            # Decode the 48-bit wire view_id to determine type
            # Read the raw 48-bit value from bytes 1-6
            raw_48 = int.from_bytes(msg.payload[1:7], 'big')
            # Check if it's an allocated ID (high bytes set) or scene ID
            high16 = (raw_48 >> 32) & 0xFFFF
            low32 = raw_48 & 0xFFFFFFFF
            if high16 == 0 and low32 < 50:
                view_type = f"SceneID:{low32}"
            else:
                view_type = f"AllocatedID:{low32} (h={high16})"

            direction = "C→S" if src[1] != 7777 else "S→C"

            results.append({
                'method': decoded['method_name'],
                'view_id': view_id,
                'view_type': view_type,
                'first_use': decoded['first_use'],
                'constant': const,
                'direction': direction,
                'counter': decoded['timestamp_ms'],
            })

    if not results:
        print("  No RPCs found.")
        return results

    print(f"\n  {'Dir':<4} {'Method':<30} {'ViewType':<20} {'First?':<6} {'Constant':<10} {'Counter'}")
    print(f"  {'---':<4} {'------':<30} {'--------':<20} {'------':<6} {'--------':<10} {'-------'}")
    for r in results:
        const_str = f"0x{r['constant']:04x}" if r['constant'] is not None else "???"
        first = "YES" if r['first_use'] else "no"
        print(f"  {r['direction']:<4} {r['method']:<30} {r['view_type']:<20} {first:<6} {const_str:<10} {r['counter']}")

    # Summary: unique constants
    unique = {}
    for r in results:
        key = (r['view_type'], r['method'])
        if key not in unique:
            unique[key] = r['constant']

    print(f"\n  Summary (unique view+method → constant):")
    for (vt, method), const in sorted(unique.items()):
        const_str = f"0x{const:04x}" if const is not None else "???"
        print(f"    {vt:<20} {method:<30} → {const_str}")

    return results


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <pcap-file> [<pcap-file>...]")
        sys.exit(1)

    all_results = []
    for pcap in sys.argv[1:]:
        all_results.extend(process_pcap(pcap))

    if len(sys.argv) > 2 and all_results:
        print(f"\n{'='*60}")
        print("COMBINED SUMMARY")
        print(f"{'='*60}")
        unique = {}
        for r in all_results:
            key = (r['view_type'], r['method'])
            if key not in unique:
                unique[key] = set()
            if r['constant'] is not None:
                unique[key].add(r['constant'])

        for (vt, method), consts in sorted(unique.items()):
            consts_str = ', '.join(f'0x{c:04x}' for c in sorted(consts))
            consistent = "CONSISTENT" if len(consts) == 1 else "VARIES!"
            print(f"  {vt:<20} {method:<30} → {consts_str}  [{consistent}]")


if __name__ == '__main__':
    main()
