import { getCodes } from '../huffman.js';

export function computeMethodId(methodName: string): {
  classGuid: Uint8Array;
  methodHash: Uint8Array;
} {
  if (!methodName) {
    throw new Error('methodName must be non-empty');
  }
  const codes = getCodes();
  let huffmanBits = '';
  for (let i = 0; i < methodName.length; i++) {
    const code = codes.get(methodName.charCodeAt(i));
    if (code) huffmanBits += code;
  }
  const n = huffmanBits.length;
  const totalBytes = Math.ceil(n / 8);
  const totalBits = totalBytes * 8;

  let content = '00' + huffmanBits;

  if (content.length > totalBits) {
    content = content.slice(0, totalBits);
  } else if (content.length < totalBits) {
    const paddingNeeded = totalBits - content.length;
    let padded = false;
    for (let i = 0; i < 256; i++) {
      const code = codes.get(i) ?? '';
      if (code.length > paddingNeeded) {
        content += code.slice(0, paddingNeeded);
        padded = true;
        break;
      }
    }
    if (!padded) {
      content += '0'.repeat(paddingNeeded);
    }
  }

  const result = new Uint8Array(totalBytes);
  for (let i = 0; i < totalBytes; i++) {
    result[i] = parseInt(content.slice(i * 8, i * 8 + 8), 2);
  }

  return {
    classGuid: result.slice(0, 6),
    methodHash: result.slice(6),
  };
}

const methodIdCache = new Map<string, { classGuid: Uint8Array; methodHash: Uint8Array }>();

export function getMethodId(methodName: string): {
  classGuid: Uint8Array;
  methodHash: Uint8Array;
} {
  let cached = methodIdCache.get(methodName);
  if (!cached) {
    cached = computeMethodId(methodName);
    methodIdCache.set(methodName, cached);
  }
  return cached;
}

export function lookupMethodByHash(hashHex: string): string | null {
  for (const [name, { methodHash }] of methodIdCache) {
    if (bytesToHex(methodHash) === hashHex) {
      return name;
    }
  }
  return null;
}

export function registerMethodNames(names: string[]): void {
  for (const name of names) {
    getMethodId(name);
  }
}

export function computeMethodIndex(methodRid: number, interfaceMethodCount: number): number {
  return (methodRid - 1 - interfaceMethodCount) * 4;
}

function bytesToHex(bytes: Uint8Array): string {
  let hex = '';
  for (let i = 0; i < bytes.length; i++) {
    hex += (bytes[i] ?? 0).toString(16).padStart(2, '0');
  }
  return hex;
}
