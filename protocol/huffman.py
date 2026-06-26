"""
RakNet StringCompressor Huffman encoder/decoder.

Uses the default englishCharacterFrequencies table from RakNet 3.x/4.x.

Tree construction matches RakNet's sorted-list algorithm:
- Leaf nodes sorted by (weight ascending, char index descending)
- Combined nodes inserted before the first existing node with weight >=
  the combined weight (stable insertion)
"""

ENGLISH_CHAR_FREQUENCIES = [
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 722, 0, 0, 2, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    11084, 58, 63, 1, 0, 31, 0, 317, 64, 64, 44, 0, 695, 62, 980, 266,
    69, 67, 56, 7, 73, 3, 14, 2, 69, 1, 167, 9, 1, 2, 25, 94,
    0, 195, 139, 34, 96, 48, 103, 56, 125, 653, 21, 5, 23, 64, 85, 44,
    34, 7, 92, 76, 147, 12, 14, 57, 15, 39, 15, 1, 1, 1, 2, 3,
    0, 3611, 845, 1077, 1884, 5870, 841, 1057, 2501, 3212, 164, 531, 2019, 1330, 3056, 4037,
    848, 47, 2586, 2919, 4771, 1707, 535, 1106, 152, 1243, 100, 0, 2, 0, 10, 0,
] + [0] * 128  # indices 128-255 all zero


class HuffmanNode:
    def __init__(self, char=None, freq=0, left=None, right=None):
        self.char = char
        self.freq = freq
        self.left = left
        self.right = right


def build_huffman_tree(frequencies):
    """Build a Huffman tree from a frequency table (256 entries).

    RakNet uses weight=max(freq,1) so all 256 chars are in the tree.
    Matches RakNet's sorted-list construction with specific tie-breaking.
    """
    nodes = []
    for i in range(256):
        weight = max(frequencies[i] if i < len(frequencies) else 0, 1)
        nodes.append(HuffmanNode(char=i, freq=weight))

    nodes.sort(key=lambda n: (n.freq, -(n.char if n.char is not None else 0)))

    while len(nodes) > 1:
        left = nodes.pop(0)
        right = nodes.pop(0)
        combined = HuffmanNode(freq=left.freq + right.freq, left=left, right=right)
        inserted = False
        for i in range(len(nodes)):
            if nodes[i].freq >= combined.freq:
                nodes.insert(i, combined)
                inserted = True
                break
        if not inserted:
            nodes.append(combined)

    return nodes[0] if nodes else None


def build_code_table(tree):
    """Build a dict mapping byte value -> bit string."""
    codes = {}
    if tree is None:
        return codes

    def walk(node, prefix=''):
        if node.char is not None:
            codes[node.char] = prefix if prefix else '0'
            return
        if node.left:
            walk(node.left, prefix + '0')
        if node.right:
            walk(node.right, prefix + '1')

    walk(tree)
    return codes


def decode_string(bits, tree):
    """Decode a bit string using the Huffman tree. Returns decoded bytes."""
    result = []
    node = tree
    for bit in bits:
        if bit == '0':
            node = node.left
        else:
            node = node.right
        if node is None:
            break
        if node.char is not None:
            result.append(node.char)
            node = tree
    return bytes(result)


# Build the default tree and code table
_tree = build_huffman_tree(ENGLISH_CHAR_FREQUENCIES)
_codes = build_code_table(_tree)


def get_tree():
    return _tree


def get_codes():
    return _codes


def encode_string(s):
    """Encode a string to a bit string using the default Huffman tree (raw, no padding)."""
    bits = ''
    for ch in s.encode('ascii'):
        if ch not in _codes:
            raise ValueError("Character %d (0x%02x) not in Huffman table" % (ch, ch))
        bits += _codes[ch]
    return bits


def encode_string_for_wire(s):
    """Encode a string with EncodeArray byte-alignment padding.

    RakNet's EncodeArray pads the output to a byte boundary by writing
    partial bits from a character whose code is longer than the padding needed.
    Returns the padded bit string (length is always a multiple of 8).
    """
    bits = encode_string(s)
    remainder = len(bits) % 8
    if remainder == 0:
        return bits
    padding_needed = 8 - remainder
    for i in range(256):
        code = _codes.get(i, '')
        if len(code) > padding_needed:
            bits += code[:padding_needed]
            return bits
    bits += '0' * padding_needed
    return bits
