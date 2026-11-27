import type { QuarantineStatus, Verdict } from "#lib/api/index.js";

export type Tone =
  "danger" | "warning" | "info" | "success" | "neutral" | "outline";

export const verdictTone: Record<Verdict, Tone> = {
  BLOCKED: "danger",
  NEEDS_REVIEW: "warning",
  FAIL_CLOSED: "danger",
};

export const verdictLabel: Record<Verdict, string> = {
  BLOCKED: "Blocked",
  NEEDS_REVIEW: "Needs review",
  FAIL_CLOSED: "Fail closed",
};

export const statusTone: Record<QuarantineStatus, Tone> = {
  quarantined: "neutral",
  purged: "outline",
  overridden: "success",
};

export const flagLabel = (flag: string): string => flag.replaceAll("_", " ");
