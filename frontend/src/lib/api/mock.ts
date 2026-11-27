import audit from "../../../../contracts/fixtures/audit.json";
import health from "../../../../contracts/fixtures/health.json";
import keys from "../../../../contracts/fixtures/keys_public.json";
import quarantine from "../../../../contracts/fixtures/quarantine.json";
import receiptJson from "../../../../contracts/fixtures/receipts/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa3.json";
import { sha256Hex } from "../crypto/auditChain";
import { canonBytes } from "../crypto/canonical";
import { sortQueue } from "../review";
import {
  JUDGE_DELAY_MS,
  pendingItem,
  pendingResolved,
  triageSession,
} from "./mockData";
import {
  ApiError,
  type AuditLog,
  type Health,
  type PublicKey,
  type QuarantineItem,
  type QuarantineList,
  type Receipt,
  type ReviewApi,
} from "./types";

const clone = <T>(v: unknown): T => structuredClone(v) as T;
const fixtureReceipt = receiptJson as unknown as Receipt;
const microTime = () =>
  new Date().toISOString().replace(/\.(\d{3})Z$/, ".$1000Z");

function toBase64(buf: ArrayBuffer): string {
  let bin = "";
  for (const b of new Uint8Array(buf)) bin += String.fromCharCode(b);
  return btoa(bin);
}

interface Signer {
  key: PublicKey;
  sign: (
    unsigned: Omit<Receipt, "signature_b64" | "key_id">,
  ) => Promise<Receipt>;
}

/**
 * Ephemeral Ed25519 key made in this tab, so mock receipts are signed for the real decision
 * and the browser verification path runs for real. Falls back to the fixture key and receipt
 * where Web Crypto lacks Ed25519.
 */
async function createSigner(): Promise<Signer | null> {
  try {
    const pair = (await crypto.subtle.generateKey({ name: "Ed25519" }, true, [
      "sign",
      "verify",
    ])) as CryptoKeyPair;
    const raw = await crypto.subtle.exportKey("raw", pair.publicKey);
    const jwk = await crypto.subtle.exportKey("jwk", pair.publicKey);
    const keyIdDigest = await crypto.subtle.digest("SHA-256", raw);
    const key_id = Array.from(new Uint8Array(keyIdDigest), (b) =>
      b.toString(16).padStart(2, "0"),
    )
      .join("")
      .slice(0, 16);
    const key: PublicKey = {
      alg: "Ed25519",
      key_id,
      public_key_b64: toBase64(raw),
      jwk: { kty: "OKP", crv: "Ed25519", x: jwk.x ?? "" },
    };
    return {
      key,
      sign: async (unsigned) => {
        const body = { ...unsigned, key_id };
        const sig = await crypto.subtle.sign(
          "Ed25519",
          pair.privateKey,
          canonBytes(body),
        );
        return { ...body, signature_b64: toBase64(sig) };
      },
    };
  } catch {
    return null;
  }
}

export interface MockOptions {
  /** How long the pending judge row stays pending. */
  judgeDelayMs?: number;
}

/** Mock adapter: serves ../contracts/fixtures plus mockData rows, applies decisions in memory. */
export function createMockApi({
  judgeDelayMs = JUDGE_DELAY_MS,
}: MockOptions = {}): ReviewApi {
  const base = clone<QuarantineList>(quarantine);
  base.sessions[0].items.push(clone<QuarantineItem>(pendingItem));
  base.sessions[0].write_count += 1;
  base.sessions.push(clone(triageSession));
  const state = sortQueue(base);
  const started = Date.now();
  const receipts = new Map<string, Receipt>();
  let signer: Promise<Signer | null> | undefined;

  const items = () => state.sessions.flatMap((s) => s.items);
  const find = (id: string) => items().find((i) => i.id === id);

  function receiptFor(
    item: QuarantineItem,
  ): Omit<Receipt, "signature_b64" | "key_id"> {
    return {
      receipt_id: item.receipt_id ?? crypto.randomUUID(),
      event: item.status === "purged" ? "purged" : "overridden",
      quarantine_id: item.id,
      session_id: item.session_id,
      verdict: item.verdict,
      risk_score: item.risk_score,
      rule_flags: item.rule_flags,
      payload_hash: item.payload_hash,
      audit_head_hash: audit.head_hash,
      override_reason: item.override_reason,
      timestamp: (item.decided_at ?? microTime()).replace(/\.\d+Z$/, "Z"),
      signature_alg: "Ed25519",
    };
  }

  /** Signs receipts for rows that arrive already decided, once the key exists. */
  function getSigner(): Promise<Signer | null> {
    signer ??= createSigner().then(async (s) => {
      if (s)
        for (const item of items())
          if (item.receipt_id)
            receipts.set(item.receipt_id, await s.sign(receiptFor(item)));
      return s;
    });
    return signer;
  }

  function resolveJudge() {
    if (Date.now() - started < judgeDelayMs) return;
    const row = find(pendingItem.id);
    if (row?.judge_status === "pending") {
      Object.assign(row, clone(pendingResolved));
      state.sessions = sortQueue(state).sessions;
    }
  }

  return {
    getHealth: async () => clone<Health>(health),
    listQuarantine: async (status) => {
      resolveJudge();
      const list = clone<QuarantineList>(state);
      if (!status) return list;
      return sortQueue({
        sessions: list.sessions
          .map((s) => ({
            ...s,
            items: s.items.filter((i) => i.status === status),
          }))
          .filter((s) => s.items.length > 0),
      });
    },
    decide: async (id, body) => {
      const item = find(id);
      if (!item) throw new ApiError(404, "Not found");
      if (item.status !== "quarantined")
        throw new ApiError(409, "Row already decided", "already_decided");
      if (
        body.action === "override" &&
        (item.verdict === "BLOCKED" || item.verdict === "FAIL_CLOSED") &&
        !body.reason?.trim()
      ) {
        throw new ApiError(
          422,
          "A reason is required to override a blocked row",
          "reason_required",
        );
      }
      if (
        body.action === "override" &&
        `sha256:${await sha256Hex(item.content ?? "")}` !== item.payload_hash
      ) {
        throw new ApiError(
          409,
          "Content does not match payload_hash",
          "payload_hash_mismatch",
        );
      }
      const s = await getSigner();
      item.status = body.action === "purge" ? "purged" : "overridden";
      if (body.action === "purge") item.content = null;
      item.override_reason =
        body.action === "override" ? body.reason?.trim() || null : null;
      item.decided_by = "reviewer";
      item.decided_at = microTime();
      item.receipt_id = crypto.randomUUID();
      item.receipt_uri = `s3://quarantine-receipts/receipts/${item.receipt_id}.json`;
      const receipt = s
        ? await s.sign(receiptFor(item))
        : clone<Receipt>(fixtureReceipt);
      receipts.set(item.receipt_id, receipt);
      return {
        item: clone<QuarantineItem>(item),
        receipt: clone<Receipt>(receipt),
        memory_id: body.action === "override" ? crypto.randomUUID() : null,
      };
    },
    getAudit: async () => clone<AuditLog>(audit),
    getPublicKey: async () => {
      const s = await getSigner();
      return s ? clone<PublicKey>(s.key) : clone<PublicKey>(keys);
    },
    getReceipt: async (id) => {
      const s = await getSigner();
      const r = s
        ? receipts.get(id)
        : id === fixtureReceipt.receipt_id
          ? fixtureReceipt
          : undefined;
      if (!r) throw new ApiError(404, "Not found");
      return clone<Receipt>(r);
    },
    crawl: async (body) => ({
      url: body.url,
      final_url: body.url,
      title: "Mock page",
      summary: "Canned crawl result. Mock mode does not run the sandbox.",
      key_points: ["Mock data", "No container was started"],
      model: "mock",
      inference_id: "mock-inference",
      usage: null,
      elapsed_ms: 0,
      sandbox: {
        runtime: "docker",
        container_id: "0".repeat(64),
        image_id: "sha256:" + "0".repeat(64),
        network: "none",
        limits: { memory_mb: 512, cpus: 1, timeout_s: 30 },
      },
    }),
  };
}
