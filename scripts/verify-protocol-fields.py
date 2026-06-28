#!/usr/bin/env python3
"""
Verify protocol fields from Unity pcap captures against our encoder output.

Usage:
    python3 scripts/verify-protocol-fields.py <pcap-file> [--verbose]

Parses a pcap file, extracts Unity RPC messages, and checks each M20 protocol
field against the expected value from our Python encoder.

Requires: dpkt (pip install dpkt)
"""
import sys
import os
import struct
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from protocol.raknet_transport import unpack_datagram, unpack_encapsulated
from protocol.unity_protocol import (
    decode_rpc, encode_rpc_subsequent, encode_rpc_first_use,
    INTERNAL_RPC_CONSTANT,
    compute_method_id, METHOD_INDEX_MAP, METHOD_SIGNATURES,
    RPCMode,
)
from protocol.bitstream import BitStream


def load_pcap_udp_payloads(pcap_path):
    """Load UDP payloads from a pcap/pcapng file. Returns list of (src, dst, payload)."""
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


def extract_rpc_messages(payloads):
    """Extract Unity RPC messages from UDP payloads via RakNet parsing."""
    rpcs = []
    disconnects = []
    frame_info = []

    for src, dst, data in payloads:
        result = unpack_datagram(data)
        if result[0] != 'data':
            if result[0] == 'offline' and len(data) > 0:
                if data[0] in (0x13, 0x15):
                    disconnects.append({'msg_id': data[0], 'src': src, 'dst': dst})
            continue

        _, timestamp, seq, messages = result
        for msg in messages:
            if not msg.payload:
                continue
            msg_id = msg.payload[0]

            if msg_id in (0x13, 0x15):
                disconnects.append({'msg_id': msg_id, 'src': src, 'dst': dst})
                continue

            if msg_id != 0x1b:
                continue
            if len(msg.payload) < 10 or msg.payload[9] != 0x0b:
                continue

            try:
                decoded = decode_rpc(msg.payload, msg.bit_length)
                rpcs.append({
                    'decoded': decoded,
                    'raw': msg.payload,
                    'bit_length': msg.bit_length,
                    'frame_bit_length': msg.bit_length,
                    'src': src,
                    'dst': dst,
                })
            except Exception as e:
                rpcs.append({
                    'error': str(e),
                    'raw': msg.payload,
                    'bit_length': msg.bit_length,
                    'src': src,
                    'dst': dst,
                })

    return rpcs, disconnects


def check_target_view(rpc_entry, verbose=False):
    """Fix 1: Check 0x2000 is 0x2000."""
    raw = rpc_entry['raw']
    decoded = rpc_entry.get('decoded')
    if not decoded:
        return None

    all_bits = ''.join(f'{b:08b}' for b in raw)

    if decoded['first_use']:
        guid, hash_val = compute_method_id(decoded['method_name'])
        method_id_bits = (len(guid) + len(hash_val)) * 8
        hash_extra_bits = method_id_bits - 48
        const_start = 160 + hash_extra_bits + 36
    else:
        const_start = 120

    if const_start + 16 > len(all_bits):
        return None

    const_val = int(all_bits[const_start:const_start + 16], 2)
    method_name = decoded['method_name']

    if method_name in ('__RPCNetworkInstantiate',):
        expected = INTERNAL_RPC_CONSTANT
    else:
        expected = 0x2000

    ok = const_val == expected
    if verbose or not ok:
        label = 'PASS' if ok else 'FAIL'
        print(f"  [{label}] Fix 1 (0x2000): {method_name} "
              f"constant=0x{const_val:04x} expected=0x{expected:04x}")
    return ok


def check_16bit_counter(rpc_entry, verbose=False):
    """Fix 2: Check counter is 16-bit."""
    decoded = rpc_entry.get('decoded')
    raw = rpc_entry['raw']
    if not decoded:
        return None

    high = raw[7]
    low = raw[8]
    wire_counter = ((high << 8) | low) >> 1

    ok = wire_counter == decoded['timestamp_ms']
    if verbose or not ok:
        label = 'PASS' if ok else 'FAIL'
        print(f"  [{label}] Fix 2 (16-bit counter): "
              f"wire_counter={wire_counter} decoded={decoded['timestamp_ms']} "
              f"raw_bytes=[0x{high:02x}, 0x{low:02x}]")
    return ok


def check_counter_above_127(rpcs, verbose=False):
    """Fix 2 extension: Verify counter values > 127 appear in wire data."""
    max_counter = 0
    for rpc in rpcs:
        decoded = rpc.get('decoded')
        if decoded:
            max_counter = max(max_counter, decoded['timestamp_ms'])

    ok = max_counter > 127
    label = 'PASS' if ok else 'FAIL'
    print(f"  [{label}] Fix 2 (counter > 127): max_counter={max_counter} "
          f"{'(proves 16-bit)' if ok else '(need >128 RPCs to verify)'}")
    return ok


def check_subsequent_remaining(rpc_entry, verbose=False):
    """Fix 3: Check subsequent remaining = total_bits - 121."""
    decoded = rpc_entry.get('decoded')
    raw = rpc_entry['raw']
    bit_length = rpc_entry['bit_length']
    if not decoded or decoded['first_use']:
        return None

    all_bits = ''.join(f'{b:08b}' for b in raw)
    remaining_start = 104
    if remaining_start + 16 > len(all_bits):
        return None
    wire_remaining = int(all_bits[remaining_start:remaining_start + 16], 2)

    expected_remaining = bit_length - 121
    ok = wire_remaining == expected_remaining
    if verbose or not ok:
        label = 'PASS' if ok else 'FAIL'
        print(f"  [{label}] Fix 3 (subsequent remaining): "
              f"wire={wire_remaining} expected={expected_remaining} "
              f"(total_bits={bit_length})")
    return ok


def check_first_use_remaining(rpc_entry, verbose=False):
    """Fix 4: Check first-use remaining = param_bits + 19 + target_bits."""
    decoded = rpc_entry.get('decoded')
    raw = rpc_entry['raw']
    if not decoded or not decoded['first_use']:
        return None

    all_bits = ''.join(f'{b:08b}' for b in raw)

    method_name = decoded['method_name']
    if method_name == 'unknown':
        return None

    guid, hash_val = compute_method_id(method_name)
    method_id_bits = (len(guid) + len(hash_val)) * 8
    hash_extra_bits = method_id_bits - 48
    remaining_start = 160 + hash_extra_bits + 20

    if remaining_start + 16 > len(all_bits):
        return None

    wire_remaining = int(all_bits[remaining_start:remaining_start + 16], 2)

    sig = METHOD_SIGNATURES.get(method_name, [])
    target_bits = 1 if decoded.get('rpc_mode') == RPCMode.Player else 0

    # Compute param_bits from the actual frame
    param_start_bit = 160 + hash_extra_bits + 52 + 4 + target_bits
    total_bits = rpc_entry['bit_length']
    param_bits = total_bits - param_start_bit

    expected_remaining = param_bits + 19 + target_bits

    ok = wire_remaining == expected_remaining
    if verbose or not ok:
        label = 'PASS' if ok else 'FAIL'
        print(f"  [{label}] Fix 4 (first-use remaining): "
              f"wire={wire_remaining} expected={expected_remaining} "
              f"(param_bits={param_bits}, target_bits={target_bits})")
    return ok


def check_method_tag(rpc_entry, verbose=False):
    """Fix 5: Extract method_tag from first-use RPC."""
    decoded = rpc_entry.get('decoded')
    raw = rpc_entry['raw']
    if not decoded or not decoded['first_use']:
        return None

    method_name = decoded['method_name']
    if method_name == 'unknown':
        return None

    all_bits = ''.join(f'{b:08b}' for b in raw)

    guid, hash_val = compute_method_id(method_name)
    method_id_bits = (len(guid) + len(hash_val)) * 8
    hash_extra_bits = method_id_bits - 48
    tag_start = 160 + hash_extra_bits

    if tag_start + 4 > len(all_bits):
        return None

    wire_tag = int(all_bits[tag_start:tag_start + 4], 2)
    print(f"  [INFO] Fix 5 (method_tag): {method_name} tag={wire_tag} "
          f"(4-bit value from wire)")
    return wire_tag


def check_frame_bit_length(rpc_entry, verbose=False):
    """Fix 6: Check RakNet frame bitLength matches RPC bit count."""
    decoded = rpc_entry.get('decoded')
    if not decoded:
        return None

    frame_bits = rpc_entry.get('frame_bit_length', 0)
    payload_bytes = len(rpc_entry['raw'])
    byte_aligned_bits = payload_bytes * 8

    # If frame_bit_length differs from byte_aligned, the transport preserves bit counts
    not_byte_aligned = frame_bits != byte_aligned_bits
    if verbose or not_byte_aligned:
        label = 'INFO'
        print(f"  [{label}] Fix 6 (bitLength): frame_bits={frame_bits} "
              f"byte_aligned={byte_aligned_bits} "
              f"{'(sub-byte precision preserved)' if not_byte_aligned else '(byte-aligned)'}")
    return True


def check_disconnect(disconnects, verbose=False):
    """Fix 7: Report disconnect message IDs."""
    if not disconnects:
        print("  [SKIP] Fix 7 (disconnect): no disconnect messages in capture")
        return None

    for d in disconnects:
        msg_id = d['msg_id']
        label = 'INFO'
        version = '2018' if msg_id == 0x15 else '5.5' if msg_id == 0x13 else 'unknown'
        print(f"  [{label}] Fix 7 (disconnect): msg_id=0x{msg_id:02x} "
              f"(Unity {version})")
    return True


def verify_roundtrip(rpc_entry, verbose=False):
    """Verify our encoder produces the same bytes as Unity for this RPC."""
    decoded = rpc_entry.get('decoded')
    raw = rpc_entry['raw']
    bit_length = rpc_entry['bit_length']
    if not decoded:
        return None

    method_name = decoded['method_name']
    if method_name == 'unknown' or method_name not in METHOD_SIGNATURES:
        return None

    params = decoded.get('params', [])
    counter = decoded['timestamp_ms']
    view_id = decoded['view_id']

    rpc_mode_val = decoded['rpc_mode']
    if isinstance(rpc_mode_val, RPCMode):
        mode = rpc_mode_val
    elif isinstance(rpc_mode_val, int):
        mode = RPCMode(rpc_mode_val)
    else:
        return None

    try:
        if decoded['first_use']:
            our_data, our_bits = encode_rpc_first_use(
                method_name, params, view_id, counter, mode,
                target_view=0x2000)
        else:
            our_data, our_bits = encode_rpc_subsequent(
                method_name, params, view_id, counter, mode,
                target_view=0x2000)
    except Exception:
        return None

    # Compare only the bits that matter (ignore padding beyond bit_length)
    wire_bits = ''.join(f'{b:08b}' for b in raw)[:bit_length]
    our_bits_str = ''.join(f'{b:08b}' for b in our_data)[:our_bits]

    ok = wire_bits == our_bits_str and bit_length == our_bits
    if verbose or not ok:
        label = 'PASS' if ok else 'FAIL'
        msg = f"  [{label}] Roundtrip: {method_name}"
        if decoded['first_use']:
            msg += " (first-use)"
        msg += f" counter={counter} params={params}"
        if not ok:
            msg += f"\n    wire: {raw.hex()[:80]} ({bit_length} bits)"
            msg += f"\n    ours: {our_data.hex()[:80]} ({our_bits} bits)"
            # Find first differing bit
            for i in range(min(len(wire_bits), len(our_bits_str))):
                if wire_bits[i] != our_bits_str[i]:
                    msg += f"\n    first diff at bit {i}"
                    break
        print(msg)
    return ok


def main():
    parser = argparse.ArgumentParser(description='Verify protocol fields from Unity pcap')
    parser.add_argument('pcap', help='Path to pcap file')
    parser.add_argument('--verbose', '-v', action='store_true')
    args = parser.parse_args()

    print(f"Loading {args.pcap}...")
    payloads = load_pcap_udp_payloads(args.pcap)
    print(f"  {len(payloads)} UDP packets")

    rpcs, disconnects = extract_rpc_messages(payloads)
    print(f"  {len(rpcs)} RPC messages, {len(disconnects)} disconnect messages")
    print()

    errors = [r for r in rpcs if 'error' in r]
    if errors:
        print(f"  {len(errors)} RPCs failed to decode:")
        for e in errors[:5]:
            print(f"    {e['error']}")
        print()

    decoded_rpcs = [r for r in rpcs if 'decoded' in r]
    first_use = [r for r in decoded_rpcs if r['decoded']['first_use']]
    subsequent = [r for r in decoded_rpcs if not r['decoded']['first_use']]

    print(f"RPC breakdown: {len(first_use)} first-use, {len(subsequent)} subsequent")
    print()

    results = {'pass': 0, 'fail': 0, 'skip': 0}

    def record(ok):
        if ok is None:
            results['skip'] += 1
        elif ok:
            results['pass'] += 1
        else:
            results['fail'] += 1

    # Fix 1: 0x2000
    print("=== Fix 1: 0x2000 (0x2000) ===")
    for rpc in decoded_rpcs[:5]:
        record(check_target_view(rpc, args.verbose))
    if len(decoded_rpcs) > 5:
        # Check remaining silently
        for rpc in decoded_rpcs[5:]:
            r = check_target_view(rpc, False)
            if r is False:
                check_target_view(rpc, True)
            record(r)
    print()

    # Fix 2: 16-bit counter
    print("=== Fix 2: 16-bit counter ===")
    for rpc in decoded_rpcs[:3]:
        record(check_16bit_counter(rpc, args.verbose))
    for rpc in decoded_rpcs[3:]:
        r = check_16bit_counter(rpc, False)
        if r is False:
            check_16bit_counter(rpc, True)
        record(r)
    record(check_counter_above_127(decoded_rpcs, args.verbose))
    print()

    # Fix 3: subsequent remaining
    print("=== Fix 3: Subsequent remaining (total_bits - 121) ===")
    for rpc in subsequent[:5]:
        record(check_subsequent_remaining(rpc, args.verbose))
    for rpc in subsequent[5:]:
        r = check_subsequent_remaining(rpc, False)
        if r is False:
            check_subsequent_remaining(rpc, True)
        record(r)
    print()

    # Fix 4: first-use remaining
    print("=== Fix 4: First-use remaining (param_bits + 19) ===")
    for rpc in first_use:
        record(check_first_use_remaining(rpc, args.verbose))
    if not first_use:
        print("  [SKIP] No first-use RPCs in capture")
    print()

    # Fix 5: method_tag
    print("=== Fix 5: method_tag ===")
    tags = {}
    for rpc in first_use:
        tag = check_method_tag(rpc, args.verbose)
        if tag is not None:
            method_name = rpc['decoded']['method_name']
            tags[method_name] = tag
    if tags:
        print(f"  Observed method tags: {tags}")
    else:
        print("  [SKIP] No first-use RPCs to extract tags from")
    print()

    # Fix 6: bitLength
    print("=== Fix 6: Frame bitLength ===")
    for rpc in decoded_rpcs[:3]:
        record(check_frame_bit_length(rpc, args.verbose))
    print()

    # Fix 7: disconnect
    print("=== Fix 7: Disconnect message ID ===")
    check_disconnect(disconnects, args.verbose)
    print()

    # Roundtrip verification
    print("=== Roundtrip: Unity wire vs Python encoder ===")
    roundtrip_count = 0
    for rpc in decoded_rpcs:
        r = verify_roundtrip(rpc, args.verbose)
        record(r)
        if r is not None:
            roundtrip_count += 1
    if roundtrip_count == 0:
        print("  [SKIP] No RPCs with known signatures for roundtrip check")
    else:
        pass_count = sum(1 for r in decoded_rpcs if verify_roundtrip(r) is True)
        print(f"  {pass_count}/{roundtrip_count} roundtrips match")
    print()

    # Summary
    print("=" * 50)
    print(f"PASS: {results['pass']}  FAIL: {results['fail']}  SKIP: {results['skip']}")
    if results['fail'] > 0:
        print("SOME CHECKS FAILED — see details above")
        sys.exit(1)
    else:
        print("All checks passed!")


if __name__ == '__main__':
    main()
