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
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
    readonly code?: string,
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
