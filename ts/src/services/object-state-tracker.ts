import { BitStream } from '../bitstream.js';

export interface FieldDef {
  name: string;
  type: 'int' | 'float' | 'Vector3' | 'Quaternion' | 'short' | 'bool';
  width?: number;
}

type FieldValue = number | number[] | boolean;

const DEFAULT_WIDTHS: Record<string, number> = {
  int: 32,
  float: 32,
  short: 16,
  bool: 1,
  Vector3: 96,
  Quaternion: 128,
};

function fieldToNumbers(def: FieldDef, value: FieldValue): number[] {
  if (def.type === 'Vector3') {
    const v = Array.isArray(value) ? value : [0, 0, 0];
    return [v[0] ?? 0, v[1] ?? 0, v[2] ?? 0];
  }
  if (def.type === 'Quaternion') {
    const q = Array.isArray(value) ? value : [0, 0, 0, 1];
    return [q[0] ?? 0, q[1] ?? 0, q[2] ?? 0, q[3] ?? 0];
  }
  if (def.type === 'bool') {
    return [value ? 1 : 0];
  }
  return [typeof value === 'number' ? value : 0];
}

function writeField(bs: BitStream, def: FieldDef, value: FieldValue): void {
  if (def.type === 'int') {
    let v = typeof value === 'number' ? value : 0;
    if (v < 0) v += 0x100000000;
    bs.writeBits(v & 0xffffffff, 32);
  } else if (def.type === 'float') {
    bs.writeFloatBE(typeof value === 'number' ? value : 0);
  } else if (def.type === 'short') {
    bs.writeBits((typeof value === 'number' ? value : 0) & 0xffff, 16);
  } else if (def.type === 'bool') {
    bs.writeBit(value ? 1 : 0);
  } else if (def.type === 'Vector3') {
    const v = Array.isArray(value) ? value : [0, 0, 0];
    bs.writeFloatBE(v[0] ?? 0);
    bs.writeFloatBE(v[1] ?? 0);
    bs.writeFloatBE(v[2] ?? 0);
  } else {
    const q = Array.isArray(value) ? value : [0, 0, 0, 1];
    bs.writeFloatBE(q[0] ?? 0);
    bs.writeFloatBE(q[1] ?? 0);
    bs.writeFloatBE(q[2] ?? 0);
    bs.writeFloatBE(q[3] ?? 0);
  }
}

export class ObjectStateTracker {
  readonly viewId: number;
  private fields: FieldDef[];
  private currentValues: Map<string, FieldValue> = new Map();
  private prevNumbers: Map<string, number[]> = new Map();
  private dirty: Set<string> = new Set();
  private isFirst = true;

  constructor(viewId: number, fields: FieldDef[]) {
    this.viewId = viewId;
    this.fields = fields;
    for (const f of fields) {
      const defaultVal = this.defaultValue(f);
      this.currentValues.set(f.name, defaultVal);
      this.prevNumbers.set(f.name, fieldToNumbers(f, defaultVal));
    }
  }

  update(values: Record<string, FieldValue>): boolean[] {
    const flags: boolean[] = [];
    for (const f of this.fields) {
      if (f.name in values) {
        const newVal = values[f.name] ?? this.defaultValue(f);
        const newNums = fieldToNumbers(f, newVal);
        const prevNums = this.prevNumbers.get(f.name) ?? [];
        const changed = newNums.some((n, i) => n !== prevNums[i]);
        flags.push(changed);
        if (changed) {
          this.dirty.add(f.name);
          this.currentValues.set(f.name, newVal);
        }
      } else {
        flags.push(false);
      }
    }
    return flags;
  }

  getValues(): Record<string, FieldValue> {
    const result: Record<string, FieldValue> = {};
    for (const [name, val] of this.currentValues) {
      result[name] = val;
    }
    return result;
  }

  toBitStream(): BitStream {
    const bs = new BitStream();
    for (const f of this.fields) {
      writeField(bs, f, this.currentValues.get(f.name) ?? this.defaultValue(f));
    }
    return bs;
  }

  toDeltaBitStream(): {
    fieldValues: number[];
    prevValues: number[];
    fieldWidths: number[];
    isFirst: boolean;
  } | null {
    if (this.dirty.size === 0 && !this.isFirst) return null;
    return this.getDirtyFieldValues();
  }

  getDirtyFieldValues(): {
    fieldValues: number[];
    prevValues: number[];
    fieldWidths: number[];
    isFirst: boolean;
  } {
    const fieldValues: number[] = [];
    const prevValues: number[] = [];
    const fieldWidths: number[] = [];

    for (const f of this.fields) {
      const width = f.width ?? DEFAULT_WIDTHS[f.type] ?? 32;
      const curNums = fieldToNumbers(f, this.currentValues.get(f.name) ?? this.defaultValue(f));
      const prevNums = this.prevNumbers.get(f.name) ?? [];

      if (f.type === 'Vector3' || f.type === 'Quaternion') {
        for (let i = 0; i < curNums.length; i++) {
          fieldValues.push(curNums[i] ?? 0);
          prevValues.push(prevNums[i] ?? 0);
          fieldWidths.push(32);
        }
      } else {
        fieldValues.push(curNums[0] ?? 0);
        prevValues.push(prevNums[0] ?? 0);
        fieldWidths.push(width);
      }
    }

    return { fieldValues, prevValues, fieldWidths, isFirst: this.isFirst };
  }

  markClean(): void {
    for (const f of this.fields) {
      this.prevNumbers.set(
        f.name,
        fieldToNumbers(f, this.currentValues.get(f.name) ?? this.defaultValue(f)),
      );
    }
    this.dirty.clear();
    this.isFirst = false;
  }

  reset(): void {
    this.isFirst = true;
    this.dirty.clear();
    for (const f of this.fields) {
      this.prevNumbers.set(f.name, fieldToNumbers(f, this.defaultValue(f)));
    }
  }

  private defaultValue(f: FieldDef): FieldValue {
    if (f.type === 'Vector3') return [0, 0, 0];
    if (f.type === 'Quaternion') return [0, 0, 0, 1];
    if (f.type === 'bool') return false;
    return 0;
  }
}
