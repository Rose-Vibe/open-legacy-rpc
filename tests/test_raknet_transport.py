import socket as _sock_mod

from protocol.raknet_transport import (
    EncapsulatedMessage, Reliability, pack_encapsulated, unpack_encapsulated,
    pack_datagram, pack_ack, unpack_datagram, encode_address, decode_address,
    SplitPacketAssembler, encode_u24_le, decode_u24_le, RakNetPeer,
    MAX_FRAGMENT_PAYLOAD,
)


def test_u24_le_roundtrip():
    for val in [0, 1, 255, 256, 0x123456, 0xFFFFFF]:
        encoded = encode_u24_le(val)
        assert len(encoded) == 3
        assert decode_u24_le(encoded) == val


def test_address_roundtrip():
    for ip, port in [('127.0.0.1', 7777), ('10.200.1.2', 8080), ('0.0.0.0', 0)]:
        encoded = encode_address(ip, port)
        assert len(encoded) == 6
        dec_ip, dec_port = decode_address(encoded)
        assert dec_ip == ip
        assert dec_port == port


def test_address_known_capture():
    data = bytes.fromhex('80fffffe1e61')
    ip, port = decode_address(data)
    assert ip == '127.0.0.1'
    assert port == 7777


def test_encapsulated_unreliable_roundtrip():
    msg = EncapsulatedMessage(b'\x1b\x00\x01\x02', Reliability.UNRELIABLE)
    packed = pack_encapsulated(msg)
    msgs = unpack_encapsulated(packed)
    assert len(msgs) == 1
    assert msgs[0].reliability == Reliability.UNRELIABLE
    assert msgs[0].payload == b'\x1b\x00\x01\x02'
    assert msgs[0].bit_length == 32


def test_encapsulated_reliable_ordered_roundtrip():
    msg = EncapsulatedMessage(b'\x1b\xAA\xBB', Reliability.RELIABLE_ORDERED)
    msg.reliable_msg_number = 42
    msg.ordering_index = 7
    msg.ordering_channel = 0
    packed = pack_encapsulated(msg)
    msgs = unpack_encapsulated(packed)
    assert len(msgs) == 1
    m = msgs[0]
    assert m.reliability == Reliability.RELIABLE_ORDERED
    assert m.reliable_msg_number == 42
    assert m.ordering_index == 7
    assert m.ordering_channel == 0
    assert m.payload == b'\x1b\xAA\xBB'


def test_encapsulated_unreliable_sequenced_roundtrip():
    msg = EncapsulatedMessage(b'\x1b\x01\x02\x03', Reliability.UNRELIABLE_SEQUENCED)
    msg.ordering_index = 100
    msg.ordering_channel = 0
    packed = pack_encapsulated(msg)
    msgs = unpack_encapsulated(packed)
    assert len(msgs) == 1
    m = msgs[0]
    assert m.reliability == Reliability.UNRELIABLE_SEQUENCED
    assert m.ordering_index == 100
    assert m.reliable_msg_number is None  # UNRELIABLE has no reliable number


def test_datagram_roundtrip():
    msg1 = EncapsulatedMessage(b'\x1b\x01', Reliability.UNRELIABLE)
    msg2 = EncapsulatedMessage(b'\x83\x00\x00\x00\x01', Reliability.RELIABLE_ORDERED)
    msg2.reliable_msg_number = 0
    msg2.ordering_index = 0
    msg2.ordering_channel = 0
    datagram = pack_datagram(5, [msg1, msg2], timestamp=12345)
    result = unpack_datagram(datagram)
    assert result[0] == 'data'
    _, ts, seq, msgs = result
    assert ts == 12345
    assert seq == 5
    assert len(msgs) == 2
    assert msgs[0].payload == b'\x1b\x01'
    assert msgs[1].payload == b'\x83\x00\x00\x00\x01'


def test_ack_roundtrip():
    ack = pack_ack([(0, 0), (3, 5)], timestamp=100)
    result = unpack_datagram(ack)
    assert result[0] == 'ack'
    _, ts, ranges = result
    assert ts == 100
    assert ranges == [(0, 0), (3, 5)]


def test_split_packet_reassembly():
    assembler = SplitPacketAssembler()

    # 3-part split
    for i in range(3):
        msg = EncapsulatedMessage(bytes([i * 10 + j for j in range(5)]), Reliability.RELIABLE)
        msg.split_packet_count = 3
        msg.split_packet_id = 1
        msg.split_packet_index = i
        msg.reliable_msg_number = i
        result = assembler.add(msg)
        if i < 2:
            assert result is None
        else:
            assert result is not None
            assert len(result.payload) == 15
            assert result.payload == b'\x00\x01\x02\x03\x04\x0a\x0b\x0c\x0d\x0e\x14\x15\x16\x17\x18'


def test_split_packet_out_of_order():
    assembler = SplitPacketAssembler()

    payloads = [b'AAA', b'BBB', b'CCC']
    order = [2, 0, 1]
    for i in order:
        msg = EncapsulatedMessage(payloads[i], Reliability.RELIABLE)
        msg.split_packet_count = 3
        msg.split_packet_id = 2
        msg.split_packet_index = i
        result = assembler.add(msg)
        if i == 1:  # last to arrive
            assert result is not None
            assert result.payload == b'AAABBBCCC'
        else:
            assert result is None


def test_split_assembler_prunes_stale():
    """SplitPacketAssembler evicts entries older than MAX_AGE."""
    import time
    assembler = SplitPacketAssembler()
    # Temporarily set a very low max age
    old_age = SplitPacketAssembler.MAX_AGE
    SplitPacketAssembler.MAX_AGE = 0.0
    try:
        msg = EncapsulatedMessage(b'\x01', Reliability.RELIABLE)
        msg.split_packet_count = 2
        msg.split_packet_id = 0
        msg.split_packet_index = 0
        assembler.add(msg)
        assert len(assembler._pending) == 1

        # Adding another split triggers prune of the stale one
        time.sleep(0.01)
        msg2 = EncapsulatedMessage(b'\x02', Reliability.RELIABLE)
        msg2.split_packet_count = 2
        msg2.split_packet_id = 1
        msg2.split_packet_index = 0
        assembler.add(msg2)
        assert 0 not in assembler._pending
    finally:
        SplitPacketAssembler.MAX_AGE = old_age


def test_split_assembler_limits_pending():
    """SplitPacketAssembler evicts oldest when over MAX_PENDING."""
    assembler = SplitPacketAssembler()
    old_max = SplitPacketAssembler.MAX_PENDING
    SplitPacketAssembler.MAX_PENDING = 5
    try:
        for i in range(10):
            msg = EncapsulatedMessage(b'\x01', Reliability.RELIABLE)
            msg.split_packet_count = 2
            msg.split_packet_id = i
            msg.split_packet_index = 0
            assembler.add(msg)
        assert len(assembler._pending) <= 5
    finally:
        SplitPacketAssembler.MAX_PENDING = old_max


def test_sequence_number_wrapping():
    """RakNetPeer wraps _send_seq at 24 bits."""
    import socket as sock_mod
    from protocol.raknet_transport import RakNetPeer
    s = sock_mod.socket(sock_mod.AF_INET, sock_mod.SOCK_DGRAM)
    s.setblocking(False)
    s.bind(('127.0.0.1', 0))
    peer = RakNetPeer(s, ('127.0.0.1', 9999))
    peer._send_seq = 0xFFFFFE
    # send_message increments _send_seq
    peer.send_message(b'\x01', Reliability.UNRELIABLE)
    assert peer._send_seq == 0xFFFFFF
    peer.send_message(b'\x02', Reliability.UNRELIABLE)
    assert peer._send_seq == 0
    s.close()


def test_parse_known_capture_datagram():
    """Parse a known datagram from the ConnectExperiment capture."""
    # A datagram containing 0x83 (Unity player ready)
    raw = bytes.fromhex('8400000000000178a4040000600028020000010000008300000001')
    result = unpack_datagram(raw)
    assert result[0] == 'data'
    _, ts, seq, msgs = result
    assert len(msgs) == 1
    m = msgs[0]
    assert m.reliability == Reliability.RELIABLE_ORDERED
    assert m.payload[0] == 0x83
    assert m.payload == bytes.fromhex('8300000001')


def _make_peer():
    s = _sock_mod.socket(_sock_mod.AF_INET, _sock_mod.SOCK_DGRAM)
    s.setblocking(False)
    s.bind(('127.0.0.1', 0))
    return RakNetPeer(s, ('127.0.0.1', 9999)), s


def test_send_large_payload_splits_into_fragments():
    """Payloads > MAX_FRAGMENT_PAYLOAD are split; each fragment is one datagram."""
    peer, s = _make_peer()
    big = bytes(range(256)) * 10  # 2560 bytes — more than two fragments
    peer.send_message(big, Reliability.RELIABLE_ORDERED)

    # Three fragments expected: 1200 + 1200 + 160
    assert peer._send_seq == 3

    # Read back the raw datagrams sent to the (loopback) socket
    receiver = _sock_mod.socket(_sock_mod.AF_INET, _sock_mod.SOCK_DGRAM)
    receiver.bind(('127.0.0.1', peer.remote_addr[1]))
    # Re-send via a fresh peer aimed at receiver
    peer2, s2 = _make_peer()
    peer2.remote_addr = ('127.0.0.1', receiver.getsockname()[1])
    peer2.send_message(big, Reliability.RELIABLE_ORDERED)

    frames = []
    for _ in range(3):
        data, _ = receiver.recvfrom(65535)
        result = unpack_datagram(data)
        assert result[0] == 'data'
        frames.append(result[3][0])  # single message per datagram

    assert frames[0].split_packet_count == 3
    assert frames[0].split_packet_index == 0
    assert frames[1].split_packet_index == 1
    assert frames[2].split_packet_index == 2
    assert all(f.split_packet_id == frames[0].split_packet_id for f in frames)

    assert len(frames[0].payload) == MAX_FRAGMENT_PAYLOAD
    assert len(frames[1].payload) == MAX_FRAGMENT_PAYLOAD
    assert len(frames[2].payload) == len(big) - 2 * MAX_FRAGMENT_PAYLOAD

    assert frames[0].reliable_msg_number == 0
    assert frames[1].reliable_msg_number == 1
    assert frames[2].reliable_msg_number == 2

    # All fragments share one ordering index
    assert frames[0].ordering_index == 0
    assert frames[1].ordering_index == 0
    assert frames[2].ordering_index == 0

    receiver.close()
    s.close()
    s2.close()


def test_send_large_payload_reassembles_correctly():
    """Fragments sent by send_message reassemble to the original payload."""
    sender, s_send = _make_peer()
    receiver_sock = _sock_mod.socket(_sock_mod.AF_INET, _sock_mod.SOCK_DGRAM)
    receiver_sock.bind(('127.0.0.1', 0))
    receiver_sock.setblocking(False)
    sender.remote_addr = ('127.0.0.1', receiver_sock.getsockname()[1])

    big = bytes(i & 0xFF for i in range(2500))
    sender.send_message(big, Reliability.RELIABLE_ORDERED)

    receiver_peer, s_recv = _make_peer()
    reassembled = []
    for _ in range(3):
        data, _ = receiver_sock.recvfrom(65535)
        msgs = receiver_peer.handle_received(data)
        reassembled.extend(msgs)

    assert len(reassembled) == 1
    assert reassembled[0].payload == big

    receiver_sock.close()
    s_send.close()
    s_recv.close()


def test_payload_at_threshold_not_split():
    """Payloads exactly at MAX_FRAGMENT_PAYLOAD are sent unfragmented."""
    peer, s = _make_peer()
    exact = bytes(MAX_FRAGMENT_PAYLOAD)
    peer.send_message(exact, Reliability.RELIABLE_ORDERED)
    assert peer._send_seq == 1  # one datagram
    assert peer._unacked_reliable[0][0].split_packet_count is None
    s.close()


def test_split_ordering_index_not_double_incremented():
    """A split message consumes exactly one ordering index."""
    peer, s = _make_peer()
    peer.send_message(bytes(10), Reliability.RELIABLE_ORDERED)      # ordering_index 0
    peer.send_message(bytes(2500), Reliability.RELIABLE_ORDERED)    # ordering_index 1 (split)
    peer.send_message(bytes(10), Reliability.RELIABLE_ORDERED)      # ordering_index 2
    assert peer._ordering_index[0] == 3
    s.close()


def test_ordering_index_separate_for_ordered_vs_sequenced():
    """ORDERED and SEQUENCED use independent index counters on the same channel."""
    peer, s = _make_peer()

    # Send interleaved RELIABLE_ORDERED and UNRELIABLE_SEQUENCED on channel 0
    peer.send_message(b'\x01', Reliability.RELIABLE_ORDERED, ordering_channel=0)
    peer.send_message(b'\x02', Reliability.UNRELIABLE_SEQUENCED, ordering_channel=0)
    peer.send_message(b'\x03', Reliability.RELIABLE_ORDERED, ordering_channel=0)
    peer.send_message(b'\x04', Reliability.UNRELIABLE_SEQUENCED, ordering_channel=0)

    # Ordered counter: 0, 1 (two RELIABLE_ORDERED sends)
    assert peer._ordering_index[0] == 2
    # Sequenced counter: 0, 1 (two UNRELIABLE_SEQUENCED sends)
    assert peer._sequencing_index[0] == 2
    s.close()


if __name__ == '__main__':
    import traceback
    tests = [v for k, v in sorted(globals().items()) if k.startswith('test_')]
    passed = failed = 0
    for t in tests:
        try:
            t()
            passed += 1
            print(f'  PASS  {t.__name__}')
        except Exception as e:
            failed += 1
            print(f'  FAIL  {t.__name__}: {e}')
            traceback.print_exc()
    print(f'\n{passed} passed, {failed} failed')
    sys.exit(1 if failed else 0)
