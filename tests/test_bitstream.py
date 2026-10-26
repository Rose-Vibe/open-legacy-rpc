import struct
import sys

from protocol.bitstream import BitStream


def test_read_write_bits():
    bs = BitStream()
    bs.write_bits(0b10110, 5)
    bs.write_bits(0b001, 3)
    assert bs.to_bytes() == bytes([0b10110001])
    bs.pos = 0
    assert bs.read_bits(5) == 0b10110
    assert bs.read_bits(3) == 0b001


def test_read_write_bool():
    bs = BitStream()
    bs.write_bool(True)
    bs.write_bool(False)
    bs.write_bool(True)
    bs.pos = 0
    assert bs.read_bool() is True
    assert bs.read_bool() is False
    assert bs.read_bool() is True


def test_read_write_u8():
    bs = BitStream()
    bs.write_u8(0xAB)
    bs.pos = 0
    assert bs.read_u8() == 0xAB


def test_read_write_u16_be():
    bs = BitStream()
    bs.write_u16_be(0x1234)
    assert bs.to_bytes() == bytes([0x12, 0x34])
    bs.pos = 0
    assert bs.read_u16_be() == 0x1234


def test_read_write_i16_be():
    bs = BitStream()
    bs.write_i16_be(-1)
    bs.write_i16_be(1234)
    bs.pos = 0
    assert bs.read_i16_be() == -1
    assert bs.read_i16_be() == 1234


def test_read_write_u32_be():
    bs = BitStream()
    bs.write_u32_be(0xDEADBEEF)
    assert bs.to_bytes() == bytes([0xDE, 0xAD, 0xBE, 0xEF])
    bs.pos = 0
    assert bs.read_u32_be() == 0xDEADBEEF


def test_read_write_i32_be():
    for val in [0, 1, -1, 42, -42, 2147483647, -2147483648]:
        bs = BitStream()
        bs.write_i32_be(val)
        bs.pos = 0
        assert bs.read_i32_be() == val, f"Failed for {val}"


def test_read_write_float_be():
    for val in [0.0, 1.0, -1.5, 3.14]:
        bs = BitStream()
        bs.write_float_be(val)
        bs.pos = 0
        result = bs.read_float_be()
        assert abs(result - val) < 1e-6, f"Failed for {val}: got {result}"


def test_read_write_char():
    bs = BitStream()
    bs.write_char('X')
    bs.write_char('Z')
    bs.pos = 0
    assert bs.read_char() == 'X'
    assert bs.read_char() == 'Z'


def test_read_write_bytes():
    data = b'\x01\x02\x03\x04\x05'
    bs = BitStream()
    bs.write_bytes(data)
    bs.pos = 0
    assert bs.read_bytes(5) == data


def test_read_write_vector3():
    bs = BitStream()
    bs.write_vector3(1.0, 2.0, 3.0)
    bs.pos = 0
    v = bs.read_vector3()
    assert abs(v[0] - 1.0) < 1e-6
    assert abs(v[1] - 2.0) < 1e-6
    assert abs(v[2] - 3.0) < 1e-6


def test_read_write_quaternion():
    bs = BitStream()
    bs.write_quaternion(0.5, 0.183, 0.5, 0.683)
    bs.pos = 0
    q = bs.read_quaternion()
    assert abs(q[0] - 0.5) < 1e-3
    assert abs(q[1] - 0.183) < 1e-3
    assert abs(q[2] - 0.5) < 1e-3
    assert abs(q[3] - 0.683) < 1e-3


def test_compressed_u32_roundtrip():
    for val in [0, 1, 42, 255, 256, 0x1234, 0x123456, 0x12345678, 0x00000038,
                0x10000, 0x100, 0xFF00, 0xFF0000, 0x01000000, 0x00010000]:
        bs = BitStream()
        bs.write_compressed_u32(val)
        bs.pos = 0
        result = bs.read_compressed_u32()
        assert result == val, f"Failed for {val:#x}: got {result:#x}"


def test_state_sync_decode_known_capture():
    """Decode a known state sync payload from the SerializeTypesExperiment."""
    payload = bytes.fromhex('0000002a4048f5c33f80000040000000404000003effffff3e3b67ae3efffffe3f2ed9eb82692c00')
    bs = BitStream(payload)

    assert bs.read_i32_be() == 42
    assert abs(bs.read_float_be() - 3.14) < 1e-5

    v = bs.read_vector3()
    assert v == (1.0, 2.0, 3.0)

    q = bs.read_quaternion()
    assert abs(q[0] - 0.5) < 1e-5
    assert abs(q[3] - 0.683) < 1e-2

    assert bs.read_bool() is True
    assert bs.read_i16_be() == 1234
    assert bs.read_char() == 'X'


def test_state_sync_encode_matches_capture():
    """Encode state sync data and verify it matches the captured wire bytes."""
    bs = BitStream()
    bs.write_i32_be(42)
    bs.write_float_be(3.140000104904175)  # exact float32 representation
    bs.write_vector3(1.0, 2.0, 3.0)
    # Quaternion values from Euler(30,60,90) - use exact float32 values
    bs.write_quaternion(
        struct.unpack('>f', bytes.fromhex('3effffff'))[0],
        struct.unpack('>f', bytes.fromhex('3e3b67ae'))[0],
        struct.unpack('>f', bytes.fromhex('3efffffe'))[0],
        struct.unpack('>f', bytes.fromhex('3f2ed9eb'))[0],
    )
    bs.write_bool(True)
    bs.write_i16_be(1234)
    bs.write_char('X')

    expected = bytes.fromhex('0000002a4048f5c33f80000040000000404000003effffff3e3b67ae3efffffe3f2ed9eb82692c00')
    result = bs.to_bytes()
    assert result == expected, f"Mismatch:\n  got:    {result.hex()}\n  expect: {expected.hex()}"


def test_state_sync_phase1_decode():
    """Decode phase 1 values (int=99, float=-1.5, vec=(10,20,30), quat=identity, bool=false, short=-1, char='Z')."""
    payload = bytes.fromhex('00000063bfc000004120000041a0000041f000000000000000000000000000003f8000007fffad00')
    bs = BitStream(payload)

    assert bs.read_i32_be() == 99
    assert abs(bs.read_float_be() - (-1.5)) < 1e-5

    v = bs.read_vector3()
    assert abs(v[0] - 10.0) < 1e-5
    assert abs(v[1] - 20.0) < 1e-5
    assert abs(v[2] - 30.0) < 1e-5

    q = bs.read_quaternion()
    assert abs(q[0]) < 1e-5  # identity = (0,0,0,1)
    assert abs(q[1]) < 1e-5
    assert abs(q[2]) < 1e-5
    assert abs(q[3] - 1.0) < 1e-5

    assert bs.read_bool() is False
    assert bs.read_i16_be() == -1
    assert bs.read_char() == 'Z'


def test_bit_packing_across_byte_boundary():
    """Verify bool(1 bit) + short(16 bits) pack correctly across bytes."""
    bs = BitStream()
    bs.write_bool(True)
    bs.write_i16_be(1234)
    bs.write_char('X')

    bs.pos = 0
    assert bs.read_bool() is True
    assert bs.read_i16_be() == 1234
    assert bs.read_char() == 'X'


def test_remaining():
    bs = BitStream(b'\x00\x00', bit_length=12)
    assert bs.remaining == 12
    bs.read_bits(5)
    assert bs.remaining == 7


def test_read_past_end_raises():
    """Reading past bit_length raises BitStreamError."""
    from protocol.bitstream import BitStreamError
    bs = BitStream(b'\xff', bit_length=4)
    bs.read_bits(4)
    try:
        bs.read_bit()
        assert False, "should have raised BitStreamError"
    except BitStreamError:
        pass


def test_read_past_end_empty():
    """Reading from empty stream raises BitStreamError."""
    from protocol.bitstream import BitStreamError
    bs = BitStream(b'', bit_length=0)
    try:
        bs.read_bit()
        assert False, "should have raised BitStreamError"
    except BitStreamError:
        pass


def test_float_nan_roundtrip():
    """NaN round-trips through BitStream."""
    import math
    bs = BitStream()
    bs.write_float_be(float('nan'))
    bs.pos = 0
    assert math.isnan(bs.read_float_be())


def test_float_infinity_roundtrip():
    """Infinity round-trips through BitStream."""
    bs = BitStream()
    bs.write_float_be(float('inf'))
    bs.write_float_be(float('-inf'))
    bs.pos = 0
    assert bs.read_float_be() == float('inf')
    assert bs.read_float_be() == float('-inf')


def test_float_negative_zero_roundtrip():
    """-0.0 round-trips through BitStream."""
    bs = BitStream()
    bs.write_float_be(-0.0)
    bs.pos = 0
    val = bs.read_float_be()
    assert val == 0.0
    assert struct.pack('>f', val) == struct.pack('>f', -0.0)


def test_float_denorm_roundtrip():
    """Smallest positive float32 subnormal round-trips."""
    denorm = 1.401298464324817e-45
    bs = BitStream()
    bs.write_float_be(denorm)
    bs.pos = 0
    val = bs.read_float_be()
    assert struct.pack('>f', val) == struct.pack('>f', denorm)


def test_i32_boundary_values():
    """INT32_MIN and INT32_MAX round-trip correctly."""
    bs = BitStream()
    bs.write_i32_be(-2147483648)
    bs.write_i32_be(2147483647)
    bs.pos = 0
    assert bs.read_i32_be() == -2147483648
    assert bs.read_i32_be() == 2147483647


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
