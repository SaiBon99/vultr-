import type { QuarantineStatus, Verdict } from "#lib/api/index.js";

export type Tone =
  "danger" | "warning" | "info" | "success" | "neutral" | "outline";

export const verdictTone: Record<Verdict, Tone> = {
  POLICY_BLOCKED: "danger",
  TAINTED_UNREVIEWED: "warning",
  INCONCLUSIVE: "info",
};

export const verdictLabel: Record<Verdict, string> = {
  POLICY_BLOCKED: "Policy blocked",
  TAINTED_UNREVIEWED: "Tainted, unreviewed",
  INCONCLUSIVE: "Inconclusive",
};

export const statusTone: Record<QuarantineStatus, Tone> = {
  quarantined: "neutral",
  purged: "outline",
  overridden: "success",
};

export const flagLabel = (flag: string): string => flag.replaceAll("_", " ");
