import type {
  ChatTool,
  QuarantineStatus,
  RunLogLine,
  Verdict,
} from "#lib/api/index.js";

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

export const toolLabel: Record<ChatTool, string> = {
  browse: "Browse",
  remember: "Remember",
  recall: "Recall",
  place_order: "Place order",
  send_email: "Send email",
};

export const flagLabel = (flag: string): string => flag.replaceAll("_", " ");

const clip = (s: string, n = 80): string =>
  s.length > n ? `${s.slice(0, n - 1)}…` : s;

/** Picks the first string or number field in `keys` order, as `key value`. */
function pick(rec: Record<string, unknown>, keys: string[]): string[] {
  return keys.flatMap((k) => {
    const v = rec[k];
    return typeof v === "string" || typeof v === "number"
      ? [`${k.replaceAll("_", " ")} ${clip(String(v))}`]
      : [];
  });
}

/** One-line summary of a run log line for the viewer; full JSON is shown on demand. */
export function runLogSummary(line: RunLogLine): string {
  switch (line.type) {
    case "run_start":
      return `${line.kind} run, ${line.limits.memory_mb} MB, ${line.limits.cpus} CPU, ${line.limits.timeout_s} s`;
    case "msg": {
      if (!line.msg) return `unparseable: ${clip(line.raw ?? "")}`;
      const kind = typeof line.msg.type === "string" ? line.msg.type : "?";
      return [kind, ...pick(line.msg, ["url", "final_url", "title"])].join(
        ", ",
      );
    }
    case "host":
      return [
        line.event,
        ...pick(line, [
          "status",
          "bytes",
          "content_type",
          "model",
          "latency_ms",
          "error_code",
        ]),
      ].join(", ");
    case "run_end":
      return [
        line.status,
        `HTTP ${line.http_status}`,
        line.error_code,
        line.exit_code === null ? null : `exit ${line.exit_code}`,
        `${line.elapsed_ms} ms`,
        line.lines_dropped ? `${line.lines_dropped} lines dropped` : null,
      ]
        .filter((p): p is string => p !== null)
        .join(", ");
    default: {
      const unreachable: never = line;
      return String(unreachable);
    }
  }
}
