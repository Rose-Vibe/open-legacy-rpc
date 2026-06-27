import { describe, it, expect } from 'vitest';
import { encodeAddress, decodeAddress } from '../src/raknet/address.js';

describe('Address encoding', () => {
  it('roundtrips 0.0.0.0:0', () => {
    const encoded = encodeAddress('0.0.0.0', 0);
    const decoded = decodeAddress(encoded);
    expect(decoded.ip).toBe('0.0.0.0');
    expect(decoded.port).toBe(0);
  });

  it('roundtrips 255.255.255.255:65535', () => {
    const encoded = encodeAddress('255.255.255.255', 65535);
    const decoded = decodeAddress(encoded);
    expect(decoded.ip).toBe('255.255.255.255');
    expect(decoded.port).toBe(65535);
  });

  it('roundtrips 127.0.0.1:7777', () => {
    const encoded = encodeAddress('127.0.0.1', 7777);
    const decoded = decodeAddress(encoded);
    expect(decoded.ip).toBe('127.0.0.1');
    expect(decoded.port).toBe(7777);
  });

  it('uses bitwise inversion for IP octets', () => {
    const encoded = encodeAddress('127.0.0.1', 0);
    expect(encoded[0]).toBe(127 ^ 0xff);
    expect(encoded[1]).toBe(0 ^ 0xff);
    expect(encoded[2]).toBe(0 ^ 0xff);
    expect(encoded[3]).toBe(1 ^ 0xff);
  });

  it('encodes port as big-endian u16', () => {
    const encoded = encodeAddress('0.0.0.0', 0x1234);
    expect(encoded[4]).toBe(0x12);
    expect(encoded[5]).toBe(0x34);
  });
});
