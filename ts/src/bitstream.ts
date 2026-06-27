const FLOAT_BUF = new ArrayBuffer(4);
const FLOAT_VIEW = new DataView(FLOAT_BUF);
const DOUBLE_BUF = new ArrayBuffer(8);
const DOUBLE_VIEW = new DataView(DOUBLE_BUF);

export class BitStream {
  private buf: Uint8Array;
  private _bitLength: number;
  private _pos: number;

  constructor(data?: Uint8Array, bitLength?: number) {
    if (data !== undefined) {
      this.buf = new Uint8Array(data);
      this._bitLength = bitLength ?? data.length * 8;
    } else {
      this.buf = new Uint8Array(64);
      this._bitLength = 0;
    }
    this._pos = 0;
  }

  get bitLength(): number {
    return this._bitLength;
  }

  get readOffset(): number {
    return this._pos;
  }

  set readOffset(value: number) {
    this._pos = value;
  }

  get remaining(): number {
    return this._bitLength - this._pos;
  }

  toBytes(): Uint8Array {
    const byteLen = (this._bitLength + 7) >>> 3;
    return this.buf.slice(0, byteLen);
  }

  static fromBytes(data: Uint8Array, bitLength?: number): BitStream {
    return new BitStream(data, bitLength);
  }

  private getByte(idx: number): number {
    // eslint-disable-next-line @typescript-eslint/no-non-null-assertion -- bounds checked by caller
    return this.buf[idx]!;
  }

  // ── Read operations ──

  readBit(): number {
    const byteIdx = this._pos >>> 3;
    const bitIdx = 7 - (this._pos & 7);
    this._pos += 1;
    return (this.getByte(byteIdx) >>> bitIdx) & 1;
  }

  readBits(n: number): number {
    let val = 0;
    for (let i = 0; i < n; i++) {
      val = (val << 1) | this.readBit();
    }
    return val >>> 0;
  }

  readBool(): boolean {
    return this.readBit() === 1;
  }

  readU8(): number {
    return this.readBits(8);
  }

  readU16BE(): number {
    return this.readBits(16);
  }

  readI16BE(): number {
    const v = this.readBits(16);
    return v >= 0x8000 ? v - 0x10000 : v;
  }

  readU32BE(): number {
    return this.readBits(32);
  }

  readI32BE(): number {
    const v = this.readU32BE();
    return v >= 0x80000000 ? v - 0x100000000 : v;
  }

  readFloatBE(): number {
    const bits = this.readU32BE();
    FLOAT_VIEW.setUint32(0, bits, false);
    return FLOAT_VIEW.getFloat32(0, false);
  }

  readDoubleBE(): number {
    const hi = this.readBits(32);
    const lo = this.readBits(32);
    DOUBLE_VIEW.setUint32(0, hi, false);
    DOUBLE_VIEW.setUint32(4, lo, false);
    return DOUBLE_VIEW.getFloat64(0, false);
  }

  readChar(): string {
    return String.fromCharCode(this.readBits(8));
  }

  readBytes(n: number): Uint8Array {
    const result = new Uint8Array(n);
    for (let i = 0; i < n; i++) {
      result[i] = this.readBits(8);
    }
    return result;
  }

  readCompressedU32(): number {
    for (let byteIdx = 3; byteIdx > 0; byteIdx--) {
      const flag = this.readBit();
      if (flag === 1) {
        continue;
      }
      const shift = (3 - byteIdx) * 8;
      return (this.readBits((byteIdx + 1) * 8) << shift) >>> 0;
    }
    const flag = this.readBit();
    if (flag === 1) {
      return (this.readBits(4) << 24) >>> 0;
    }
    return (this.readBits(8) << 24) >>> 0;
  }

  readVector3(): [number, number, number] {
    return [this.readFloatBE(), this.readFloatBE(), this.readFloatBE()];
  }

  readQuaternion(): [number, number, number, number] {
    return [this.readFloatBE(), this.readFloatBE(), this.readFloatBE(), this.readFloatBE()];
  }

  readAlignedBytes(n: number): Uint8Array {
    this.alignReadToByte();
    return this.readBytes(n);
  }

  alignReadToByte(): void {
    if (this._pos & 7) {
      this._pos = (this._pos + 7) & ~7;
    }
  }

  // ── Write operations ──

  private ensureCapacity(bitsNeeded: number): void {
    const total = this._pos + bitsNeeded;
    const bytesNeeded = (total + 7) >>> 3;
    if (bytesNeeded > this.buf.length) {
      const newSize = Math.max(bytesNeeded, this.buf.length * 2);
      const newBuf = new Uint8Array(newSize);
      newBuf.set(this.buf);
      this.buf = newBuf;
    }
  }

  writeBit(val: number): void {
    this.ensureCapacity(1);
    const byteIdx = this._pos >>> 3;
    const bitIdx = 7 - (this._pos & 7);
    if (val) {
      this.buf[byteIdx] = this.getByte(byteIdx) | (1 << bitIdx);
    } else {
      this.buf[byteIdx] = this.getByte(byteIdx) & ~(1 << bitIdx);
    }
    this._pos += 1;
    if (this._pos > this._bitLength) {
      this._bitLength = this._pos;
    }
  }

  writeBits(val: number, n: number): void {
    for (let i = n - 1; i >= 0; i--) {
      this.writeBit((val >>> i) & 1);
    }
  }

  writeBool(val: boolean): void {
    this.writeBit(val ? 1 : 0);
  }

  writeU8(val: number): void {
    this.writeBits(val & 0xff, 8);
  }

  writeU16BE(val: number): void {
    this.writeBits(val & 0xffff, 16);
  }

  writeI16BE(val: number): void {
    if (val < 0) {
      val += 0x10000;
    }
    this.writeBits(val & 0xffff, 16);
  }

  writeU32BE(val: number): void {
    this.writeBits(val >>> 0, 32);
  }

  writeI32BE(val: number): void {
    if (val < 0) {
      val += 0x100000000;
    }
    this.writeBits(val >>> 0, 32);
  }

  writeFloatBE(val: number): void {
    FLOAT_VIEW.setFloat32(0, val, false);
    this.writeU32BE(FLOAT_VIEW.getUint32(0, false));
  }

  writeDoubleBE(val: number): void {
    DOUBLE_VIEW.setFloat64(0, val, false);
    this.writeU32BE(DOUBLE_VIEW.getUint32(0, false));
    this.writeU32BE(DOUBLE_VIEW.getUint32(4, false));
  }

  writeChar(ch: string): void {
    this.writeBits(ch.charCodeAt(0) & 0xff, 8);
  }

  writeBytes(data: Uint8Array): void {
    for (let i = 0; i < data.length; i++) {
      this.writeU8(data[i] ?? 0);
    }
  }

  writeCompressedU32(val: number): void {
    val = val >>> 0;
    const b0 = (val >>> 24) & 0xff;
    const b1 = (val >>> 16) & 0xff;
    const b2 = (val >>> 8) & 0xff;
    const b3 = val & 0xff;
    const bytes = [b0, b1, b2, b3];
    for (let byteIdx = 3; byteIdx > 0; byteIdx--) {
      if (bytes[byteIdx] === 0) {
        this.writeBit(1);
      } else {
        this.writeBit(0);
        const shift = (3 - byteIdx) * 8;
        this.writeBits(val >>> shift, (byteIdx + 1) * 8);
        return;
      }
    }
    if ((b0 & 0xf0) === 0) {
      this.writeBit(1);
      this.writeBits(b0 & 0x0f, 4);
    } else {
      this.writeBit(0);
      this.writeBits(b0, 8);
    }
  }

  writeVector3(x: number, y: number, z: number): void {
    this.writeFloatBE(x);
    this.writeFloatBE(y);
    this.writeFloatBE(z);
  }

  writeQuaternion(x: number, y: number, z: number, w: number): void {
    this.writeFloatBE(x);
    this.writeFloatBE(y);
    this.writeFloatBE(z);
    this.writeFloatBE(w);
  }

  writeAlignedBytes(data: Uint8Array): void {
    this.alignWriteToByte();
    this.writeBytes(data);
  }

  alignWriteToByte(): void {
    if (this._pos & 7) {
      const padding = 8 - (this._pos & 7);
      this.writeBits(0, padding);
    }
  }
}
