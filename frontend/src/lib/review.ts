import type {
  FrozenVerdict,
  QuarantineItem,
  QuarantineList,
  RuleFlag,
  Verdict,
} from "#lib/api/index.js";

/** Mirror of `x-rulebook` on RuleFlag in contracts/openapi.yaml; review.test.ts fails on drift. */
export const RULEBOOK = {
  precedence: ["FAIL_CLOSED", "BLOCKED", "NEEDS_REVIEW", "ALLOW"],
  max_clean_writes: 3,
  fail_closed_floor: 85,
  judge_priority_boost: 15,
  judge_boost_when: {
    recommended_action: "purge",
    risk_level: ["high", "critical"],
  },
} as const;

export interface RuleSpec {
  verdict: FrozenVerdict;
  weight: number;
  label: string;
  /** Plain-English reason shown when the rule fires. */
  reason: string;
  /** What the rule checks, shown in the passed list. */
  check: string;
}

export const RULES: Record<RuleFlag, RuleSpec> = {
  tainted_session: {
    verdict: "NEEDS_REVIEW",
    weight: 25,
    label: "Tainted session",
    reason:
      "The agent read external content in this session, so anything it writes may carry that content.",
    check: "Session has not read external content",
  },
  immediate_write_after_read: {
    verdict: "NEEDS_REVIEW",
    weight: 10,
    label: "Write right after a read",
    reason:
      "The write came straight after an external read, with no clean write in between.",
    check: "No write directly after an external read",
  },
  write_burst: {
    verdict: "NEEDS_REVIEW",
    weight: 15,
    label: "Write burst",
    reason: `This is write ${RULEBOOK.max_clean_writes + 1} or later in the session; more than ${RULEBOOK.max_clean_writes} writes is unusual.`,
    check: `At most ${RULEBOOK.max_clean_writes} writes in the session`,
  },
  overwrite_attempt: {
    verdict: "NEEDS_REVIEW",
    weight: 25,
    label: "Overwrite attempt",
    reason: "The write tries to replace an existing active memory.",
    check: "Insert only, no overwrite of an existing memory",
  },
  imperative_directive: {
    verdict: "BLOCKED",
    weight: 40,
    label: "Imperative directive",
    reason:
      "The text tells the agent to take an outbound action, contact someone, use a tool or ignore its limits.",
    check: "No directive aimed at an outbound action or policy override",
  },
  external_email: {
    verdict: "BLOCKED",
    weight: 45,
    label: "External email",
    reason: "The text names an email address outside the allowlisted domains.",
    check: "Every email address is on an allowlisted domain",
  },
  external_url: {
    verdict: "BLOCKED",
    weight: 45,
    label: "External URL",
    reason: "The text links to a host outside the allowlisted domains.",
    check: "Every URL host is on an allowlisted domain",
  },
  sensitive_tool: {
    verdict: "BLOCKED",
    weight: 45,
    label: "Sensitive tool",
    reason: "The text names a tool that can move data out, such as send_email.",
    check: "No sensitive tool names",
  },
  canary_overlap: {
    verdict: "BLOCKED",
    weight: 90,
    label: "Canary token",
    reason:
      "The text contains a planted canary token, proof that secret data is being copied.",
    check: "No canary token in the text",
  },
  poison_similarity: {
    verdict: "BLOCKED",
    weight: 90,
    label: "Matches purged poison",
    reason:
      "The text is close to a memory a reviewer already purged (cosine similarity at or above 0.85).",
    check: "Not similar to any purged memory",
  },
  missing_provenance: {
    verdict: "FAIL_CLOSED",
    weight: 0,
    label: "Missing provenance",
    reason:
      "The proxy could not tie the write to a known session and source, so it fails closed.",
    check: "Session and source are known",
  },
  invalid_schema: {
    verdict: "FAIL_CLOSED",
    weight: 0,
    label: "Invalid schema",
    reason: "The write did not match the expected shape, so it fails closed.",
    check: "Write matches the schema",
  },
  judge_failed: {
    verdict: "FAIL_CLOSED",
    weight: 0,
    label: "Judge failed",
    reason:
      "The isolated judge timed out or returned invalid JSON. The row fails closed instead of passing unexplained.",
    check: "Judge returned a valid explanation",
  },
};

export const ALL_FLAGS = Object.keys(RULES) as RuleFlag[];

const rank = (v: Verdict) =>
  (RULEBOOK.precedence as readonly Verdict[]).indexOf(v);

/** Hit flags first by verdict tier (FAIL_CLOSED first), then weight; the rest are passed. */
export function splitFlags(hits: readonly RuleFlag[]): {
  failed: RuleFlag[];
  passed: RuleFlag[];
} {
  const set = new Set(hits);
  const failed = ALL_FLAGS.filter((f) => set.has(f)).sort(
    (a, b) =>
      rank(RULES[a].verdict) - rank(RULES[b].verdict) ||
      RULES[b].weight - RULES[a].weight,
  );
  return { failed, passed: ALL_FLAGS.filter((f) => !set.has(f)) };
}

/** Uncapped weight sum, so the UI can show "135, capped at 100". */
export const weightSum = (hits: readonly RuleFlag[]): number =>
  hits.reduce((sum, f) => sum + RULES[f].weight, 0);

/** The +15 judge boost applied to effective_priority_score, as reported by the server. */
export const judgeBoost = (
  item: Pick<QuarantineItem, "risk_score" | "effective_priority_score">,
): number => Math.max(0, item.effective_priority_score - item.risk_score);

/**
 * How a judge failure changed the row. The contract escalates NEEDS_REVIEW to FAIL_CLOSED;
 * BLOCKED keeps its verdict and score; a row already failing closed on its own stays put.
 */
export function judgeFailure(
  item: Pick<QuarantineItem, "judge_status" | "verdict" | "rule_flags">,
): "escalated" | "kept" | null {
  if (item.judge_status !== "failed") return null;
  const ownFailClosed = item.rule_flags.some(
    (f) => f !== "judge_failed" && RULES[f].verdict === "FAIL_CLOSED",
  );
  return item.verdict === "FAIL_CLOSED" && !ownFailClosed
    ? "escalated"
    : "kept";
}

/** Override needs a typed reason for BLOCKED and FAIL_CLOSED rows. */
export const reasonRequired = (verdict: FrozenVerdict): boolean =>
  verdict === "BLOCKED" || verdict === "FAIL_CLOSED";

const byPriority = (a: QuarantineItem, b: QuarantineItem) =>
  b.effective_priority_score - a.effective_priority_score ||
  b.created_at.localeCompare(a.created_at);

/**
 * GET /quarantine order: items by (effective_priority_score DESC, created_at DESC); sessions by
 * their top item's effective_priority_score, then session created_at DESC. Timestamps share one
 * fixed-width UTC format, so string order is time order.
 */
export function sortQueue(list: QuarantineList): QuarantineList {
  const sessions = list.sessions.map((s) => ({
    ...s,
    items: [...s.items].sort(byPriority),
  }));
  const top = (s: (typeof sessions)[number]) =>
    s.items[0]?.effective_priority_score ?? -1;
  sessions.sort(
    (a, b) => top(b) - top(a) || b.created_at.localeCompare(a.created_at),
  );
  return { sessions };
}
