import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import type { QuarantineItem, QuarantineList } from "#lib/api/index.js";
import {
  ALL_FLAGS,
  RULEBOOK,
  RULES,
  judgeBoost,
  judgeFailure,
  reasonRequired,
  sortQueue,
  splitFlags,
  weightSum,
} from "./review";

const openapi = readFileSync(
  new URL("../../../contracts/openapi.yaml", import.meta.url),
  "utf8",
);
const fixture = JSON.parse(
  readFileSync(
    new URL("../../../contracts/fixtures/quarantine.json", import.meta.url),
    "utf8",
  ),
) as QuarantineList;

describe("RULES mirrors x-rulebook", () => {
  const block = openapi.slice(openapi.indexOf("x-rulebook:"));
  const flags = [
    ...block.matchAll(/^\s{10}(\w+): \{ verdict: (\w+), weight: (\d+) \}$/gm),
  ].map(([, flag, verdict, weight]) => ({
    flag,
    verdict,
    weight: Number(weight),
  }));

  it("has the same 13 flags, verdicts and weights", () => {
    expect(flags).toHaveLength(13);
    expect(
      ALL_FLAGS.map((f) => ({
        flag: f,
        verdict: RULES[f].verdict,
        weight: RULES[f].weight,
      })),
    ).toEqual(flags);
  });

  it("has the same constants", () => {
    const num = (key: string) =>
      Number(new RegExp(`${key}: (\\d+)`).exec(block)?.[1]);
    expect(num("max_clean_writes")).toBe(RULEBOOK.max_clean_writes);
    expect(num("fail_closed_floor")).toBe(RULEBOOK.fail_closed_floor);
    expect(num("judge_priority_boost")).toBe(RULEBOOK.judge_priority_boost);
  });
});

describe("review helpers", () => {
  it("orders failed flags by tier then weight and keeps the rest as passed", () => {
    const { failed, passed } = splitFlags([
      "tainted_session",
      "external_email",
      "judge_failed",
      "imperative_directive",
    ]);
    expect(failed).toEqual([
      "judge_failed",
      "external_email",
      "imperative_directive",
      "tainted_session",
    ]);
    expect(passed).toHaveLength(9);
  });

  it("sums weights uncapped", () => {
    expect(
      weightSum([
        "tainted_session",
        "immediate_write_after_read",
        "imperative_directive",
        "external_email",
      ]),
    ).toBe(120);
  });

  it("reads the judge boost and failure mode from the row", () => {
    const items = fixture.sessions.flatMap((s) => s.items);
    const byId = (id: string) => items.find((i) => i.id.startsWith(id))!;
    expect(judgeBoost(byId("1111"))).toBe(15);
    expect(judgeBoost(byId("2222"))).toBe(0);
    expect(judgeFailure(byId("4444"))).toBe("escalated");
    expect(judgeFailure(byId("1111"))).toBeNull();
    expect(
      judgeFailure({
        judge_status: "failed",
        verdict: "BLOCKED",
        rule_flags: ["external_url", "judge_failed"],
      }),
    ).toBe("kept");
  });

  it("requires an override reason only for BLOCKED and FAIL_CLOSED", () => {
    expect(reasonRequired("BLOCKED")).toBe(true);
    expect(reasonRequired("FAIL_CLOSED")).toBe(true);
    expect(reasonRequired("NEEDS_REVIEW")).toBe(false);
  });

  it("sorts items by priority then newest, and sessions by top item", () => {
    const item = (id: string, p: number, at: string) =>
      ({ id, effective_priority_score: p, created_at: at }) as QuarantineItem;
    const list = sortQueue({
      sessions: [
        {
          ...fixture.sessions[0],
          session_id: "low",
          items: [item("a", 25, "2026-11-27T10:00:00.000000Z")],
        },
        {
          ...fixture.sessions[0],
          session_id: "high",
          items: [
            item("b", 100, "2026-11-27T10:01:00.000000Z"),
            item("c", 115, "2026-11-27T10:00:00.000000Z"),
            item("d", 100, "2026-11-27T10:02:00.000000Z"),
          ],
        },
      ],
    });
    expect(list.sessions.map((s) => s.session_id)).toEqual(["high", "low"]);
    expect(list.sessions[0].items.map((i) => i.id)).toEqual(["c", "d", "b"]);
  });
});
