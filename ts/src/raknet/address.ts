export function encodeAddress(ip: string, port: number): Uint8Array {
  const parts = ip.split('.').map(Number);
  const result = new Uint8Array(6);
  result[0] = ((parts[0] ?? 0) ^ 0xff) & 0xff;
  result[1] = ((parts[1] ?? 0) ^ 0xff) & 0xff;
  result[2] = ((parts[2] ?? 0) ^ 0xff) & 0xff;
  result[3] = ((parts[3] ?? 0) ^ 0xff) & 0xff;
  result[4] = (port >>> 8) & 0xff;
  result[5] = port & 0xff;
  return result;
}

export interface DecodedAddress {
  ip: string;
  port: number;
}

export function decodeAddress(data: Uint8Array): DecodedAddress {
  const parts = [
    ((data[0] ?? 0) ^ 0xff) & 0xff,
    ((data[1] ?? 0) ^ 0xff) & 0xff,
    ((data[2] ?? 0) ^ 0xff) & 0xff,
    ((data[3] ?? 0) ^ 0xff) & 0xff,
  ];
  const ip = parts.join('.');
  const port = (((data[4] ?? 0) << 8) | (data[5] ?? 0)) & 0xffff;
  return { ip, port };
}
