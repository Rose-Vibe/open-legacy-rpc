import type { BitStream } from '../bitstream.js';
import { encodeStringForWire, decodeString } from '../huffman.js';
import type { ViewId } from '../unity/view-id.js';
import { decodeViewId16, encodeViewId16 } from '../unity/view-id.js';

export interface Serializer<T> {
  write(bs: BitStream, value: T): void;
  read(bs: BitStream): T;
}

export const int32: Serializer<number> = {
  write(bs, value) {
    bs.writeI32BE(value);
  },
  read(bs) {
    return bs.readI32BE();
  },
};

export const float32: Serializer<number> = {
  write(bs, value) {
    bs.writeFloatBE(value);
  },
  read(bs) {
    return bs.readFloatBE();
  },
};

export const string: Serializer<string> = {
  write(bs, value) {
    if (!value) {
      bs.writeCompressedU32(0);
      return;
    }
    const bits = encodeStringForWire(value);
    bs.writeCompressedU32(bits.length);
    for (let i = 0; i < bits.length; i++) {
      bs.writeBit(bits[i] === '1' ? 1 : 0);
    }
  },
  read(bs) {
    const bitCount = bs.readCompressedU32();
    if (bitCount === 0) return '';
    let bits = '';
    for (let i = 0; i < bitCount; i++) {
      bits += bs.readBit() ? '1' : '0';
    }
    return new TextDecoder().decode(decodeString(bits));
  },
};

export const bytes: Serializer<Uint8Array> = {
  write(bs, value) {
    bs.writeU32BE(value.length);
    bs.writeBytes(value);
  },
  read(bs) {
    const len = bs.readU32BE();
    return bs.readBytes(len);
  },
};

export const vector3: Serializer<[number, number, number]> = {
  write(bs, value) {
    bs.writeFloatBE(value[0]);
    bs.writeFloatBE(value[1]);
    bs.writeFloatBE(value[2]);
  },
  read(bs) {
    return [bs.readFloatBE(), bs.readFloatBE(), bs.readFloatBE()];
  },
};

export const quaternion: Serializer<[number, number, number, number]> = {
  write(bs, value) {
    bs.writeFloatBE(value[0]);
    bs.writeFloatBE(value[1]);
    bs.writeFloatBE(value[2]);
    bs.writeFloatBE(value[3]);
  },
  read(bs) {
    return [bs.readFloatBE(), bs.readFloatBE(), bs.readFloatBE(), bs.readFloatBE()];
  },
};

export const viewId: Serializer<ViewId> = {
  write(bs, value) {
    bs.writeU16BE(encodeViewId16(value.scope, value.id));
  },
  read(bs) {
    return decodeViewId16(bs.readU16BE());
  },
};

export const networkPlayer: Serializer<number> = {
  write(bs, value) {
    bs.writeI32BE(value);
  },
  read(bs) {
    return bs.readI32BE();
  },
};

export type FieldSchema<T> = {
  [K in keyof T]: Serializer<T[K]>;
};

export function createMessageSerializer<T extends Record<string, unknown>>(
  schema: FieldSchema<T>,
): Serializer<T> {
  const keys = Object.keys(schema) as Array<keyof T & string>;
  return {
    write(bs, value) {
      for (const key of keys) {
        schema[key].write(bs, value[key]);
      }
    },
    read(bs) {
      const result: Partial<T> = {};
      for (const key of keys) {
        result[key] = schema[key].read(bs);
      }
      return result as T;
    },
  };
}
