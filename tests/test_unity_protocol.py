import struct
import sys

from protocol.unity_protocol import (
    RPCMode, encode_rpc_subsequent, encode_rpc_first_use, decode_rpc,
    encode_state_sync, decode_state_sync, encode_view_id, METHOD_SIGNATURES,
    compute_method_id, method_hash_hex, class_guid_hex,
    compute_method_index, METHOD_INDEX_MAP, INDEX_TO_METHOD,
    INTERNAL_RPCS, INTERNAL_RPC_CONSTANT,
    lookup_method_by_hash,
    encode_view_id_16, decode_view_id_16,
    encode_instantiate_group_flags, decode_instantiate_group_flags,
    encode_instantiate_params, decode_instantiate_params,
    METHOD_TAG_MAP, register_method_indices,
    register_method_tag, register_method_tags,
    _reset_tag_fallback_warnings,
    encode_batch_index, decode_batch_index, MSG_ID_BATCH_INDEX,
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
    payload, bits = encode_rpc_subsequent('RPC_Int', [42], mode=RPCMode.Server, target_view=0x2000)
    result = decode_rpc(payload, bits)
    assert result['method_name'] == 'RPC_Int'
    assert result['rpc_mode'] == RPCMode.Server
    assert result['first_use'] is False
    assert result['params'] == [42]


def test_rpc_subsequent_roundtrip_int():
    for val in [0, 1, -1, 42, 2147483647, -2147483648]:
        payload, bits = encode_rpc_subsequent('RPC_Int', [val], mode=RPCMode.Server, target_view=0x2000)
        result = decode_rpc(payload, bits)
        assert result['params'] == [val], f"Failed for {val}"


def test_rpc_subsequent_roundtrip_float():
    for val in [0.0, 1.0, -1.5, 3.14]:
        payload, bits = encode_rpc_subsequent('RPC_Float', [val], mode=RPCMode.Server, target_view=0x2000)
        result = decode_rpc(payload, bits)
        assert abs(result['params'][0] - val) < 1e-5, f"Failed for {val}"


def test_rpc_subsequent_roundtrip_vector3():
    v = (1.0, 2.0, 3.0)
    payload, bits = encode_rpc_subsequent('RPC_Vector3', [v], mode=RPCMode.All, target_view=0x2000)
    result = decode_rpc(payload, bits)
    assert result['rpc_mode'] == RPCMode.All
    rv = result['params'][0]
    for i in range(3):
        assert abs(rv[i] - v[i]) < 1e-5


def test_rpc_subsequent_roundtrip_quaternion():
    q = (0.5, 0.183, 0.5, 0.683)
    payload, bits = encode_rpc_subsequent('RPC_Quaternion', [q], mode=RPCMode.Others, target_view=0x2000)
    result = decode_rpc(payload, bits)
    assert result['rpc_mode'] == RPCMode.Others
    rq = result['params'][0]
    for i in range(4):
        assert abs(rq[i] - q[i]) < 1e-3


def test_rpc_subsequent_roundtrip_string():
    for s in ['hello', '', 'Hello World!', 'x' * 100]:
        payload, bits = encode_rpc_subsequent('RPC_String', [s], mode=RPCMode.Server, target_view=0x2000)
        result = decode_rpc(payload, bits)
        assert result['params'][0] == s, f"Failed for {s!r}"


def test_rpc_subsequent_roundtrip_bytes():
    for data in [b'', b'\x00\x01\x02', b'\xff' * 50]:
        payload, bits = encode_rpc_subsequent('RPC_Bytes', [data], mode=RPCMode.Server, target_view=0x2000)
        result = decode_rpc(payload, bits)
        assert result['params'][0] == data


def test_rpc_subsequent_roundtrip_multi_param():
    payload, bits = encode_rpc_subsequent(
        'RPC_IntFloatString', [42, 3.14, 'hello'], mode=RPCMode.All,
        target_view=0x2000)
    result = decode_rpc(payload, bits)
    assert result['params'][0] == 42
    assert abs(result['params'][1] - 3.14) < 1e-5
    assert result['params'][2] == 'hello'


def test_rpc_first_use_roundtrip_int():
    payload, bits = encode_rpc_first_use('RPC_Int', [99], mode=RPCMode.Server, target_view=0x2000)
    result = decode_rpc(payload, bits)
    assert result['first_use'] is True
    assert result['method_name'] == 'RPC_Int'
    assert result['method_hash'] == 'd456'
    assert result['rpc_mode'] == RPCMode.Server
    assert result['params'] == [99]


def test_rpc_first_use_roundtrip_string():
    payload, bits = encode_rpc_first_use('RPC_String', ['test'], mode=RPCMode.All, target_view=0x2000)
    result = decode_rpc(payload, bits)
    assert result['first_use'] is True
    assert result['method_name'] == 'RPC_String'
    assert result['params'][0] == 'test'


def test_rpc_first_use_roundtrip_multi_param():
    payload, bits = encode_rpc_first_use(
        'RPC_IntFloatString', [10, -2.5, 'abc'], mode=RPCMode.OthersBuffered,
        target_view=0x2000)
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
        payload, bits = encode_rpc_subsequent('RPC_Int', [1], mode=mode, target_view=0x2000)
        result = decode_rpc(payload, bits)
        assert result['rpc_mode'] == mode, f"Failed for {mode}"


def test_first_use_metadata_remaining_count():
    """First-use metadata contains correct remaining_bit_count."""
    payload, bits = encode_rpc_first_use('RPC_Int', [42], view_id=0, timestamp_ms=0, target_view=0x2000)
    all_bits = ''.join(f'{b:08b}' for b in payload)

    # Method hash for RPC_Int is 'd456' (2 bytes), method_id_bits = (6+2)*8 = 64
    # meta_start = 160 + (64-48) = 176
    meta_start = 176
    meta_bits = all_bits[meta_start:meta_start+52]

    # method_tag (bits 0-3): RPC_Int's real captured tag is 8 (see
    # docs/research/2026-07-12-method-tag-real-derivation.md — not derived
    # from method_index, which would give the wrong value of 4)
    assert meta_bits[0:4] == '1000'
    # zeros (bits 4-19)
    assert meta_bits[4:20] == '0' * 16
    # remaining_bit_count (bits 20-35): param_bits(32) + 19 = 51
    remaining = int(meta_bits[20:36], 2)
    assert remaining == 51
    # constant 0x2000 (bits 36-51) — default; configurable per-game
    const = int(meta_bits[36:52], 2)
    assert const == 0x2000


def test_first_use_metadata_with_variable_params():
    """Remaining count adjusts for variable-length params."""
    # Short string
    payload1, bits1 = encode_rpc_first_use('RPC_String', ['hi'], target_view=0x2000)
    # Longer string
    payload2, bits2 = encode_rpc_first_use('RPC_String', ['hello world'], target_view=0x2000)
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
    # Header: 1b [u64 timestamp BE] 7f [view_id_16]
    assert payload[0] == 0x1b
    assert payload[1:9] == b'\x00\x00\x00\x00\x00\x00\x09\xb7'  # u64 timestamp
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
    payload, bits = encode_rpc_first_use('RPC_Alpha', [77], target_view=0x2000)
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
                                                 target_view=0x2000,
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
        payload, bits = encode_rpc_first_use('__RPCNetworkInstantiate', [0], target_view=0x2000)
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


def test_target_view_0x2000():
    """First-use encoding of user RPCs uses constant=0x2000."""
    payload, bits = encode_rpc_first_use('RPC_Int', [42], target_view=0x2000)
    all_bits = ''.join(f'{b:08b}' for b in payload)
    meta_start = 176  # known for RPC_Int
    const_start = meta_start + 36
    const_bits = all_bits[const_start:const_start + 16]
    assert int(const_bits, 2) == 0x2000


def test_rpc_network_view_id_hash():
    """RPC_NetworkViewID produces the observed hash."""
    _, hash_val = compute_method_id('RPC_NetworkViewID')
    assert hash_val.hex() == '310ba632fd579053a8ce'


def test_rpc_network_view_id_index():
    """RPC_NetworkViewID has the expected method index."""
    assert METHOD_INDEX_MAP['RPC_NetworkViewID'] == 0x74


def test_rpc_network_view_id_roundtrip():
    """NetworkViewID RPC param round-trips as 16-bit value."""
    payload, bits = encode_rpc_subsequent('RPC_NetworkViewID', [0x0004], target_view=0x2000)
    result = decode_rpc(payload, bits)
    assert result['params'] == [0x0004]


def test_rpc_network_player_roundtrip():
    """NetworkPlayer RPC param round-trips as int32."""
    payload, bits = encode_rpc_subsequent('RPC_NetworkPlayer', [1], target_view=0x2000)
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
        payload, bits = encode_rpc_subsequent('RPC_NetworkPlayer', [player_idx], target_view=0x2000)
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
    data, bits = encode_rpc_subsequent('RPC_Int', [42], view_id=1, timestamp_ms=0,
                                           target_view=0x2000,
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
    data_int, bits_int = encode_rpc_subsequent('RPC_Int', [0], view_id=1, timestamp_ms=0, target_view=0x2000)
    decoded_int = decode_rpc(data_int, bits_int)
    assert decoded_int['params'][0] == 0

    data_float, bits_float = encode_rpc_subsequent('RPC_Float', [0.0], view_id=1, timestamp_ms=0, target_view=0x2000)
    decoded_float = decode_rpc(data_float, bits_float)
    assert decoded_float['params'][0] == 0.0

    data_str, bits_str = encode_rpc_subsequent('RPC_String', [''], view_id=1, timestamp_ms=0, target_view=0x2000)
    decoded_str = decode_rpc(data_str, bits_str)
    assert decoded_str['params'][0] == ''

    data_bytes, bits_bytes = encode_rpc_subsequent('RPC_Bytes', [b''], view_id=1, timestamp_ms=0, target_view=0x2000)
    decoded_bytes = decode_rpc(data_bytes, bits_bytes)
    assert decoded_bytes['params'][0] == b''


def test_u64_timestamp_roundtrip():
    """u64 timestamp survives encode/decode including values > 65535."""
    for ts in [0, 100, 32767, 32768, 50000, 65535, 65536, 100000, 200000, 955000]:
        data, bits = encode_rpc_subsequent('RPC_Int', [42], view_id=1, timestamp_ms=ts, target_view=0x2000)
        decoded = decode_rpc(data, bits)
        assert decoded['timestamp_ms'] == ts, \
            f"timestamp={ts}: expected {ts}, got {decoded['timestamp_ms']}"


def test_u64_timestamp_first_use():
    """First-use encoding also preserves full u64 timestamp."""
    for ts in [0, 127, 128, 32767, 32768, 50000, 65536, 200000]:
        data, bits = encode_rpc_first_use('RPC_Int', [42], view_id=1, timestamp_ms=ts, target_view=0x2000)
        decoded = decode_rpc(data, bits)
        assert decoded['timestamp_ms'] == ts, \
            f"timestamp={ts}: expected {ts}, got {decoded['timestamp_ms']}"


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


def test_bytes_param_size_limit():
    """Decoding a bytes param with count > MAX_BYTES_PARAM_SIZE raises ValueError."""
    from protocol.unity_protocol import MAX_BYTES_PARAM_SIZE
    # Build a minimal RPC payload with a bytes param whose count exceeds the limit
    # Use encode_rpc_subsequent for RPC_Bytes, then tamper with the count field
    payload, bits = encode_rpc_subsequent('RPC_Bytes', [b'\x00'], 1, 0, RPCMode.Server, target_view=0x2000)
    result = decode_rpc(payload, bits)
    assert result['method_name'] == 'RPC_Bytes'
    assert result['params'][0] == b'\x00'

    # Now build a payload with an absurd count
    bs = BitStream(payload, bits)
    # Find where the bytes count is and replace it with a huge value
    # Easier: construct a minimal bitstream manually
    payload2, bits2 = encode_rpc_subsequent('RPC_Bytes', [b''], 1, 0, RPCMode.Server, target_view=0x2000)
    # Replace the 4-byte count (value 0) with MAX_BYTES_PARAM_SIZE + 1
    import pytest
    bs2 = BitStream(payload2, bits2)
    # Navigate to the param area: for subsequent RPC_Bytes, params start after mode bits
    # The count is at a specific bit offset - just test by encoding a huge payload
    # Instead, test through decode_rpc by crafting raw bytes
    big_count = MAX_BYTES_PARAM_SIZE + 1
    # Encode an RPC with 0-length bytes, then find and replace the count
    data = bytearray(payload2)
    # The count is the last 4 bytes of meaningful data before end (big-endian u32)
    # For an empty bytes param, the count=0 is encoded as 4 zero bytes right before the end
    # Easier approach: just use _decode_params directly
    from protocol.unity_protocol import _decode_params
    count_bs = BitStream()
    count_bs.write_u32_be(big_count)
    count_bs.pos = 0
    with pytest.raises(ValueError, match="bytes param too large"):
        _decode_params(count_bs, ['bytes'])


def test_method_tag_registration():
    """register_method_tag sets the method_tag used for first-use encoding.

    method_tag cannot be derived from method_index (see
    docs/research/2026-07-12-method-tag-real-derivation.md) — it must be
    registered directly from a real captured value.
    """
    saved_tag = dict(METHOD_TAG_MAP)
    try:
        register_method_tag('RPC_Int', 8)
        payload, bits = encode_rpc_first_use('RPC_Int', [42], target_view=0x2000)
        all_bits = ''.join(f'{b:08b}' for b in payload)
        guid, hash_val = compute_method_id('RPC_Int')
        method_id_bits = (len(guid) + len(hash_val)) * 8
        hash_extra_bits = method_id_bits - 48
        tag_start = 160 + hash_extra_bits
        tag_bits = all_bits[tag_start:tag_start + 4]
        assert int(tag_bits, 2) == 8, \
            f"Expected method_tag=8, got {int(tag_bits, 2)}"
    finally:
        METHOD_TAG_MAP.clear()
        METHOD_TAG_MAP.update(saved_tag)


def test_register_method_indices_does_not_derive_tags():
    """register_method_indices must not guess method_tag from the index."""
    saved_tag = dict(METHOD_TAG_MAP)
    saved_index = dict(METHOD_INDEX_MAP)
    saved_reverse = dict(INDEX_TO_METHOD)
    try:
        METHOD_TAG_MAP.pop('RPC_Waffle', None)
        register_method_indices({'RPC_Waffle': 44})
        assert METHOD_TAG_MAP.get('RPC_Waffle') is None, \
            "register_method_indices must not write METHOD_TAG_MAP"
    finally:
        METHOD_TAG_MAP.clear()
        METHOD_TAG_MAP.update(saved_tag)
        METHOD_INDEX_MAP.clear()
        METHOD_INDEX_MAP.update(saved_index)
        INDEX_TO_METHOD.clear()
        INDEX_TO_METHOD.update(saved_reverse)


def test_method_tag_defaults_to_zero(caplog):
    """Unregistered methods use method_tag=0 and log a one-time warning."""
    saved_tag = dict(METHOD_TAG_MAP)
    try:
        METHOD_TAG_MAP.pop('RPC_Int', None)
        _reset_tag_fallback_warnings()
        with caplog.at_level('WARNING'):
            payload, bits = encode_rpc_first_use('RPC_Int', [42], target_view=0x2000)
        all_bits = ''.join(f'{b:08b}' for b in payload)
        guid, hash_val = compute_method_id('RPC_Int')
        method_id_bits = (len(guid) + len(hash_val)) * 8
        hash_extra_bits = method_id_bits - 48
        tag_start = 160 + hash_extra_bits
        tag_bits = all_bits[tag_start:tag_start + 4]
        assert int(tag_bits, 2) == 0
        assert any('RPC_Int' in rec.message and 'method_tag' in rec.message
                   for rec in caplog.records), \
            "Expected a fallback warning mentioning the method name and method_tag"
    finally:
        METHOD_TAG_MAP.clear()
        METHOD_TAG_MAP.update(saved_tag)


def test_register_method_tags_bulk():
    """register_method_tags sets METHOD_TAG_MAP for multiple methods at once."""
    saved_tag = dict(METHOD_TAG_MAP)
    try:
        register_method_tags({'RPC_Alpha': 4, 'RPC_Beta': 12})
        assert METHOD_TAG_MAP['RPC_Alpha'] == 4
        assert METHOD_TAG_MAP['RPC_Beta'] == 12
    finally:
        METHOD_TAG_MAP.clear()
        METHOD_TAG_MAP.update(saved_tag)


def test_loader_assembly_tags_match_ground_truth():
    """The 13 built-in Loader methods' tags match the captured ground truth.

    Regression test against silently reintroducing the disproven
    `method_index & 0x0F` formula. See
    docs/research/2026-07-12-method-tag-real-derivation.md.
    """
    expected = {
        'RPC_Void': 0,
        'RPC_Int': 8,
        'RPC_Float': 12,
        'RPC_String': 0,
        'RPC_Vector3': 8,
        'RPC_Quaternion': 8,
        'RPC_Bytes': 12,
        'RPC_IntFloatString': 8,
        'RPC_NetworkPlayer': 4,
        'RPC_NetworkViewID': 8,
        'RPC_Alpha': 4,
        'RPC_Beta': 4,
        'RPC_Gamma': 4,
    }
    for name, tag in expected.items():
        assert METHOD_TAG_MAP[name] == tag, \
            f"{name}: expected tag={tag}, got {METHOD_TAG_MAP.get(name)}"


def test_u64_timestamp_high_values():
    """Large timestamp values survive encode→decode roundtrip."""
    for ts in [255, 256, 1000, 16383, 32767, 100000, 500000]:
        data, bits = encode_rpc_subsequent('RPC_Int', [42], view_id=1, timestamp_ms=ts, target_view=0x2000)
        decoded = decode_rpc(data, bits)
        assert decoded['timestamp_ms'] == ts, \
            f"timestamp={ts}: got {decoded['timestamp_ms']}"


def test_subsequent_remaining_bit_count():
    """Subsequent-use remaining count is total_bits - 121."""
    data, bits = encode_rpc_subsequent('RPC_Void', [], view_id=1, timestamp_ms=0, target_view=0x2000)
    all_bits = ''.join(f'{b:08b}' for b in data)
    remaining_bits = all_bits[104:120]
    remaining = int(remaining_bits, 2)
    assert remaining == bits - 121, \
        f"Expected {bits - 121}, got {remaining}"


def test_subsequent_extended_header_method_index_128():
    """method_index >= 128 uses a 4-bit-wider header (extension flag at bit
    89), confirmed against a real Unity client — see
    docs/research/2026-07-13-method-index-ceiling-fix.md. RPC_Gamma sits
    exactly at the 128 boundary in METHOD_INDEX_MAP."""
    assert METHOD_INDEX_MAP['RPC_Gamma'] == 128
    data, bits = encode_rpc_subsequent('RPC_Gamma', [43], view_id=1, timestamp_ms=0, target_view=0x2000)
    all_bits = ''.join(f'{b:08b}' for b in data)

    # Extension flag at bit 89 is set; bit 88 and the rest of the
    # reserved span (90-107) stay zero.
    assert all_bits[88] == '0'
    assert all_bits[89] == '1'
    assert all_bits[90:108] == '0' * 18

    # remaining_bit_count now sits at 108-123 and uses total_bits - 125.
    remaining = int(all_bits[108:124], 2)
    assert remaining == bits - 125, f"Expected {bits - 125}, got {remaining}"

    decoded = decode_rpc(data, bits)
    assert decoded['method_index'] == 128
    assert decoded['method_name'] == 'RPC_Gamma'
    assert decoded['target_view'] == 0x2000
    assert decoded['rpc_mode'] == RPCMode.Server
    assert decoded['params'] == [43]


def test_first_use_remaining_bit_count():
    """First-use remaining count is param_bits + 19 + target_bits."""
    data, bits = encode_rpc_first_use('RPC_Int', [42], view_id=1, timestamp_ms=0, target_view=0x2000)
    all_bits = ''.join(f'{b:08b}' for b in data)
    guid, hash_val = compute_method_id('RPC_Int')
    method_id_bits = (len(guid) + len(hash_val)) * 8
    hash_extra_bits = method_id_bits - 48
    remaining_start = 160 + hash_extra_bits + 20
    remaining_bits = all_bits[remaining_start:remaining_start + 16]
    remaining = int(remaining_bits, 2)
    # param_bits=32 (int), target_bits=0 (Server mode)
    assert remaining == 32 + 19 + 0, \
        f"Expected 51, got {remaining}"


def test_batch_index_encode_decode_roundtrip():
    methods = [('RPC_Int', 0x60), ('RPC_Float', 4), ('RPC_Void', 8),
               ('RPC_String', 124), ('RPC_Alpha', 0), ('RPC_Int', 76)]
    for name, idx in methods:
        data, bits = encode_batch_index(name, idx)
        assert data[0] == MSG_ID_BATCH_INDEX
        result = decode_batch_index(data)
        assert result is not None, f"decode returned None for {name}/{idx}"
        assert result['method_name'] == name
        assert result['method_index'] == idx


def test_batch_index_decode_rejects_wrong_msgid():
    assert decode_batch_index(b'\x1b\x00\x00\x00\x00\x00') is None


def test_batch_index_decode_rejects_short():
    assert decode_batch_index(b'\x07\x00\x00') is None


def test_batch_index_method_index_override():
    data_override, bits_override = encode_rpc_subsequent(
        'RPC_Int', [42], mode=RPCMode.Server, target_view=0x2000,
        method_index=0x60)
    data_default, bits_default = encode_rpc_subsequent(
        'RPC_Int', [42], mode=RPCMode.Server, target_view=0x2000)
    default_idx = METHOD_INDEX_MAP.get('RPC_Int')
    assert bits_override == bits_default, "bit length should match"
    if default_idx != 0x60:
        assert data_override != data_default, "override should produce different bytes"


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
