import { describe, it, expect } from 'vitest';
import { encodeString, encodeBytes, decodeString, encodeBytesForWire } from '../src/huffman.js';

describe('Huffman codec', () => {
  it('roundtrips empty string', () => {
    const bits = encodeString('');
    expect(bits).toBe('');
    const decoded = decodeString(bits);
    expect(decoded).toEqual(new Uint8Array(0));
  });

  it('roundtrips single character', () => {
    const bits = encodeString('a');
    expect(bits.length).toBeGreaterThan(0);
    const decoded = decodeString(bits);
    expect(decoded).toEqual(new Uint8Array([0x61]));
  });

  it('roundtrips ASCII string', () => {
    const input = 'Hello, World!';
    const bits = encodeString(input);
    const decoded = decodeString(bits);
    const expected = new Uint8Array(input.length);
    for (let i = 0; i < input.length; i++) expected[i] = input.charCodeAt(i);
    expect(decoded).toEqual(expected);
  });

  it('roundtrips all 256 byte values', () => {
    const data = new Uint8Array(256);
    for (let i = 0; i < 256; i++) data[i] = i;
    const bits = encodeBytes(data);
    const decoded = decodeString(bits);
    expect(decoded).toEqual(data);
  });

  it('encodeBytesForWire produces byte-aligned output', () => {
    const data = new Uint8Array([0x61, 0x62, 0x63]);
    const bits = encodeBytesForWire(data);
    expect(bits.length % 8).toBe(0);
  });

  it('wire-encoded then decoded matches original', () => {
    const data = new Uint8Array([0x48, 0x65, 0x6c, 0x6c, 0x6f]);
    const bits = encodeBytesForWire(data);
    const decoded = decodeString(bits);
    expect(decoded.slice(0, data.length)).toEqual(data);
  });
});
