"""Tests for decode safety caps (fixes 1-8 + decodeBatchIndex)."""
import logging
import struct

import pytest

from protocol.bitstream import BitStream
from protocol.master_serialization import (
    ID_DATABASE_QUERY_REPLY,
    decode_query_reply,
)
from protocol.raknet_transport import (
    EncapsulatedMessage,
    RakNetPeer,
    Reliability,
    SplitPacketAssembler,
    unpack_encapsulated,
)
from protocol.unity_protocol import (
    MSG_ID_BATCH_INDEX,
    decode_batch_index,
    decode_rpc,
)


class TestMasterSerializationCaps:
    """Fixes 1-4: master server decode caps."""

    def test_num_columns_cap(self):
        bs = BitStream()
        bs.write_u8(ID_DATABASE_QUERY_REPLY)
        bs.write_u32_be(1001)
        with pytest.raises(ValueError, match="numColumns exceeds cap"):
            decode_query_reply(bs.to_bytes())

    def test_num_rows_cap(self):
        bs = BitStream()
        bs.write_u8(ID_DATABASE_QUERY_REPLY)
        bs.write_u32_be(0)  # 0 columns
        bs.write_u32_be(100_001)
        with pytest.raises(ValueError, match="numRows exceeds cap"):
            decode_query_reply(bs.to_bytes())

    def test_num_entries_exceeds_columns(self):
        bs = BitStream()
        bs.write_u8(ID_DATABASE_QUERY_REPLY)
        bs.write_u32_be(1)  # 1 column
        bs.write_compressed_u32(0)  # empty name
        bs.write_u8(0)  # NUMERIC
        bs.write_u32_be(1)  # 1 row
        bs.write_u32_be(0)  # row key
        bs.write_u32_be(2)  # numEntries > numColumns
        with pytest.raises(ValueError, match="numEntries exceeds numColumns"):
            decode_query_reply(bs.to_bytes())

    def test_binary_cell_length_cap(self):
        bs = BitStream()
        bs.write_u8(ID_DATABASE_QUERY_REPLY)
        bs.write_u32_be(1)
        bs.write_compressed_u32(0)
        bs.write_u8(2)  # BINARY
        bs.write_u32_be(1)
        bs.write_u32_be(0)
        bs.write_u32_be(1)
        bs.write_u32_be(0)  # cellIdx
        bs.write_bool(False)  # not empty
        bs.write_u32_be(16 * 1024 * 1024 + 1)
        with pytest.raises(ValueError, match="BINARY cell length exceeds cap"):
            decode_query_reply(bs.to_bytes())

    def test_huffman_bitlength_clamp(self, caplog):
        bs = BitStream()
        bs.write_u8(ID_DATABASE_QUERY_REPLY)
        bs.write_u32_be(1)
        bs.write_compressed_u32(9999)  # claim 9999 bits
        bs.write_u8(0)
        with caplog.at_level(logging.WARNING):
            try:
                decode_query_reply(bs.to_bytes())
            except Exception:
                pass
        assert any("Huffman bitLength exceeds remaining" in r.message for r in caplog.records)


class TestRakNetTransportCaps:
    """Fixes 5-7: RakNet transport caps."""

    def test_split_count_cap(self, caplog):
        assembler = SplitPacketAssembler()
        msg = EncapsulatedMessage(b'\x42', Reliability.RELIABLE)
        msg.split_packet_count = 200
        msg.split_packet_id = 1
        msg.split_packet_index = 0
        with caplog.at_level(logging.WARNING):
            result = assembler.add(msg)
        assert result is None
        assert any("splitPacketCount exceeds cap" in r.message for r in caplog.records)

    def test_split_index_ge_count(self, caplog):
        assembler = SplitPacketAssembler()
        msg = EncapsulatedMessage(b'\x42', Reliability.RELIABLE)
        msg.split_packet_count = 5
        msg.split_packet_id = 1
        msg.split_packet_index = 5
        with caplog.at_level(logging.WARNING):
            result = assembler.add(msg)
        assert result is None
        assert any("splitPacketIndex >= splitPacketCount" in r.message for r in caplog.records)

    def test_frame_bitlength_clamp(self, caplog):
        # Build raw frame data: unreliable, claims 128 bits but only has 4 bytes
        frame_data = bytearray()
        frame_data.append(0x00)  # reliability=0, no split
        frame_data += struct.pack('>H', 128)  # claim 128 bits = 16 bytes
        frame_data += b'\x01\x02\x03\x04'  # only 4 bytes

        with caplog.at_level(logging.WARNING):
            messages = unpack_encapsulated(bytes(frame_data))
        assert len(messages) == 1
        assert messages[0].bit_length == 32  # clamped to 4*8
        assert any("frame bitLength exceeds payload" in r.message for r in caplog.records)

    def test_ack_range_cap(self, caplog):
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(('127.0.0.1', 0))
        peer = RakNetPeer(sock, ('127.0.0.1', 9999))
        # Add something to unacked
        peer._unacked_reliable[0] = (EncapsulatedMessage(b'\x01'), 0)

        # Simulate receiving ACK with huge range
        with caplog.at_level(logging.WARNING):
            peer._handle_ack([(0, 20000)])
        # The seq 0 should NOT be removed because range was skipped
        assert 0 in peer._unacked_reliable
        assert any("ACK range span exceeds cap" in r.message for r in caplog.records)
        sock.close()


class TestUnityProtocolCaps:
    """Fix 4 (string param), Fix 8 (min bitLength), decodeBatchIndex."""

    def test_decode_rpc_min_bitlength(self):
        payload = bytes([0x1b, 0x00, 0x00, 0x00])
        with pytest.raises(ValueError, match="bitLength too short"):
            decode_rpc(payload, 32)

    def test_batch_index_hash_bytes_cap(self, caplog):
        bs = BitStream()
        bs.write_u8(MSG_ID_BATCH_INDEX)
        bs.write_u32_be(300)  # halfBits=300 => hashBytes=69 > 64
        payload = bytearray(100)
        prefix = bs.to_bytes()
        payload[:len(prefix)] = prefix

        with caplog.at_level(logging.WARNING):
            result = decode_batch_index(bytes(payload))
        assert result is None
        assert any("batchIndex hashBytes exceeds cap" in r.message for r in caplog.records)
