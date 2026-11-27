import type { QuarantineStatus, Verdict } from "#lib/api/index.js";

export type Tone =
  "danger" | "warning" | "info" | "success" | "neutral" | "outline";

export const verdictTone: Record<Verdict, Tone> = {
  ALLOW: "success",
  NEEDS_REVIEW: "warning",
  BLOCKED: "danger",
  FAIL_CLOSED: "danger",
};

export const verdictLabel: Record<Verdict, string> = {
  ALLOW: "Allowed",
  NEEDS_REVIEW: "Needs review",
  BLOCKED: "Blocked",
  FAIL_CLOSED: "Fail closed",
};

export const statusTone: Record<QuarantineStatus, Tone> = {
  quarantined: "neutral",
  purged: "outline",
  overridden: "success",
};

export const statusLabel: Record<QuarantineStatus, string> = {
  quarantined: "Awaiting decision",
  purged: "Purged",
  overridden: "Overridden",
};

export const flagLabel = (flag: string): string => flag.replaceAll("_", " ");
