"""Deterministic 4-state gate (contracts/README.md "Gate"). Pure: no I/O, no model calls."""

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from urllib.parse import urlsplit

CLEAN_USER = "CLEAN_USER"
TAINTED_UNREVIEWED = "TAINTED_UNREVIEWED"
POLICY_BLOCKED = "POLICY_BLOCKED"
INCONCLUSIVE = "INCONCLUSIVE"

# Flags in contract order; results are emitted in this order.
TAINT_FLAGS = ("tainted_session", "write_burst", "overwrite_attempt")
POLICY_FLAGS = (
    "imperative_directive",
    "external_email",
    "external_url",
    "sensitive_tool",
    "canary_overlap",
    "poison_similarity",
)
INCONCLUSIVE_FLAGS = ("missing_provenance", "invalid_schema", "judge_failed")
ALL_FLAGS = TAINT_FLAGS + POLICY_FLAGS + INCONCLUSIVE_FLAGS

MAX_CLEAN_WRITES = 3  # the 4th write in a session is a burst

_DIRECTIVE = re.compile(
    r"\balways\s+(?:forward|send|cc|bcc|email|copy|reply|include|share)\b"
    r"|\bforward\b[^.\n]{0,80}\b(?:to|all|every|any)\b"
    r"|\b(?:ignore|disregard|forget)\s+(?:all\s+|any\s+|the\s+|your\s+)?"
    r"(?:previous|prior|earlier|above|instructions?|rules?)\b"
    r"|\bfrom now on\b"
    r"|\b(?:do not|don't|never)\s+(?:tell|mention|inform|notify)\b"
    r"|\b(?:override|bypass)\s+(?:the\s+)?(?:policy|policies|rules?|safeguards?)\b",
    re.IGNORECASE,
)
_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@([A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)+)")
# Match the whole URL, then let urlsplit find the host, so userinfo (https://good.com:x@evil.com)
# cannot smuggle an allowlisted name past the check. Also catches protocol-relative //host links.
_URL = re.compile(r"(?:\bhttps?:|(?<![:\w/]))//[^\s\"'<>]+", re.IGNORECASE)
_SENSITIVE_TOOL = re.compile(
    r"\b(?:send_email|send_mail|forward_email|share_file|transfer_funds|run_shell"
    r"|execute_command|http_post|delete_\w+)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class GateInput:
    content: str
    session_tainted: bool
    prior_write_count: int = 0
    overwrite: bool = False
    allowlist: frozenset[str] = frozenset()
    canaries: frozenset[str] = frozenset()
    poison_similarity_hit: bool = False
    missing_provenance: bool = False
    invalid_schema: bool = False
    judge_failed: bool = False


@dataclass(frozen=True)
class GateResult:
    verdict: str
    rule_flags: tuple[str, ...] = field(default_factory=tuple)


def normalize_allowlist(domains: Iterable[str]) -> frozenset[str]:
    return frozenset(d.strip().lower().lstrip("@").lstrip(".") for d in domains if d.strip())


def _allowed(domain: str, allowlist: frozenset[str]) -> bool:
    d = domain.lower().rstrip(".")
    return any(d == a or d.endswith("." + a) for a in allowlist)


def _has_external_email(text: str, allowlist: frozenset[str]) -> bool:
    return any(not _allowed(m.group(1), allowlist) for m in _EMAIL.finditer(text))


def _has_external_url(text: str, allowlist: frozenset[str]) -> bool:
    for m in _URL.finditer(text):
        raw = m.group(0)
        try:
            host = urlsplit("http:" + raw if raw.startswith("//") else raw).hostname
        except ValueError:
            return True  # unparseable URL: treat as external (fail closed)
        if not host or not _allowed(host, allowlist):
            return True
    return False


def _canary_overlap(text: str, canaries: frozenset[str]) -> bool:
    low = text.lower()
    return any(c and c.lower() in low for c in canaries)


def evaluate(gate_in: GateInput) -> GateResult:
    text = gate_in.content
    hit = {
        "tainted_session": gate_in.session_tainted,
        "write_burst": gate_in.prior_write_count >= MAX_CLEAN_WRITES,
        "overwrite_attempt": gate_in.overwrite,
        "imperative_directive": bool(_DIRECTIVE.search(text)),
        "external_email": _has_external_email(text, gate_in.allowlist),
        "external_url": _has_external_url(text, gate_in.allowlist),
        "sensitive_tool": bool(_SENSITIVE_TOOL.search(text)),
        "canary_overlap": _canary_overlap(text, gate_in.canaries),
        "poison_similarity": gate_in.poison_similarity_hit,
        "missing_provenance": gate_in.missing_provenance,
        "invalid_schema": gate_in.invalid_schema,
        "judge_failed": gate_in.judge_failed,
    }
    flags = tuple(f for f in ALL_FLAGS if hit[f])
    if any(f in POLICY_FLAGS for f in flags):
        verdict = POLICY_BLOCKED
    elif any(f in INCONCLUSIVE_FLAGS for f in flags):
        verdict = INCONCLUSIVE
    elif flags:
        verdict = TAINTED_UNREVIEWED
    else:
        verdict = CLEAN_USER
    return GateResult(verdict, flags)
