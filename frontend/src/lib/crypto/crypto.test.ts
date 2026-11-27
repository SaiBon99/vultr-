import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { canon } from "./canonical";
import { verifyAuditChain, type AuditEvent } from "./auditChain";
import { verifyReceipt, type PublicKey, type Receipt } from "./verifyReceipt";

const fx = <T>(name: string): T =>
  JSON.parse(
    readFileSync(
      new URL(`../../../../contracts/fixtures/${name}`, import.meta.url),
      "utf8",
    ),
  ) as T;

describe("canon", () => {
  it("sorts keys by code point, strips whitespace, keeps non-ASCII", () => {
    expect(
      canon({ b: 1, a: [true, null, "é"], "\u{1F600}": 2, z: { y: 1, x: 2 } }),
    ).toBe('{"a":[true,null,"é"],"b":1,"z":{"x":2,"y":1},"\u{1F600}":2}');
  });
  it("rejects floats", () => {
    expect(() => canon({ a: 1.5 })).toThrow();
  });
});

describe("audit chain", () => {
  it("accepts audit.json", async () => {
    const log = fx<{ events: AuditEvent[] }>("audit.json");
    expect(await verifyAuditChain(log.events)).toMatchObject({
      valid: true,
      first_invalid_seq: null,
    });
  });
  it("flags audit_broken.json at seq 5", async () => {
    const log = fx<{ events: AuditEvent[] }>("audit_broken.json");
    expect(await verifyAuditChain(log.events)).toMatchObject({
      valid: false,
      first_invalid_seq: 5,
    });
  });
});

describe("receipt", () => {
  const key = fx<PublicKey>("keys_public.json");
  it("verifies a signed receipt", async () => {
    const receipt = fx<Receipt>(
      "receipts/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa3.json",
    );
    expect(await verifyReceipt(receipt, key)).toBe(true);
  });
  it("rejects a tampered receipt", async () => {
    expect(await verifyReceipt(fx<Receipt>("receipt_tampered.json"), key)).toBe(
      false,
    );
  });
});
