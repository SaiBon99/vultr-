import type { components } from "./schema";

type S = components["schemas"];
export type Health = S["Health"];
export type QuarantineList = S["QuarantineList"];
export type QuarantineSessionGroup = S["QuarantineSessionGroup"];
export type QuarantineItem = S["QuarantineItem"];
export type QuarantineStatus = S["QuarantineStatus"];
export type Verdict = S["FrozenVerdict"];
export type RuleFlag = S["RuleFlag"];
export type DecideRequest = S["DecideRequest"];
export type DecideResponse = S["DecideResponse"];
export type AuditLog = S["AuditLog"];
export type PublicKey = S["PublicKey"];
export type Receipt = S["Receipt"];

export type ApiMode = "mock" | "live";

/** The review surface the UI needs. Mock and live adapters both implement it. */
export interface ReviewApi {
  getHealth(): Promise<Health>;
  listQuarantine(status?: QuarantineStatus): Promise<QuarantineList>;
  decide(id: string, body: DecideRequest): Promise<DecideResponse>;
  getAudit(sessionId?: string): Promise<AuditLog>;
  getPublicKey(): Promise<PublicKey>;
  getReceipt(id: string): Promise<Receipt>;
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
