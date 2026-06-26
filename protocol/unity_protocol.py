"""
Unity legacy networking protocol layer — RPC and state sync encoding/decoding.
"""
import struct
from enum import IntEnum

from .bitstream import BitStream
from .huffman import get_tree, get_codes, decode_string, encode_string_for_wire


class RPCMode(IntEnum):
    Server = 0
    Others = 1
    All = 2
    Player = 3
    OthersBuffered = 5
    AllBuffered = 6


MSG_ID_RPC = 0x1B


def register_method_names(names):
    """Pre-populate the method ID cache for server-side decode.

    Call this with all expected method names so that lookup_method_by_hash
    can resolve incoming first-use RPCs.
    """
    for name in names:
        get_method_id(name)


def compute_method_id(method_name):
    """Compute the first-use method identifier from a method name.

    The method_id is: 2 zero bits + Huffman(method_name), sized to
    ceil(Huffman_bit_length / 8) bytes. The first 6 bytes are the
    "class GUID" and the remainder is the "method hash".

    Returns (class_guid: bytes, method_hash: bytes).
    """
    if not method_name:
        raise ValueError("method_name must be non-empty")
    codes = get_codes()
    huffman_bits = ''.join(codes[ord(c)] for c in method_name)
    n = len(huffman_bits)

    total_bytes = (n + 7) // 8
    total_bits = total_bytes * 8

    content = '00' + huffman_bits

    if len(content) > total_bits:
        content = content[:total_bits]
    elif len(content) < total_bits:
        padding_needed = total_bits - len(content)
        for i in range(256):
            code = codes.get(i, '')
            if len(code) > padding_needed:
                content += code[:padding_needed]
                break
        else:
            content += '0' * padding_needed

    result = bytes(int(content[i:i+8], 2) for i in range(0, len(content), 8))
    return result[:6], result[6:]


_method_id_cache = {}


def get_method_id(method_name):
    """Get (class_guid, method_hash) for a method name, with caching."""
    if method_name not in _method_id_cache:
        _method_id_cache[method_name] = compute_method_id(method_name)
    return _method_id_cache[method_name]


def method_hash_hex(method_name):
    """Get the hex-encoded method hash for a method name."""
    _, h = get_method_id(method_name)
    return h.hex()


def class_guid_hex(method_name):
    """Get the hex-encoded class GUID for a method name."""
    g, _ = get_method_id(method_name)
    return g.hex()


def lookup_method_by_hash(hash_hex):
    """Look up a method name by its hash hex string.

    Checks the cache of previously computed method IDs.
    """
    for name, (_, h) in _method_id_cache.items():
        if h.hex() == hash_hex:
            return name
    return None

METHOD_INDEX_MAP = {}
INDEX_TO_METHOD = {}


def compute_method_index(method_rid, interface_method_count=0):
    """Compute the subsequent-use method index from .NET metadata.

    method_rid: the method's row number in the MethodDef table (1-based)
    interface_method_count: total interface methods in the assembly
                           whose RIDs come before method_rid

    Formula: (method_rid - 1 - interface_method_count) * 4

    The index is a 7-bit field (0-127). Methods beyond index 127 cannot
    use subsequent-use encoding.
    """
    idx = (method_rid - 1 - interface_method_count) * 4
    return idx


def register_method_index_table(method_entries):
    """Register method indices from an assembly's method table.

    method_entries: list of (method_name, method_rid, is_interface_method)
    tuples in RID order. Only methods with [RPC] attribute need names;
    pass None for non-RPC methods.

    Populates METHOD_INDEX_MAP and INDEX_TO_METHOD.
    """
    global METHOD_INDEX_MAP, INDEX_TO_METHOD
    interface_count = 0
    for name, rid, is_iface in method_entries:
        if is_iface:
            interface_count += 1
            continue
        if name is not None:
            idx = compute_method_index(rid, interface_count)
            METHOD_INDEX_MAP[name] = idx
            INDEX_TO_METHOD[idx] = name
            register_method_names([name])

INTERNAL_RPC_CONSTANT = 0x0000
USER_RPC_CONSTANT = 0x0002

INTERNAL_RPCS = {
    '__RPCNetworkInstantiate',
}

METHOD_SIGNATURES = {
    'RPC_Int': ['int'],
    'RPC_Float': ['float'],
    'RPC_String': ['string'],
    'RPC_Vector3': ['Vector3'],
    'RPC_Quaternion': ['Quaternion'],
    'RPC_Bytes': ['bytes'],
    'RPC_IntFloatString': ['int', 'float', 'string'],
    'RPC_Void': [],
    'RPC_Alpha': ['int'],
    'RPC_Beta': ['int'],
    'RPC_Gamma': ['int'],
    'RPC_NetworkViewID': ['NetworkViewID'],
    'RPC_NetworkPlayer': ['NetworkPlayer'],
}


def _register_loader_assembly():
    """Register method indices for the test Loader assembly.

    Assembly layout (MethodDef RIDs):
      1-4:   SerializeHandler (delegate)
      5-8:   ExperimentContext (class)
      9-15:  IExperiment (interface, 7 methods)
      16-42: Loader (MonoBehaviour)
    """
    _INTERFACE_METHODS = 7
    _LOADER_RPC_RIDS = {
        'RPC_Void': 28,
        'RPC_Int': 29,
        'RPC_Float': 30,
        'RPC_String': 31,
        'RPC_Vector3': 32,
        'RPC_Quaternion': 33,
        'RPC_Bytes': 34,
        'RPC_IntFloatString': 35,
        'RPC_NetworkPlayer': 36,
        'RPC_NetworkViewID': 37,
        'RPC_Alpha': 38,
        'RPC_Beta': 39,
        'RPC_Gamma': 40,
    }
    for name, rid in _LOADER_RPC_RIDS.items():
        idx = compute_method_index(rid, _INTERFACE_METHODS)
        METHOD_INDEX_MAP[name] = idx
        INDEX_TO_METHOD[idx] = name
    register_method_names(METHOD_SIGNATURES.keys())
    register_method_names(INTERNAL_RPCS)


_register_loader_assembly()


def encode_view_id(view_id):
    """Encode a NetworkViewID as 48-bit big-endian bytes."""
    return struct.pack('>HI', (view_id >> 32) & 0xFFFF, view_id & 0xFFFFFFFF)


def decode_view_id_bits(bs):
    """Read a 48-bit NetworkViewID from a BitStream."""
    return bs.read_bits(48)


def encode_view_id_16(scope, id_value):
    """Encode a NetworkViewID as 16-bit packed value for RPC params.

    scope: 'scene' for scene-baked views, 'allocated' for runtime-allocated
    id_value: the view's numeric ID
    """
    if scope == 'scene':
        return id_value << 2
    else:
        return 0x4000 | (id_value << 6)


def decode_view_id_16(val16):
    """Decode a 16-bit packed NetworkViewID from RPC params.

    Returns (scope, id_value) where scope is 'scene' or 'allocated'.
    """
    if val16 & 0x4000:
        return ('allocated', (val16 & 0x3FFF) >> 6)
    else:
        return ('scene', val16 >> 2)


def encode_rpc_subsequent(method_name, params, view_id=1, rpc_counter=0,
                          mode=RPCMode.Server):
    """Encode a subsequent-use RPC (method already registered on receiver)."""
    method_index = METHOD_INDEX_MAP.get(method_name)
    if method_index is None:
        raise ValueError(f"Unknown method for subsequent encoding: {method_name}")

    sig = METHOD_SIGNATURES.get(method_name, [])
    param_bs = BitStream()
    _encode_params(param_bs, sig, params)
    param_data = param_bs.to_bytes()
    param_bits = param_bs.bit_length

    target_bits = 1 if mode == RPCMode.Player else 0
    total_bits = 140 + target_bits + param_bits

    bs = BitStream()
    # msg_id
    bs.write_u8(MSG_ID_RPC)
    # ViewID (48 bits)
    bs.write_bytes(encode_view_id(view_id))
    # Invocation metadata (24 bits)
    counter_byte = (rpc_counter * 2) & 0xFF
    bs.write_u8(counter_byte)
    bs.write_u8(0x00)
    bs.write_u8(0x0b)
    # first_use = 0
    bs.write_bit(0)
    # method index (7 bits) — bottom 7 bits of method_index
    bs.write_bits(method_index, 7)
    # 16 bits of zeros
    bs.write_u16_be(0)
    # remaining_bit_count = total_bit_length - 121
    remaining = total_bits - 121
    bs.write_u16_be(remaining)
    # constant: 0x0000 for internal RPCs, 0x0002 for user RPCs
    constant = INTERNAL_RPC_CONSTANT if method_name in INTERNAL_RPCS else USER_RPC_CONSTANT
    bs.write_u16_be(constant)
    # RPCMode (4 bits)
    bs.write_bits(int(mode), 4)
    # mode=Player has a 1-bit target field
    if mode == RPCMode.Player:
        bs.write_bit(0)
    # Parameters
    for i in range(param_bs.bit_length):
        param_bs.pos = i
        bs.write_bit(param_bs.read_bit())

    return bs.to_bytes(), total_bits


def encode_rpc_first_use(method_name, params, view_id=1, rpc_counter=0,
                         mode=RPCMode.Server):
    """Encode a first-use RPC (includes method name hash)."""
    class_guid, method_hash = get_method_id(method_name)
    method_id_bits = (len(class_guid) + len(method_hash)) * 8
    length_indicator = method_id_bits // 4

    sig = METHOD_SIGNATURES.get(method_name, [])
    param_bs = BitStream()
    _encode_params(param_bs, sig, params)
    param_bits = param_bs.bit_length

    hash_extra_bits = method_id_bits - 48
    target_bits = 1 if mode == RPCMode.Player else 0
    param_start = 160 + hash_extra_bits + 52 + 4 + target_bits
    total_bits = param_start + param_bits

    bs = BitStream()
    bs.write_u8(MSG_ID_RPC)
    bs.write_bytes(encode_view_id(view_id))
    counter_byte = (rpc_counter * 2) & 0xFF
    bs.write_u8(counter_byte)
    bs.write_u8(0x00)
    bs.write_u8(0x0b)
    bs.write_bit(1)
    bs.write_bits(0, 7)
    while bs.pos < 104:
        bs.write_bit(0)
    bs.write_u8(length_indicator)
    bs.write_bytes(class_guid)
    bs.write_bytes(method_hash)
    # 52-bit internal metadata: method_tag(4) + zeros(16) + remaining_count(16) + constant(16)
    remaining_count = param_bits + 19 + target_bits
    bs.write_bits(0, 4)       # method_tag (unknown derivation, 0 is accepted)
    bs.write_bits(0, 16)      # zeros
    bs.write_u16_be(remaining_count)
    constant = INTERNAL_RPC_CONSTANT if method_name in INTERNAL_RPCS else USER_RPC_CONSTANT
    bs.write_u16_be(constant)
    # RPCMode (4 bits)
    bs.write_bits(int(mode), 4)
    # mode=Player has a 1-bit target field
    if mode == RPCMode.Player:
        bs.write_bit(0)
    for i in range(param_bs.bit_length):
        param_bs.pos = i
        bs.write_bit(param_bs.read_bit())

    return bs.to_bytes(), total_bits


def decode_rpc(payload, bit_length):
    """Decode a Unity RPC message. Returns a dict with decoded fields."""
    bs = BitStream(payload, bit_length)
    result = {}

    result['msg_id'] = bs.read_u8()
    result['view_id'] = decode_view_id_bits(bs)
    counter_byte = bs.read_u8()
    result['rpc_counter'] = counter_byte // 2
    bs.read_bits(16)  # rest of invocation metadata
    first_use = bs.read_bit()
    result['first_use'] = bool(first_use)

    if first_use:
        bs.read_bits(7)  # method ref bits
        bs.pos = 104
        length_indicator = bs.read_u8()
        method_id_bits = length_indicator * 4
        guid = bs.read_bytes(6)
        result['class_guid'] = guid.hex()
        hash_bytes = (method_id_bits - 48) // 8
        if hash_bytes > 0:
            method_hash = bs.read_bytes(hash_bytes)
            result['method_hash'] = method_hash.hex()
            result['method_name'] = lookup_method_by_hash(method_hash.hex()) or 'unknown'

        hash_extra_bits = method_id_bits - 48
        mode_start = 160 + hash_extra_bits + 52
        bs.pos = mode_start
    else:
        bs.pos = 80
        method_idx = bs.read_bits(8) & 0xFE
        result['method_name'] = INDEX_TO_METHOD.get(method_idx, f'unknown_0x{method_idx:02x}')
        bs.pos = 136

    result['rpc_mode'] = RPCMode(bs.read_bits(4))

    # mode=Player has a 1-bit target field before params
    if result['rpc_mode'] == RPCMode.Player:
        bs.read_bit()

    method = result.get('method_name', '')
    sig = METHOD_SIGNATURES.get(method, None)
    if sig is not None:
        result['params'] = _decode_params(bs, sig)

    return result


def _encode_params(bs, sig, params):
    """Encode RPC parameters into a BitStream."""
    for i, ptype in enumerate(sig):
        val = params[i] if i < len(params) else None
        if ptype == 'int':
            bs.write_i32_be(val or 0)
        elif ptype == 'float':
            bs.write_float_be(val or 0.0)
        elif ptype == 'string':
            _encode_string_param(bs, val or '')
        elif ptype == 'Vector3':
            v = val or (0, 0, 0)
            bs.write_vector3(*v)
        elif ptype == 'Quaternion':
            q = val or (0, 0, 0, 1)
            bs.write_quaternion(*q)
        elif ptype == 'bytes':
            data = val or b''
            bs.write_u32_be(len(data))
            bs.write_bytes(data)
        elif ptype == 'NetworkViewID':
            bs.write_bits(val or 0, 16)
        elif ptype == 'NetworkPlayer':
            bs.write_i32_be(val or 0)


def _decode_params(bs, sig):
    """Decode RPC parameters from a BitStream using the method signature."""
    params = []
    for ptype in sig:
        if ptype == 'int':
            params.append(bs.read_i32_be())
        elif ptype == 'float':
            params.append(bs.read_float_be())
        elif ptype == 'string':
            params.append(_decode_string_param(bs))
        elif ptype == 'Vector3':
            params.append(bs.read_vector3())
        elif ptype == 'Quaternion':
            params.append(bs.read_quaternion())
        elif ptype == 'bytes':
            count = bs.read_u32_be()
            params.append(bs.read_bytes(count))
        elif ptype == 'NetworkViewID':
            params.append(bs.read_bits(16))
        elif ptype == 'NetworkPlayer':
            params.append(bs.read_i32_be())
    return params


def _encode_string_param(bs, s):
    """Encode a string parameter using Huffman encoding."""
    if not s:
        bs.write_compressed_u32(0)
        return
    encoded_bits = encode_string_for_wire(s)
    bit_length = len(encoded_bits)
    bs.write_compressed_u32(bit_length)
    for bit_char in encoded_bits:
        bs.write_bit(1 if bit_char == '1' else 0)


def _decode_string_param(bs):
    """Decode a string parameter using Huffman encoding."""
    bit_length = bs.read_compressed_u32()
    if bit_length == 0:
        return ''
    huffman_bits = bs.read_bits_as_str(bit_length)
    tree = get_tree()
    decoded = decode_string(huffman_bits, tree)
    return decoded.decode('ascii', errors='replace')


# ── Network.Instantiate ──


def encode_instantiate_group_flags(group, level_prefix=0):
    """Encode the 16-bit group/flags field for Network.Instantiate params.

    bits 15-6: reserved (0), bits 5-3: group, bit 2: flag (1), bits 1-0: level_prefix
    """
    return (group << 3) | 0x04 | (level_prefix & 0x03)


def decode_instantiate_group_flags(val16):
    """Decode the 16-bit group/flags field. Returns (group, level_prefix)."""
    group = (val16 >> 3) & 0x07
    level_prefix = val16 & 0x03
    return group, level_prefix


def decode_instantiate_params(bs, remaining_bits):
    """Decode __RPCNetworkInstantiate param payload from a BitStream.

    Returns dict with: group, level_prefix, prefab_id (bytes),
    position (x,y,z), rotation (x,y,z,w), unknown_int32, view_id (scope, id).
    """
    result = {}
    group_flags = bs.read_bits(16)
    result['group'], result['level_prefix'] = decode_instantiate_group_flags(group_flags)

    prefab_bits = bs.read_bits_as_str(133)
    result['prefab_id_bits'] = prefab_bits

    x = bs.read_float_be()
    y = bs.read_float_be()
    z = bs.read_float_be()
    result['position'] = (x, y, z)

    qx = bs.read_float_be()
    qy = bs.read_float_be()
    qz = bs.read_float_be()
    qw = bs.read_float_be()
    result['rotation'] = (qx, qy, qz, qw)

    result['unknown_int32'] = bs.read_i32_be()
    view_id_16 = bs.read_bits(16)
    result['view_id'] = decode_view_id_16(view_id_16)

    return result


def encode_instantiate_params(group, prefab_id_bits, position, rotation,
                               view_id_scope, view_id_value,
                               unknown_int32=1, level_prefix=0):
    """Encode __RPCNetworkInstantiate params into a BitStream.

    prefab_id_bits: 133-character string of '0'/'1' (opaque prefab identifier)
    position: (x, y, z) tuple
    rotation: (x, y, z, w) quaternion tuple
    Returns BitStream with the encoded params.
    """
    bs = BitStream()
    bs.write_bits(encode_instantiate_group_flags(group, level_prefix), 16)

    for bit_char in prefab_id_bits:
        bs.write_bit(1 if bit_char == '1' else 0)

    bs.write_float_be(position[0])
    bs.write_float_be(position[1])
    bs.write_float_be(position[2])

    bs.write_float_be(rotation[0])
    bs.write_float_be(rotation[1])
    bs.write_float_be(rotation[2])
    bs.write_float_be(rotation[3])

    bs.write_i32_be(unknown_int32)
    bs.write_bits(encode_view_id_16(view_id_scope, view_id_value), 16)

    return bs


# ── State Sync ──

def encode_state_sync(view_id, timestamp, data_bs, is_first=False):
    """Encode a state sync message.

    data_bs: a BitStream containing the serialized field data.
    Returns (payload_bytes, total_bit_length).
    """
    bs = BitStream()
    bs.write_u8(MSG_ID_RPC)  # same msg_id as RPC
    bs.write_bytes(encode_view_id(view_id))
    bs.write_u16_be(timestamp)
    bs.write_u8(0x80 if is_first else 0x7f)
    bs.write_u16_be(0x0004)  # constant

    data_bits = data_bs.bit_length
    for i in range(data_bits):
        data_bs.pos = i
        bs.write_bit(data_bs.read_bit())

    total_bits = 96 + data_bits
    return bs.to_bytes(), total_bits


def decode_state_sync(payload, bit_length):
    """Decode a state sync message header. Returns dict with header fields
    and a BitStream positioned at the start of the data."""
    bs = BitStream(payload, bit_length)
    result = {}
    result['msg_id'] = bs.read_u8()
    result['view_id'] = decode_view_id_bits(bs)
    result['timestamp'] = bs.read_u16_be()
    result['flags'] = bs.read_u8()
    result['is_first'] = result['flags'] == 0x80
    result['constant'] = bs.read_u16_be()
    result['data_bit_length'] = bit_length - 96
    result['data_stream'] = bs  # positioned at data start
    return result


def encode_delta_state_sync(view_id, timestamp, field_values, prev_values,
                            field_widths, is_first=False):
    """Encode a ReliableDeltaCompressed state sync message.

    field_values: list of current field values (ints or floats)
    prev_values: list of previous field values (for dirty detection)
    field_widths: list of bit widths per field (all 32 in practice)
    Returns (payload_bytes, total_bit_length).
    """
    bs = BitStream()
    bs.write_u8(MSG_ID_RPC)
    bs.write_bytes(encode_view_id(view_id))
    bs.write_u16_be(timestamp)
    bs.write_u8(0x80 if is_first else 0x7f)
    bs.write_u16_be(0x0004)

    data_bits = 0
    for i, (cur, prev, width) in enumerate(
            zip(field_values, prev_values, field_widths)):
        dirty = (cur != prev)
        bs.write_bit(1 if dirty else 0)
        data_bits += 1
        if dirty:
            if isinstance(cur, float):
                bits = struct.unpack('>I', struct.pack('>f', cur))[0]
                bs.write_bits(bits, width)
            else:
                bs.write_bits(cur & ((1 << width) - 1), width)
            data_bits += width

    return bs.to_bytes(), 96 + data_bits


def decode_delta_state_sync(payload, bit_length, field_count, field_widths,
                            prev_values):
    """Decode a ReliableDeltaCompressed state sync message.

    field_count: number of serialized fields
    field_widths: list of bit widths per field
    prev_values: list of previous field values (raw integer bits)
    Returns dict with header and decoded field values.
    Field values are raw integer bits; use struct.unpack('>f', struct.pack('>I', v))
    to recover floats.
    """
    result = decode_state_sync(payload, bit_length)
    bs = result['data_stream']

    values = list(prev_values)
    dirty_flags = []
    for i in range(field_count):
        dirty = bs.read_bit()
        dirty_flags.append(dirty)
        if dirty:
            raw = bs.read_bits(field_widths[i])
            values[i] = raw

    result['dirty_flags'] = dirty_flags
    result['field_values'] = values
    return result
