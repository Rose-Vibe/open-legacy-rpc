import struct


class BitStream:
    """Bit-level reader/writer for Unity/RakNet wire format.

    All multi-byte integers use big-endian encoding on wire (RakNet's
    DoEndianSwap=true behavior on x86).
    """

    def __init__(self, data=None, bit_length=None):
        if data is not None:
            self._buf = bytearray(data)
            self._bit_length = bit_length if bit_length is not None else len(data) * 8
        else:
            self._buf = bytearray()
            self._bit_length = 0
        self._pos = 0

    @property
    def pos(self):
        return self._pos

    @pos.setter
    def pos(self, value):
        self._pos = value

    @property
    def bit_length(self):
        return self._bit_length

    @property
    def remaining(self):
        return self._bit_length - self._pos

    def to_bytes(self):
        return bytes(self._buf)

    # ── Read operations ──

    def read_bit(self):
        byte_idx = self._pos >> 3
        bit_idx = 7 - (self._pos & 7)
        self._pos += 1
        return (self._buf[byte_idx] >> bit_idx) & 1

    def read_bits(self, n):
        val = 0
        for _ in range(n):
            val = (val << 1) | self.read_bit()
        return val

    def read_bool(self):
        return bool(self.read_bit())

    def read_u8(self):
        return self.read_bits(8)

    def read_u16_be(self):
        return self.read_bits(16)

    def read_i16_be(self):
        v = self.read_bits(16)
        return v - 0x10000 if v >= 0x8000 else v

    def read_u32_be(self):
        return self.read_bits(32)

    def read_i32_be(self):
        v = self.read_u32_be()
        return v - 0x100000000 if v >= 0x80000000 else v

    def read_float_be(self):
        bits = self.read_u32_be()
        return struct.unpack('>f', struct.pack('>I', bits))[0]

    def read_char(self):
        return chr(self.read_bits(8))

    def read_bytes(self, n):
        result = bytearray()
        for _ in range(n):
            result.append(self.read_bits(8))
        return bytes(result)

    def read_bits_as_str(self, n):
        result = []
        for _ in range(n):
            result.append('1' if self.read_bit() else '0')
        return ''.join(result)

    def read_compressed_u32(self):
        """Read WriteCompressed<uint32> with big-endian byte order on wire."""
        for byte_idx in range(3, 0, -1):
            flag = self.read_bit()
            if flag:
                continue
            shift = (3 - byte_idx) * 8
            return self.read_bits((byte_idx + 1) * 8) << shift
        flag = self.read_bit()
        if flag:
            return self.read_bits(4) << 24
        return self.read_bits(8) << 24

    def read_vector3(self):
        return (self.read_float_be(), self.read_float_be(), self.read_float_be())

    def read_quaternion(self):
        return (self.read_float_be(), self.read_float_be(),
                self.read_float_be(), self.read_float_be())

    # ── Write operations ──

    def _ensure_capacity(self, bits_needed):
        total = self._pos + bits_needed
        bytes_needed = (total + 7) >> 3
        if bytes_needed > len(self._buf):
            self._buf.extend(b'\x00' * (bytes_needed - len(self._buf)))

    def write_bit(self, val):
        self._ensure_capacity(1)
        byte_idx = self._pos >> 3
        bit_idx = 7 - (self._pos & 7)
        if val:
            self._buf[byte_idx] |= (1 << bit_idx)
        else:
            self._buf[byte_idx] &= ~(1 << bit_idx)
        self._pos += 1
        if self._pos > self._bit_length:
            self._bit_length = self._pos

    def write_bits(self, val, n):
        for i in range(n - 1, -1, -1):
            self.write_bit((val >> i) & 1)

    def write_bool(self, val):
        self.write_bit(1 if val else 0)

    def write_u8(self, val):
        self.write_bits(val & 0xFF, 8)

    def write_u16_be(self, val):
        self.write_bits(val & 0xFFFF, 16)

    def write_i16_be(self, val):
        if val < 0:
            val += 0x10000
        self.write_bits(val & 0xFFFF, 16)

    def write_u32_be(self, val):
        self.write_bits(val & 0xFFFFFFFF, 32)

    def write_i32_be(self, val):
        if val < 0:
            val += 0x100000000
        self.write_bits(val & 0xFFFFFFFF, 32)

    def write_float_be(self, val):
        bits = struct.unpack('>I', struct.pack('>f', val))[0]
        self.write_u32_be(bits)

    def write_char(self, ch):
        self.write_bits(ord(ch) & 0xFF, 8)

    def write_bytes(self, data):
        for b in data:
            self.write_u8(b)

    def write_compressed_u32(self, val):
        """Write WriteCompressed<uint32> with big-endian byte order on wire."""
        b = [(val >> 24) & 0xFF, (val >> 16) & 0xFF,
             (val >> 8) & 0xFF, val & 0xFF]
        for byte_idx in range(3, 0, -1):
            if b[byte_idx] == 0:
                self.write_bit(1)
            else:
                self.write_bit(0)
                shift = (3 - byte_idx) * 8
                self.write_bits(val >> shift, (byte_idx + 1) * 8)
                return
        if (b[0] & 0xF0) == 0:
            self.write_bit(1)
            self.write_bits(b[0] & 0x0F, 4)
        else:
            self.write_bit(0)
            self.write_bits(b[0], 8)

    def write_vector3(self, x, y, z):
        self.write_float_be(x)
        self.write_float_be(y)
        self.write_float_be(z)

    def write_quaternion(self, x, y, z, w):
        self.write_float_be(x)
        self.write_float_be(y)
        self.write_float_be(z)
        self.write_float_be(w)

    def read_double_be(self):
        bits = self.read_bits(64)
        return struct.unpack('>d', struct.pack('>Q', bits))[0]

    def write_double_be(self, val):
        bits = struct.unpack('>Q', struct.pack('>d', val))[0]
        self.write_bits(bits, 64)

    def align_read_to_byte(self):
        if self._pos & 7:
            self._pos = (self._pos + 7) & ~7

    def align_write_to_byte(self):
        if self._pos & 7:
            padding = 8 - (self._pos & 7)
            self.write_bits(0, padding)

    def read_aligned_bytes(self, n):
        self.align_read_to_byte()
        return self.read_bytes(n)

    def write_aligned_bytes(self, data):
        self.align_write_to_byte()
        self.write_bytes(data)
