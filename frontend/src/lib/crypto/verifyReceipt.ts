import type { components } from "#lib/api/schema.js";
import { canonBytes } from "./canonical";

export type Receipt = components["schemas"]["Receipt"];
export type PublicKey = components["schemas"]["PublicKey"];

function fromBase64(b64: string): Uint8Array<ArrayBuffer> {
  const bin = atob(b64);
  const out = new Uint8Array(new ArrayBuffer(bin.length));
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

/** Ed25519 over canon(receipt without signature_b64), per contracts/README.md rule 4 and 5. */
export async function verifyReceipt(
  receipt: Receipt,
  key: Pick<PublicKey, "jwk">,
): Promise<boolean> {
  try {
    const { signature_b64, ...unsigned } = receipt;
    const pub = await crypto.subtle.importKey(
      "jwk",
      key.jwk,
      { name: "Ed25519" },
      false,
      ["verify"],
    );
    return await crypto.subtle.verify(
      "Ed25519",
      pub,
      fromBase64(signature_b64),
      canonBytes(unsigned),
    );
  } catch {
    return false;
  }
}
