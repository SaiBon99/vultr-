import type { components } from "./schema";

type S = components["schemas"];
export type Health = S["Health"];
export type QuarantineList = S["QuarantineList"];
export type QuarantineSessionGroup = S["QuarantineSessionGroup"];
export type QuarantineItem = S["QuarantineItem"];
export type QuarantineStatus = S["QuarantineStatus"];
/** All four gate verdicts; ALLOW never reaches quarantine_queue. */
export type Verdict = S["Verdict"];
/** Verdicts a quarantine row can carry. */
export type FrozenVerdict = S["FrozenVerdict"];
export type RuleFlag = S["RuleFlag"];
export type JudgeStatus = S["JudgeStatus"];
export type JudgeNote = S["JudgeNote"];
export type DecideRequest = S["DecideRequest"];
export type DecideResponse = S["DecideResponse"];
export type AuditLog = S["AuditLog"];
export type PublicKey = S["PublicKey"];
export type Receipt = S["Receipt"];
export type CrawlRequest = S["CrawlRequest"];
export type CrawlResult = S["CrawlResult"];

export type CrawlLimits = CrawlResult["sandbox"]["limits"];

/** Run log lines (contracts/README.md wire rule 6). One NDJSON object per line. */
export interface RunStartLine {
  type: "run_start";
  run_id: string;
  kind: string;
  session_id: string | null;
  started_at: string;
  limits: CrawlLimits;
  image_id: string | null;
}

export type RunLogDir = "host_to_agent" | "agent_to_host";

/** A protocol line: `msg` when it parsed, `raw` for an unparseable agent line. */
export interface RunMsgLine {
  type: "msg";
  seq: number;
  t_ms: number;
  dir: RunLogDir;
  msg?: Record<string, unknown>;
  raw?: string;
}

/** A host-side event (`fetch` or `model`); extra fields vary by event. */
export interface RunHostLine {
  type: "host";
  seq: number;
  t_ms: number;
  event: string;
  [field: string]: unknown;
}

export interface RunEndLine {
  type: "run_end";
  status: "ok" | "error";
  http_status: number;
  error_code: string | null;
  exit_code: number | null;
  container_id: string | null;
  elapsed_ms: number;
  stderr: string;
  stderr_truncated: boolean;
  lines_dropped: number;
}

export type RunLogLine = RunStartLine | RunMsgLine | RunHostLine | RunEndLine;

export type ApiMode = "mock" | "live";

/** The review surface the UI needs. Mock and live adapters both implement it. */
export interface ReviewApi {
  getHealth(): Promise<Health>;
  listQuarantine(status?: QuarantineStatus): Promise<QuarantineList>;
  decide(id: string, body: DecideRequest): Promise<DecideResponse>;
  getAudit(sessionId?: string): Promise<AuditLog>;
  getPublicKey(): Promise<PublicKey>;
  getReceipt(id: string): Promise<Receipt>;
  crawl(body: CrawlRequest): Promise<CrawlResult>;
  getCrawlRunLog(runId: string): Promise<RunLogLine[]>;
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
    readonly code?: string,
    /** Set on /crawl 502 and 504; the transcript is at GET /crawl/runs/{run_id}/log. */
    readonly runId?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** One line for an inline error, with the machine code when the API sent one. */
export function describeError(err: unknown, fallback: string): string {
  if (err instanceof ApiError)
    return `${err.message}${err.code ? ` (${err.code})` : ""}`;
  return fallback;
}
