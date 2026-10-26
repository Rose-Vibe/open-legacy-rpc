"""Tests for exception safety fixes (Python side)."""
import logging
import time

from protocol.raknet_transport import (
    EncapsulatedMessage,
    Reliability,
    SplitPacketAssembler,
)


class TestSplitAssemblerKeyError:
    """Fix 7: SplitPacketAssembler doesn't crash on duplicate-index fragments."""

    def test_duplicate_index_does_not_crash(self, caplog):
        assembler = SplitPacketAssembler()

        # Send two fragments with the same index (0), count=2
        msg1 = EncapsulatedMessage(b'\x01', Reliability.RELIABLE)
        msg1.split_packet_count = 2
        msg1.split_packet_id = 42
        msg1.split_packet_index = 0

        msg2 = EncapsulatedMessage(b'\x02', Reliability.RELIABLE)
        msg2.split_packet_count = 2
        msg2.split_packet_id = 42
        msg2.split_packet_index = 0  # duplicate! overwrites first

        assembler.add(msg1)
        # Now pending has {0: b'\x01'}, count matches would need len==2
        # Send the duplicate — now pending still has {0: b'\x02'}, len==1

        result = assembler.add(msg2)
        # Still waiting for index 1, so should return None (not crash)
        assert result is None

    def test_count_match_with_missing_index_logs_warning(self, caplog):
        assembler = SplitPacketAssembler()

        # Directly set up internal state: count=2 with indices {0, 5}
        # (bypassing the add() safety checks to test the reassembly guard)
        assembler._pending[99] = {0: b'\x01', 5: b'\x03'}
        assembler._counts[99] = 2
        assembler._timestamps[99] = time.monotonic()

        # Now add a valid fragment for same split_id at index 0 — overwrites,
        # but len stays 2 which equals count. The reassembly guard should
        # detect that indices {0, 5} don't cover range(2) = {0, 1}.
        msg = EncapsulatedMessage(b'\x04', Reliability.RELIABLE)
        msg.split_packet_count = 2
        msg.split_packet_id = 99
        msg.split_packet_index = 0

        with caplog.at_level(logging.WARNING):
            result = assembler.add(msg)

        # Guard detects missing index 1
        assert result is None
        assert any("missing indices" in r.message for r in caplog.records)


class TestUnityClientNonePeer:
    """Fix 6: run() doesn't crash when peer is None."""

    def test_run_with_no_peer(self):
        from protocol.unity_client import UnityClient

        client = UnityClient()
        # Not connected — _raknet.peer is None
        # run() should exit immediately because self.connected is False
        client.run(duration=0.1)
        # If we get here without AttributeError, the fix works
