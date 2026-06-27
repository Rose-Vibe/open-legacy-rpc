const ENGLISH_CHAR_FREQUENCIES: readonly number[] = [
  0,
  0,
  0,
  0,
  0,
  0,
  0,
  0,
  0,
  0,
  722,
  0,
  0,
  2,
  0,
  0,
  0,
  0,
  0,
  0,
  0,
  0,
  0,
  0,
  0,
  0,
  0,
  0,
  0,
  0,
  0,
  0,
  11084,
  58,
  63,
  1,
  0,
  31,
  0,
  317,
  64,
  64,
  44,
  0,
  695,
  62,
  980,
  266,
  69,
  67,
  56,
  7,
  73,
  3,
  14,
  2,
  69,
  1,
  167,
  9,
  1,
  2,
  25,
  94,
  0,
  195,
  139,
  34,
  96,
  48,
  103,
  56,
  125,
  653,
  21,
  5,
  23,
  64,
  85,
  44,
  34,
  7,
  92,
  76,
  147,
  12,
  14,
  57,
  15,
  39,
  15,
  1,
  1,
  1,
  2,
  3,
  0,
  3611,
  845,
  1077,
  1884,
  5870,
  841,
  1057,
  2501,
  3212,
  164,
  531,
  2019,
  1330,
  3056,
  4037,
  848,
  47,
  2586,
  2919,
  4771,
  1707,
  535,
  1106,
  152,
  1243,
  100,
  0,
  2,
  0,
  10,
  0,
  ...new Array<number>(128).fill(0),
];

interface HuffmanNode {
  char: number | null;
  freq: number;
  left: HuffmanNode | null;
  right: HuffmanNode | null;
}

function buildHuffmanTree(frequencies: readonly number[]): HuffmanNode {
  const nodes: HuffmanNode[] = [];
  for (let i = 0; i < 256; i++) {
    const weight = Math.max(frequencies[i] ?? 0, 1);
    nodes.push({ char: i, freq: weight, left: null, right: null });
  }

  nodes.sort((a, b) => {
    if (a.freq !== b.freq) return a.freq - b.freq;
    return (b.char ?? 0) - (a.char ?? 0);
  });

  while (nodes.length > 1) {
    const left = nodes.shift();
    const right = nodes.shift();
    if (!left || !right) break;
    const combined: HuffmanNode = {
      char: null,
      freq: left.freq + right.freq,
      left,
      right,
    };
    let inserted = false;
    for (let i = 0; i < nodes.length; i++) {
      const n = nodes[i];
      if (n && n.freq >= combined.freq) {
        nodes.splice(i, 0, combined);
        inserted = true;
        break;
      }
    }
    if (!inserted) {
      nodes.push(combined);
    }
  }

  const root = nodes[0];
  if (!root) throw new Error('Failed to build Huffman tree');
  return root;
}

function buildCodeTable(root: HuffmanNode): Map<number, string> {
  const codes = new Map<number, string>();

  function walk(node: HuffmanNode, prefix: string): void {
    if (node.char !== null) {
      codes.set(node.char, prefix || '0');
      return;
    }
    if (node.left) walk(node.left, prefix + '0');
    if (node.right) walk(node.right, prefix + '1');
  }

  walk(root, '');
  return codes;
}

const tree = buildHuffmanTree(ENGLISH_CHAR_FREQUENCIES);
const codes = buildCodeTable(tree);

export function getTree(): HuffmanNode {
  return tree;
}

export function getCodes(): Map<number, string> {
  return codes;
}

export function encodeString(s: string): string {
  let bits = '';
  for (let i = 0; i < s.length; i++) {
    const ch = s.charCodeAt(i);
    const code = codes.get(ch);
    if (code === undefined) {
      throw new Error(
        `Character ${String(ch)} (0x${ch.toString(16).padStart(2, '0')}) not in Huffman table`,
      );
    }
    bits += code;
  }
  return bits;
}

export function encodeBytes(data: Uint8Array): string {
  let bits = '';
  for (let i = 0; i < data.length; i++) {
    const ch = data[i] ?? 0;
    const code = codes.get(ch);
    if (code === undefined) {
      throw new Error(
        `Byte ${String(ch)} (0x${ch.toString(16).padStart(2, '0')}) not in Huffman table`,
      );
    }
    bits += code;
  }
  return bits;
}

export function decodeString(bits: string): Uint8Array {
  const result: number[] = [];
  let node: HuffmanNode | null = tree;
  for (let i = 0; i < bits.length; i++) {
    node = bits[i] === '0' ? node.left : node.right;
    if (!node) break;
    if (node.char !== null) {
      result.push(node.char);
      node = tree;
    }
  }
  return new Uint8Array(result);
}

export function encodeStringForWire(s: string): string {
  let bits = encodeString(s);
  const remainder = bits.length % 8;
  if (remainder === 0) return bits;
  const paddingNeeded = 8 - remainder;
  for (let i = 0; i < 256; i++) {
    const code = codes.get(i);
    if (code !== undefined && code.length > paddingNeeded) {
      bits += code.slice(0, paddingNeeded);
      return bits;
    }
  }
  bits += '0'.repeat(paddingNeeded);
  return bits;
}

export function encodeBytesForWire(data: Uint8Array): string {
  let bits = encodeBytes(data);
  const remainder = bits.length % 8;
  if (remainder === 0) return bits;
  const paddingNeeded = 8 - remainder;
  for (let i = 0; i < 256; i++) {
    const code = codes.get(i);
    if (code !== undefined && code.length > paddingNeeded) {
      bits += code.slice(0, paddingNeeded);
      return bits;
    }
  }
  bits += '0'.repeat(paddingNeeded);
  return bits;
}
