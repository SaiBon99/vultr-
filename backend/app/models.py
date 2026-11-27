"""Pydantic v2 wire models mirroring contracts/openapi.yaml components.schemas."""

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

GateMode = Literal["quarantined", "naive"]
Verdict = Literal["CLEAN_USER", "TAINTED_UNREVIEWED", "POLICY_BLOCKED", "INCONCLUSIVE"]
FrozenVerdict = Literal["TAINTED_UNREVIEWED", "POLICY_BLOCKED", "INCONCLUSIVE"]
RuleFlag = Literal[
    "tainted_session",
    "write_burst",
    "overwrite_attempt",
    "imperative_directive",
    "external_email",
    "external_url",
    "sensitive_tool",
    "canary_overlap",
    "poison_similarity",
    "missing_provenance",
    "invalid_schema",
    "judge_failed",
]
QuarantineStatus = Literal["quarantined", "purged", "overridden"]
JudgeStatus = Literal["pending", "done", "failed"]
SourceKind = Literal["email", "web", "file", "tool"]
HealthCheck = Literal["ok", "error", "skipped"]
AuditEventType = Literal[
    "session_created",
    "external_read",
    "memory_promoted",
    "memory_quarantined",
    "judge_completed",
    "judge_failed",
    "decision_purged",
    "decision_overridden",
    "receipt_signed",
]
PayloadHash = Annotated[str, StringConstraints(pattern=r"^sha256:[0-9a-f]{64}$")]


class Wire(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Error(Wire):
    detail: str
    code: str | None = None
    run_id: UUID | None = None


class HealthChecks(Wire):
    db: HealthCheck
    object_storage: HealthCheck
    inference: HealthCheck


class Health(Wire):
    status: Literal["ok", "degraded"]
    checks: HealthChecks


class CreateSessionRequest(Wire):
    gate_mode: GateMode | None = None
    label: str | None = Field(default=None, max_length=120)


class CreateSessionResponse(Wire):
    session_id: UUID
    session_token: str
    gate_mode: GateMode
    created_at: datetime


class ExternalSource(Wire):
    source_ref: str
    source_kind: SourceKind
    read_at: datetime


class ProxyReadRequest(Wire):
    source_ref: str = Field(max_length=2048)
    source_kind: SourceKind
    content: str | None = Field(default=None, max_length=200000)


class ProxyReadResponse(Wire):
    source_ref: str
    source_kind: SourceKind
    content: str
    tainted: Literal[True]


class MemoryWriteRequest(Wire):
    content: str = Field(min_length=1, max_length=8000)
    overwrite_id: UUID | None = None


class MemoryWriteAccepted(Wire):
    status: Literal["active"]
    verdict: Literal["CLEAN_USER"]
    memory_id: UUID
    payload_hash: PayloadHash


class MemoryWriteQuarantined(Wire):
    status: Literal["quarantined"]
    verdict: FrozenVerdict
    quarantine_id: UUID
    payload_hash: PayloadHash
    rule_flags: list[RuleFlag]


class ActiveMemory(Wire):
    id: UUID
    session_id: UUID
    content: str
    source: Literal["user", "external_override"]
    source_ref: str | None
    payload_hash: PayloadHash
    created_at: datetime
    distance: float | None = None


class ActiveMemories(Wire):
    items: list[ActiveMemory]


class JudgeNote(Wire):
    """Strict judge JSON; mirrors contracts/judge.schema.json."""

    model_config = ConfigDict(extra="forbid", strict=True)

    summary: str = Field(max_length=500)
    risk_level: Literal["low", "medium", "high", "critical"]
    recommended_action: Literal["purge", "override"]
    indicators: list[Annotated[str, StringConstraints(max_length=120)]] = Field(max_length=10)


class QuarantineItem(Wire):
    id: UUID
    session_id: UUID
    status: QuarantineStatus
    content: str | None
    payload_hash: PayloadHash
    source: Literal["user", "external"]
    source_ref: str | None
    source_snippet: str | None
    verdict: FrozenVerdict
    rule_flags: list[RuleFlag]
    judge_status: JudgeStatus
    judge_note: JudgeNote | None
    override_reason: str | None
    decided_by: str | None
    decided_at: datetime | None
    receipt_uri: str | None
    receipt_id: UUID | None
    created_at: datetime


class QuarantineSessionGroup(Wire):
    session_id: UUID
    label: str | None
    gate_mode: GateMode
    tainted: bool
    external_sources: list[ExternalSource]
    write_count: int = Field(ge=0)
    created_at: datetime
    items: list[QuarantineItem]


class QuarantineList(Wire):
    sessions: list[QuarantineSessionGroup]


class DecideRequest(Wire):
    action: Literal["purge", "override"]
    reason: str | None = Field(default=None, max_length=1000)


class Receipt(Wire):
    receipt_id: UUID
    event: QuarantineStatus
    quarantine_id: UUID
    session_id: UUID
    verdict: FrozenVerdict
    rule_flags: list[RuleFlag]
    payload_hash: PayloadHash
    audit_head_hash: PayloadHash
    override_reason: str | None
    timestamp: str
    key_id: str
    signature_alg: Literal["Ed25519"]
    signature_b64: str


class DecideResponse(Wire):
    item: QuarantineItem
    receipt: Receipt
    memory_id: UUID | None


class AuditEvent(Wire):
    seq: int = Field(ge=1)
    session_id: UUID | None
    event_type: AuditEventType
    target_id: UUID | None
    payload: dict[str, Any]
    prev_hash: PayloadHash
    event_hash: PayloadHash
    created_at: str


class AuditLog(Wire):
    events: list[AuditEvent]
    chain_valid: bool
    head_hash: PayloadHash
    first_invalid_seq: int | None = None


class Jwk(Wire):
    kty: Literal["OKP"]
    crv: Literal["Ed25519"]
    x: str


class PublicKey(Wire):
    alg: Literal["Ed25519"]
    key_id: str
    public_key_b64: str
    jwk: Jwk


class CrawlRequest(Wire):
    url: str = Field(min_length=8, max_length=2048)


class CrawlLimits(Wire):
    memory_mb: int = Field(ge=1)
    cpus: int = Field(ge=1)
    timeout_s: int = Field(ge=1)


class CrawlSandbox(Wire):
    runtime: Literal["docker"]
    container_id: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
    image_id: PayloadHash
    network: Literal["none"]
    limits: CrawlLimits


class CrawlUsage(Wire):
    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)


class CrawlPage(Wire):
    url: str
    final_url: str | None
    status: Literal["ok", "skipped", "failed"]
    title: str | None = Field(default=None, max_length=300)
    error: str | None = None


class CrawlResult(Wire):
    url: str
    final_url: str
    title: str = Field(max_length=300)
    summary: str = Field(max_length=1000)
    key_points: list[Annotated[str, StringConstraints(max_length=300)]] = Field(max_length=5)
    model: str
    inference_id: str = Field(min_length=1)
    usage: CrawlUsage | None
    elapsed_ms: int = Field(ge=0)
    sandbox: CrawlSandbox
    run_id: UUID
    log_uri: str | None
    pages: list[CrawlPage]
