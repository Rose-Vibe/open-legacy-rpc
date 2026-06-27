import struct
import sys

from protocol.unity_protocol import (
    RPCMode, encode_rpc_subsequent, encode_rpc_first_use, decode_rpc,
    encode_state_sync, decode_state_sync, encode_view_id, METHOD_SIGNATURES,
    compute_method_id, method_hash_hex, class_guid_hex,
    compute_method_index, METHOD_INDEX_MAP,
    INTERNAL_RPCS, INTERNAL_RPC_CONSTANT, USER_RPC_CONSTANT,
    lookup_method_by_hash,
    encode_view_id_16, decode_view_id_16,
    encode_instantiate_group_flags, decode_instantiate_group_flags,
    encode_instantiate_params, decode_instantiate_params,
)
from protocol.bitstream import BitStream


def test_view_id_encoding():
    assert encode_view_id(1) == b'\x00\x00\x00\x00\x00\x01'
    assert encode_view_id(0) == b'\x00' * 6


def test_rpc_subsequent_decode_known():
    """Decode a known subsequent-use RPC from wire capture."""
    # From a captured RPC_Int(42) subsequent-use message
    # bit_length varies, but we know the structure
    # Build a subsequent RPC_Int(42) and verify decode round-trips
    payload, bits = encode_rpc_subsequent('RPC_Int', [42], mode=RPCMode.Server)
    result = decode_rpc(payload, bits)
    assert result['method_name'] == 'RPC_Int'
    assert result['rpc_mode'] == RPCMode.Server
    assert result['first_use'] is False
    assert result['params'] == [42]


def test_rpc_subsequent_roundtrip_int():
    for val in [0, 1, -1, 42, 2147483647, -2147483648]:
        payload, bits = encode_rpc_subsequent('RPC_Int', [val], mode=RPCMode.Server)
        result = decode_rpc(payload, bits)
        assert result['params'] == [val], f"Failed for {val}"


def test_rpc_subsequent_roundtrip_float():
    for val in [0.0, 1.0, -1.5, 3.14]:
        payload, bits = encode_rpc_subsequent('RPC_Float', [val], mode=RPCMode.Server)
        result = decode_rpc(payload, bits)
        assert abs(result['params'][0] - val) < 1e-5, f"Failed for {val}"


def test_rpc_subsequent_roundtrip_vector3():
    v = (1.0, 2.0, 3.0)
    payload, bits = encode_rpc_subsequent('RPC_Vector3', [v], mode=RPCMode.All)
    result = decode_rpc(payload, bits)
    assert result['rpc_mode'] == RPCMode.All
    rv = result['params'][0]
    for i in range(3):
        assert abs(rv[i] - v[i]) < 1e-5


def test_rpc_subsequent_roundtrip_quaternion():
    q = (0.5, 0.183, 0.5, 0.683)
    payload, bits = encode_rpc_subsequent('RPC_Quaternion', [q], mode=RPCMode.Others)
    result = decode_rpc(payload, bits)
    assert result['rpc_mode'] == RPCMode.Others
    rq = result['params'][0]
    for i in range(4):
        assert abs(rq[i] - q[i]) < 1e-3


def test_rpc_subsequent_roundtrip_string():
    for s in ['hello', '', 'Hello World!', 'x' * 100]:
        payload, bits = encode_rpc_subsequent('RPC_String', [s], mode=RPCMode.Server)
        result = decode_rpc(payload, bits)
        assert result['params'][0] == s, f"Failed for {s!r}"


def test_rpc_subsequent_roundtrip_bytes():
    for data in [b'', b'\x00\x01\x02', b'\xff' * 50]:
        payload, bits = encode_rpc_subsequent('RPC_Bytes', [data], mode=RPCMode.Server)
        result = decode_rpc(payload, bits)
        assert result['params'][0] == data


def test_rpc_subsequent_roundtrip_multi_param():
    payload, bits = encode_rpc_subsequent(
        'RPC_IntFloatString', [42, 3.14, 'hello'], mode=RPCMode.All)
    result = decode_rpc(payload, bits)
    assert result['params'][0] == 42
    assert abs(result['params'][1] - 3.14) < 1e-5
    assert result['params'][2] == 'hello'


def test_rpc_first_use_roundtrip_int():
    payload, bits = encode_rpc_first_use('RPC_Int', [99], mode=RPCMode.Server)
    result = decode_rpc(payload, bits)
    assert result['first_use'] is True
    assert result['method_name'] == 'RPC_Int'
    assert result['method_hash'] == 'd456'
    assert result['rpc_mode'] == RPCMode.Server
    assert result['params'] == [99]


def test_rpc_first_use_roundtrip_string():
    payload, bits = encode_rpc_first_use('RPC_String', ['test'], mode=RPCMode.All)
    result = decode_rpc(payload, bits)
    assert result['first_use'] is True
    assert result['method_name'] == 'RPC_String'
    assert result['params'][0] == 'test'


def test_rpc_first_use_roundtrip_multi_param():
    payload, bits = encode_rpc_first_use(
        'RPC_IntFloatString', [10, -2.5, 'abc'], mode=RPCMode.OthersBuffered)
    result = decode_rpc(payload, bits)
    assert result['first_use'] is True
    assert result['method_name'] == 'RPC_IntFloatString'
    assert result['rpc_mode'] == RPCMode.OthersBuffered
    assert result['params'][0] == 10
    assert abs(result['params'][1] - (-2.5)) < 1e-5
    assert result['params'][2] == 'abc'


def test_rpc_modes():
    for mode in [RPCMode.Server, RPCMode.Others, RPCMode.All,
                 RPCMode.OthersBuffered, RPCMode.AllBuffered]:
        payload, bits = encode_rpc_subsequent('RPC_Int', [1], mode=mode)
        result = decode_rpc(payload, bits)
        assert result['rpc_mode'] == mode, f"Failed for {mode}"


def test_first_use_metadata_remaining_count():
    """First-use metadata contains correct remaining_bit_count."""
    payload, bits = encode_rpc_first_use('RPC_Int', [42], view_id=0, rpc_counter=0)
    all_bits = ''.join(f'{b:08b}' for b in payload)

    # Method hash for RPC_Int is 'd456' (2 bytes), method_id_bits = (6+2)*8 = 64
    # meta_start = 160 + (64-48) = 176
    meta_start = 176
    meta_bits = all_bits[meta_start:meta_start+52]

    # method_tag (bits 0-3): we write 0
    assert meta_bits[0:4] == '0000'
    # zeros (bits 4-19)
    assert meta_bits[4:20] == '0' * 16
    # remaining_bit_count (bits 20-35): param_bits(32) + 19 = 51
    remaining = int(meta_bits[20:36], 2)
    assert remaining == 51
    # constant 0x0002 (bits 36-51)
    const = int(meta_bits[36:52], 2)
    assert const == 0x0002


def test_first_use_metadata_with_variable_params():
    """Remaining count adjusts for variable-length params."""
    # Short string
    payload1, bits1 = encode_rpc_first_use('RPC_String', ['hi'])
    # Longer string
    payload2, bits2 = encode_rpc_first_use('RPC_String', ['hello world'])
    assert bits1 != bits2  # different param sizes

    # Both should round-trip correctly
    result1 = decode_rpc(payload1, bits1)
    result2 = decode_rpc(payload2, bits2)
    assert result1['params'] == ['hi']
    assert result2['params'] == ['hello world']


def test_state_sync_encode_decode_basic():
    data_bs = BitStream()
    data_bs.write_i32_be(42)

    payload, bits = encode_state_sync(1, 0x0695, data_bs, is_first=False)
    result = decode_state_sync(payload, bits)

    assert result['msg_id'] == 0x1b
    assert result['view_id'] == 1
    assert result['timestamp'] == 0x0695
    assert result['is_first'] is False
    assert result['data_bit_length'] == 32

    ds = result['data_stream']
    assert ds.read_i32_be() == 42


def test_state_sync_encode_matches_capture():
    """Encode state sync with correct header layout."""
    data_bs = BitStream()
    data_bs.write_i32_be(42)

    payload, bits = encode_state_sync(1, 0x09b7, data_bs, is_first=False,
                                       view_id_scope='scene')
    # Header: 1b 000000000000 09b7 7f [view_id_16]
    assert payload[0] == 0x1b
    assert payload[1:7] == b'\x00\x00\x00\x00\x00\x00'  # reserved
    assert payload[7:9] == bytes.fromhex('09b7')
    assert payload[9] == 0x7f
    assert payload[10:12] == encode_view_id_16('scene', 1).to_bytes(2, 'big')
    assert payload[12:16] == bytes.fromhex('0000002a')


def test_state_sync_multi_type_roundtrip():
    """Round-trip encode/decode of multi-type state sync."""
    data_bs = BitStream()
    data_bs.write_i32_be(42)
    data_bs.write_float_be(3.14)
    data_bs.write_vector3(1.0, 2.0, 3.0)
    data_bs.write_quaternion(0.5, 0.183, 0.5, 0.683)
    data_bs.write_bool(True)
    data_bs.write_i16_be(1234)
    data_bs.write_char('X')

    payload, bits = encode_state_sync(1, 0x1000, data_bs)
    result = decode_state_sync(payload, bits)

    ds = result['data_stream']
    assert ds.read_i32_be() == 42
    assert abs(ds.read_float_be() - 3.14) < 1e-5
    v = ds.read_vector3()
    assert v == (1.0, 2.0, 3.0)
    q = ds.read_quaternion()
    assert abs(q[0] - 0.5) < 1e-3
    assert ds.read_bool() is True
    assert ds.read_i16_be() == 1234
    assert ds.read_char() == 'X'


KNOWN_HASHES = {
    'RPC_Int': 'd456',
    'RPC_Float': '564a1a',
    'RPC_String': 'ab2f2853',
    'RPC_Vector3': '55e145c655e0',
    'RPC_Quaternion': '55dadac64920',
    'RPC_Bytes': 'a857636a',
    'RPC_IntFloatString': 'd456ac9435d5979429',
    'RPC_Alpha': '54929865',
    'RPC_Beta': 'a80b65',
    'RPC_Gamma': '569b4d19',
}

KNOWN_GUID = '0c93b276d5b1'


def test_method_id_reproduces_all_known_hashes():
    """Algorithm must reproduce all 10 observed method hashes exactly."""
    for method, expected_hash in KNOWN_HASHES.items():
        assert method_hash_hex(method) == expected_hash, \
            f"{method}: expected {expected_hash}, got {method_hash_hex(method)}"


def test_class_guid_constant_for_same_prefix():
    """All RPC_ methods share the same class GUID."""
    for method in KNOWN_HASHES:
        assert class_guid_hex(method) == KNOWN_GUID, \
            f"{method}: expected GUID {KNOWN_GUID}, got {class_guid_hex(method)}"


def test_method_id_deterministic():
    """compute_method_id returns the same result on repeated calls."""
    g1, h1 = compute_method_id('RPC_Int')
    g2, h2 = compute_method_id('RPC_Int')
    assert g1 == g2
    assert h1 == h2


def test_method_id_different_names_different_hashes():
    """Different method names produce different hashes."""
    _, h1 = compute_method_id('RPC_Int')
    _, h2 = compute_method_id('RPC_Float')
    assert h1 != h2


def test_first_use_roundtrip_computed_hash():
    """First-use RPC with computed hash round-trips correctly."""
    payload, bits = encode_rpc_first_use('RPC_Alpha', [77])
    result = decode_rpc(payload, bits)
    assert result['first_use'] is True
    assert result['method_name'] == 'RPC_Alpha'
    assert result['method_hash'] == '54929865'
    assert result['params'] == [77]


KNOWN_INDICES = {
    'RPC_Int': 0x54,
    'RPC_Float': 0x58,
    'RPC_String': 0x5c,
    'RPC_Vector3': 0x60,
    'RPC_Quaternion': 0x64,
    'RPC_Bytes': 0x68,
    'RPC_IntFloatString': 0x6c,
}


def test_method_index_matches_observed():
    """Computed method indices match all 7 observed values from captures."""
    for method, expected_idx in KNOWN_INDICES.items():
        assert METHOD_INDEX_MAP[method] == expected_idx, \
            f"{method}: expected 0x{expected_idx:02x}, got 0x{METHOD_INDEX_MAP[method]:02x}"


def test_compute_method_index_formula():
    """method_index = (RID - 1 - interface_method_count) * 4."""
    assert compute_method_index(29, 7) == 0x54
    assert compute_method_index(30, 7) == 0x58
    assert compute_method_index(35, 7) == 0x6c
    assert compute_method_index(1, 0) == 0x00


def test_first_use_arbitrary_method_name():
    """First-use encoding works for any method name, not just known ones."""
    METHOD_SIGNATURES['MyCustomRPC'] = ['int']
    try:
        payload, bits = encode_rpc_first_use('MyCustomRPC', [42],
                                             mode=RPCMode.Server)
        result = decode_rpc(payload, bits)
        assert result['first_use'] is True
        assert result['method_name'] == 'MyCustomRPC'
        assert result['params'] == [42]
    finally:
        del METHOD_SIGNATURES['MyCustomRPC']


def test_internal_rpc_network_instantiate_hash():
    """__RPCNetworkInstantiate produces the observed GUID and hash."""
    guid, hash_val = compute_method_id('__RPCNetworkInstantiate')
    assert guid.hex() == '2ad8d5b1324e', f"GUID mismatch: {guid.hex()}"
    assert hash_val.hex() == 'c9da62174c65fea2ddb15a3585', \
        f"Hash mismatch: {hash_val.hex()}"


def test_internal_rpc_different_guid():
    """Internal RPCs with '__RPC' prefix get different GUID from 'RPC_' user RPCs."""
    internal_guid = class_guid_hex('__RPCNetworkInstantiate')
    user_guid = class_guid_hex('RPC_Int')
    assert internal_guid != user_guid
    assert internal_guid == '2ad8d5b1324e'
    assert user_guid == '0c93b276d5b1'


def test_internal_rpc_constant_zero():
    """First-use encoding of internal RPCs uses constant=0x0000."""
    METHOD_SIGNATURES['__RPCNetworkInstantiate'] = ['int']
    try:
        payload, bits = encode_rpc_first_use('__RPCNetworkInstantiate', [0])
        all_bits = ''.join(f'{b:08b}' for b in payload)
        # Find the constant field: it's 36 bits into the metadata block
        # metadata starts after method hash
        guid, hash_val = compute_method_id('__RPCNetworkInstantiate')
        method_id_bits = (len(guid) + len(hash_val)) * 8
        hash_extra_bits = method_id_bits - 48
        meta_start = 160 + hash_extra_bits
        const_start = meta_start + 36
        const_bits = all_bits[const_start:const_start + 16]
        assert int(const_bits, 2) == INTERNAL_RPC_CONSTANT, \
            f"Expected 0x{INTERNAL_RPC_CONSTANT:04x}, got 0x{int(const_bits, 2):04x}"
    finally:
        del METHOD_SIGNATURES['__RPCNetworkInstantiate']


def test_user_rpc_constant_two():
    """First-use encoding of user RPCs uses constant=0x0002."""
    payload, bits = encode_rpc_first_use('RPC_Int', [42])
    all_bits = ''.join(f'{b:08b}' for b in payload)
    meta_start = 176  # known for RPC_Int
    const_start = meta_start + 36
    const_bits = all_bits[const_start:const_start + 16]
    assert int(const_bits, 2) == USER_RPC_CONSTANT


def test_rpc_network_view_id_hash():
    """RPC_NetworkViewID produces the observed hash."""
    _, hash_val = compute_method_id('RPC_NetworkViewID')
    assert hash_val.hex() == '310ba632fd579053a8ce'


def test_rpc_network_view_id_index():
    """RPC_NetworkViewID has the expected method index."""
    assert METHOD_INDEX_MAP['RPC_NetworkViewID'] == 0x74


def test_rpc_network_view_id_roundtrip():
    """NetworkViewID RPC param round-trips as 16-bit value."""
    payload, bits = encode_rpc_subsequent('RPC_NetworkViewID', [0x0004])
    result = decode_rpc(payload, bits)
    assert result['params'] == [0x0004]


def test_rpc_network_player_roundtrip():
    """NetworkPlayer RPC param round-trips as int32."""
    payload, bits = encode_rpc_subsequent('RPC_NetworkPlayer', [1])
    result = decode_rpc(payload, bits)
    assert result['params'] == [1]


def test_view_id_16_encode_scene():
    """SceneID encoding: N << 2."""
    assert encode_view_id_16('scene', 1) == 0x0004
    assert encode_view_id_16('scene', 0) == 0x0000
    assert encode_view_id_16('scene', 2) == 0x0008


def test_view_id_16_encode_allocated():
    """AllocatedID encoding: 0x4000 | (N << 6)."""
    assert encode_view_id_16('allocated', 1) == 0x4040
    assert encode_view_id_16('allocated', 2) == 0x4080
    assert encode_view_id_16('allocated', 3) == 0x40c0
    assert encode_view_id_16('allocated', 50) == 0x4c80


def test_view_id_16_decode_all_captures():
    """Decode all 5 captured NetworkViewID values."""
    assert decode_view_id_16(0x0004) == ('scene', 1)
    assert decode_view_id_16(0x4040) == ('allocated', 1)
    assert decode_view_id_16(0x4080) == ('allocated', 2)
    assert decode_view_id_16(0x40c0) == ('allocated', 3)
    assert decode_view_id_16(0x4c80) == ('allocated', 50)


def test_view_id_16_roundtrip():
    """Encode then decode recovers the original values."""
    for scope, id_val in [('scene', 0), ('scene', 1), ('scene', 100),
                           ('allocated', 1), ('allocated', 50), ('allocated', 255)]:
        encoded = encode_view_id_16(scope, id_val)
        decoded = decode_view_id_16(encoded)
        assert decoded == (scope, id_val), f"Failed for ({scope}, {id_val})"


def test_network_player_hash():
    """RPC_NetworkPlayer produces the observed hash."""
    _, hash_val = compute_method_id('RPC_NetworkPlayer')
    assert hash_val.hex() == '310ba632fe7649ab19'


def test_network_player_is_int32():
    """NetworkPlayer wire values match int32 BE for player indices 0 and 1."""
    for player_idx in [0, 1]:
        payload, bits = encode_rpc_subsequent('RPC_NetworkPlayer', [player_idx])
        result = decode_rpc(payload, bits)
        assert result['params'] == [player_idx]


def test_internal_rpc_lookup():
    """Internal RPC method names are registered and can be looked up."""
    _, hash_val = compute_method_id('__RPCNetworkInstantiate')
    name = lookup_method_by_hash(hash_val.hex())
    assert name == '__RPCNetworkInstantiate'


def test_password_in_connection_request():
    """Password is plaintext ASCII appended to 0x04 connection request."""
    # Simulate constructing a connection request with password
    offline_magic = bytes.fromhex('00ffff00fefefefefdfdfdfd12345678')
    client_guid = b'\x00' * 8
    password = b'secret123'
    msg = bytes([0x04]) + offline_magic + client_guid + password
    # Verify the password is at bytes 25+
    assert msg[25:] == password
    assert msg[25:].decode('ascii') == 'secret123'


def test_instantiate_group_flags_encode():
    """Group/flags field encodes group in bits 5-3 with bit 2 set."""
    assert encode_instantiate_group_flags(0) == 0x0004
    assert encode_instantiate_group_flags(5) == 0x002c
    assert encode_instantiate_group_flags(7) == 0x003c


def test_instantiate_group_flags_decode():
    """Decode group/flags from observed wire values."""
    assert decode_instantiate_group_flags(0x0004) == (0, 0)
    assert decode_instantiate_group_flags(0x002c) == (5, 0)


def test_instantiate_params_roundtrip():
    """Encode then decode instantiate params preserves all fields."""
    prefab_bits = '1' * 65 + '0' * 68  # 133 bits
    pos = (1.0, 2.0, 3.0)
    rot = (0.0, 0.0, 0.0, 1.0)

    param_bs = encode_instantiate_params(
        group=5, prefab_id_bits=prefab_bits,
        position=pos, rotation=rot,
        view_id_scope='allocated', view_id_value=3,
    )

    param_bs.pos = 0
    result = decode_instantiate_params(param_bs, param_bs.bit_length)

    assert result['group'] == 5
    assert result['level_prefix'] == 0
    assert result['prefab_id_bits'] == prefab_bits
    assert abs(result['position'][0] - 1.0) < 1e-5
    assert abs(result['position'][1] - 2.0) < 1e-5
    assert abs(result['position'][2] - 3.0) < 1e-5
    assert abs(result['rotation'][3] - 1.0) < 1e-5
    assert result['unknown_int32'] == 1
    assert result['view_id'] == ('allocated', 3)


def test_instantiate_group_flags_matches_capture():
    """Wire values from capture match our encoding."""
    assert encode_instantiate_group_flags(0) == 0x0004
    assert encode_instantiate_group_flags(5) == 0x002c
    # 0x002c - 0x0004 = 0x0028 = 40 = 5 * 8
    assert 0x002c - 0x0004 == 5 * 8


def test_invalid_rpc_mode_does_not_crash():
    """Decoding an RPC with an invalid RPCMode value should not crash."""
    data, bits = encode_rpc_subsequent('RPC_Int', [42], view_id=1, rpc_counter=0,
                                       mode=RPCMode.Server)
    # Tamper with the mode nibble at the known bit position (136)
    # For subsequent-use, mode is at bit 136. Set to value 4 (invalid).
    bs = BitStream(data)
    bs.pos = 136
    bs.write_bits(4, 4)
    tampered = bs.to_bytes()
    result = decode_rpc(tampered, bits)
    assert result['rpc_mode'] == 4  # raw int, not RPCMode enum


def test_encode_params_zero_values_not_treated_as_missing():
    """Encoding int=0, float=0.0, string='' should produce real values, not defaults."""
    data_int, bits_int = encode_rpc_subsequent('RPC_Int', [0], view_id=1, rpc_counter=0)
    decoded_int = decode_rpc(data_int, bits_int)
    assert decoded_int['params'][0] == 0

    data_float, bits_float = encode_rpc_subsequent('RPC_Float', [0.0], view_id=1, rpc_counter=0)
    decoded_float = decode_rpc(data_float, bits_float)
    assert decoded_float['params'][0] == 0.0

    data_str, bits_str = encode_rpc_subsequent('RPC_String', [''], view_id=1, rpc_counter=0)
    decoded_str = decode_rpc(data_str, bits_str)
    assert decoded_str['params'][0] == ''

    data_bytes, bits_bytes = encode_rpc_subsequent('RPC_Bytes', [b''], view_id=1, rpc_counter=0)
    decoded_bytes = decode_rpc(data_bytes, bits_bytes)
    assert decoded_bytes['params'][0] == b''


def test_rpc_counter_overflow_wraps_at_128():
    """RPC counter wraps at 128 (single byte, *2)."""
    for counter in range(501):
        data, bits = encode_rpc_subsequent('RPC_Int', [42], view_id=1, rpc_counter=counter)
        decoded = decode_rpc(data, bits)
        assert decoded['rpc_counter'] == counter % 128, \
            f"counter={counter}: expected {counter % 128}, got {decoded['rpc_counter']}"


def test_rpc_counter_overflow_first_use():
    """First-use encoding also wraps counter at 128."""
    for counter in [0, 127, 128, 200, 255, 500]:
        data, bits = encode_rpc_first_use('RPC_Int', [42], view_id=1, rpc_counter=counter)
        decoded = decode_rpc(data, bits)
        assert decoded['rpc_counter'] == counter % 128, \
            f"counter={counter}: expected {counter % 128}, got {decoded['rpc_counter']}"


def test_float_denorm_roundtrip():
    """Denormalized float round-trips through BitStream."""
    denorm = 1.401298464324817e-45  # smallest positive float32 subnormal
    bs = BitStream()
    bs.write_float_be(denorm)
    bs.pos = 0
    val = bs.read_float_be()
    assert struct.pack('>f', val) == struct.pack('>f', denorm)


def test_float_edge_cross_language_bytes():
    """Float edge values produce known IEEE 754 bytes (cross-language reference)."""
    cases = [
        (float('nan'), '7fc00000'),
        (float('inf'), '7f800000'),
        (float('-inf'), 'ff800000'),
        (-0.0, '80000000'),
        (1.401298464324817e-45, '00000001'),  # smallest subnormal
    ]
    for val, expected_hex in cases:
        bs = BitStream()
        bs.write_float_be(val)
        actual = bs.to_bytes().hex()
        assert actual == expected_hex, \
            f"value={val}: expected {expected_hex}, got {actual}"


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
