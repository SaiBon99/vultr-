import audit from "../../../../contracts/fixtures/audit.json";
import health from "../../../../contracts/fixtures/health.json";
import keys from "../../../../contracts/fixtures/keys_public.json";
import quarantine from "../../../../contracts/fixtures/quarantine.json";
import receiptJson from "../../../../contracts/fixtures/receipts/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa3.json";
import {
  ApiError,
  type QuarantineItem,
  type QuarantineList,
  type ReviewApi,
} from "./types";
import type { AuditLog, Health, PublicKey, Receipt } from "./types";

const clone = <T>(v: unknown): T => structuredClone(v) as T;
const receipt = receiptJson as unknown as Receipt;

/** Mock adapter: serves ../contracts/fixtures/*.json and applies decisions in memory. */
export function createMockApi(): ReviewApi {
  const state = clone<QuarantineList>(quarantine);
  const find = (id: string): QuarantineItem | undefined =>
    state.sessions.flatMap((s) => s.items).find((i) => i.id === id);

  return {
    getHealth: async () => clone<Health>(health),
    listQuarantine: async (status) => {
      const list = clone<QuarantineList>(state);
      if (!status) return list;
      return {
        sessions: list.sessions
          .map((s) => ({
            ...s,
            items: s.items.filter((i) => i.status === status),
          }))
          .filter((s) => s.items.length > 0),
      };
    },
    decide: async (id, body) => {
      const item = find(id);
      if (!item) throw new ApiError(404, "Not found");
      if (item.status !== "quarantined")
        throw new ApiError(409, "Row already decided", "already_decided");
      if (
        body.action === "override" &&
        item.verdict === "POLICY_BLOCKED" &&
        !body.reason?.trim()
      ) {
        throw new ApiError(
          422,
          "A reason is required to override a blocked row",
          "reason_required",
        );
      }
      const r = clone<Receipt>(receipt);
      item.status = body.action === "purge" ? "purged" : "overridden";
      if (body.action === "purge") item.content = null;
      item.override_reason = body.reason ?? null;
      item.decided_by = "reviewer";
      item.decided_at = new Date()
        .toISOString()
        .replace(/\.(\d{3})Z$/, ".$1000Z");
      item.receipt_id = r.receipt_id;
      return {
        item: clone<QuarantineItem>(item),
        receipt: r,
        memory_id: body.action === "override" ? crypto.randomUUID() : null,
      };
    },
    getAudit: async () => clone<AuditLog>(audit),
    getPublicKey: async () => clone<PublicKey>(keys),
    getReceipt: async (id) => {
      if (id !== receipt.receipt_id) throw new ApiError(404, "Not found");
      return clone<Receipt>(receipt);
    },
  };
}
