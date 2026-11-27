import type { components } from "#lib/api/schema.js";
import { canon } from "./canonical";

export type AuditEvent = components["schemas"]["AuditEvent"];

export const GENESIS_HASH = `sha256:${"0".repeat(64)}`;

export async function sha256Hex(text: string): Promise<string> {
  const digest = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(text),
  );
  return Array.from(new Uint8Array(digest), (b) =>
    b.toString(16).padStart(2, "0"),
  ).join("");
}

export async function eventHash(
  prevHash: string,
  e: Pick<
    AuditEvent,
    "session_id" | "event_type" | "target_id" | "payload" | "created_at"
  >,
): Promise<string> {
  const body = canon({
    session_id: e.session_id,
    event_type: e.event_type,
    target_id: e.target_id,
    payload: e.payload,
    created_at: e.created_at,
  });
  return `sha256:${await sha256Hex(`${prevHash}|${body}`)}`;
}

export interface ChainResult {
  valid: boolean;
  first_invalid_seq: number | null;
  head_hash: string;
}

/** Recompute the full chain from genesis; stops at the first link or hash mismatch. */
export async function verifyAuditChain(
  events: AuditEvent[],
): Promise<ChainResult> {
  // head_hash is the stored hash of the last event, valid or not (same as backend verify_chain).
  let prev = GENESIS_HASH;
  let bad: number | null = null;
  for (const e of events) {
    if (
      bad === null &&
      (e.prev_hash !== prev || e.event_hash !== (await eventHash(prev, e)))
    ) {
      bad = e.seq;
    }
    prev = e.event_hash;
  }
  return { valid: bad === null, first_invalid_seq: bad, head_hash: prev };
}
