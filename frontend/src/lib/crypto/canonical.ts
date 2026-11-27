/** Canonical JSON per contracts/README.md rule 1: sorted keys, no whitespace, UTF-8, no floats. */
export type Json =
  null | boolean | number | string | Json[] | { [key: string]: Json };

function compareCodePoints(a: string, b: string): number {
  const ac = Array.from(a);
  const bc = Array.from(b);
  const n = Math.min(ac.length, bc.length);
  for (let i = 0; i < n; i++) {
    const d = ac[i].codePointAt(0)! - bc[i].codePointAt(0)!;
    if (d !== 0) return d;
  }
  return ac.length - bc.length;
}

export function canon(value: unknown): string {
  if (value === null) return "null";
  switch (typeof value) {
    case "boolean":
      return value ? "true" : "false";
    case "string":
      return JSON.stringify(value);
    case "number":
      if (!Number.isSafeInteger(value))
        throw new Error("canonical JSON forbids floats");
      return String(value);
    case "object": {
      if (Array.isArray(value)) return `[${value.map(canon).join(",")}]`;
      const obj = value as Record<string, unknown>;
      const keys = Object.keys(obj).sort(compareCodePoints);
      return `{${keys.map((k) => `${JSON.stringify(k)}:${canon(obj[k])}`).join(",")}}`;
    }
    default:
      throw new Error(`cannot canonicalize ${typeof value}`);
  }
}

export const canonBytes = (value: unknown): Uint8Array<ArrayBuffer> =>
  new TextEncoder().encode(canon(value)) as Uint8Array<ArrayBuffer>;
