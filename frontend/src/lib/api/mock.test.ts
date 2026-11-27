import { describe, expect, it } from "vitest";
import { verifyReceipt } from "../crypto/verifyReceipt";
import { createMockApi } from "./mock";
import { ApiError } from "./types";

const ids = (
  list: Awaited<ReturnType<ReturnType<typeof createMockApi>["listQuarantine"]>>,
) => list.sessions.flatMap((s) => s.items.map((i) => i.id.slice(0, 4)));

describe("mock adapter", () => {
  it("serves every review state in contract order", async () => {
    const api = createMockApi({ judgeDelayMs: 60_000 });
    const list = await api.listQuarantine();
    const all = list.sessions.flatMap((s) => s.items);
    expect(new Set(all.map((i) => i.verdict))).toEqual(
      new Set(["BLOCKED", "NEEDS_REVIEW", "FAIL_CLOSED"]),
    );
    expect(new Set(all.map((i) => i.judge_status))).toEqual(
      new Set(["pending", "done", "failed"]),
    );
    expect(new Set(all.map((i) => i.status))).toEqual(
      new Set(["quarantined", "purged", "overridden"]),
    );
    expect(ids(list)).toEqual([
      "3333",
      "1111",
      "5555",
      "2222",
      "4444",
      "6666",
      "7777",
    ]);
  });

  it("resolves the pending judge and re-sorts by the boosted priority", async () => {
    const api = createMockApi({ judgeDelayMs: 0 });
    const list = await api.listQuarantine("quarantined");
    const row = list.sessions[0].items.find((i) => i.id.startsWith("5555"))!;
    expect(row.judge_status).toBe("done");
    expect(row.effective_priority_score).toBe(115);
    expect(ids(list).slice(0, 3)).toEqual(["5555", "1111", "2222"]);
  });

  it("requires a reason to override BLOCKED and signs a verifiable receipt", async () => {
    const api = createMockApi();
    const id = "11111111-1111-4111-8111-111111111111";
    await expect(api.decide(id, { action: "override" })).rejects.toMatchObject({
      status: 422,
      code: "reason_required",
    });
    const res = await api.decide(id, {
      action: "override",
      reason: "Checked with sales lead",
    });
    expect(res.item.status).toBe("overridden");
    expect(res.receipt.override_reason).toBe("Checked with sales lead");
    const key = await api.getPublicKey();
    expect(res.receipt.key_id).toBe(key.key_id);
    expect(await verifyReceipt(res.receipt, key)).toBe(true);
    expect(await verifyReceipt({ ...res.receipt, risk_score: 1 }, key)).toBe(
      false,
    );
    await expect(api.decide(id, { action: "purge" })).rejects.toBeInstanceOf(
      ApiError,
    );
  });

  it("re-signs receipts for rows that arrive already decided", async () => {
    const api = createMockApi();
    const key = await api.getPublicKey();
    const receipt = await api.getReceipt(
      "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa3",
    );
    expect(await verifyReceipt(receipt, key)).toBe(true);
  });
});
