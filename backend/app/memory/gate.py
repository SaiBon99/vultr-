"""Deterministic write gate. Code sets the verdict; the judge model only explains it.

Rule table from spec.md:
- CLEAN_USER: no external reads in the session, no rule hits, insert-only.
- TAINTED_UNREVIEWED: write in a tainted session, more than MAX_WRITES_PER_SESSION writes in one session, or an overwrite.
- POLICY_BLOCKED: imperative directive, non-allowlisted URL/email domain, sensitive tool name, canary overlap, or similarity to confirmed poison.
- INCONCLUSIVE: missing provenance or invalid content. Fails closed in quarantine.
"""

import re
import zlib
from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlparse


class Verdict(str, Enum):
    CLEAN_USER = "CLEAN_USER"
    TAINTED_UNREVIEWED = "TAINTED_UNREVIEWED"
    POLICY_BLOCKED = "POLICY_BLOCKED"
    INCONCLUSIVE = "INCONCLUSIVE"


MAX_WRITES_PER_SESSION = 3
SIMILARITY_THRESHOLD = 0.5
CANARY_MARKER = "CANARY-"

IMPERATIVE = re.compile(r"\b(always|forward|ignore)\b", re.IGNORECASE)
SENSITIVE_TOOL = re.compile(r"\b(send_email|place_order)\b")
EMAIL_DOMAIN = re.compile(r"[\w.+-]+@([\w-]+(?:\.[\w-]+)+)")
URL_HOST = re.compile(r"https?://([^\s/'\"<>]+)")


@dataclass(frozen=True)
class WriteFacts:
    """Facts the service computes from storage. The gate itself does no I/O."""

    content: str | None
    session_id: str | None
    session_tainted: bool
    writes_in_session: int  # including the write being judged
    overwrites_existing: bool
    confirmed_poison_similar: bool


@dataclass(frozen=True)
class GateDecision:
    verdict: Verdict
    flags: tuple[str, ...]

    @property
    def quarantined(self) -> bool:
        return self.verdict is not Verdict.CLEAN_USER


def referenced_domains(text: str) -> list[str]:
    domains = [m.group(1).lower() for m in EMAIL_DOMAIN.finditer(text)]
    for m in URL_HOST.finditer(text):
        domains.append(urlparse("https://" + m.group(1)).hostname or m.group(1).lower())
    return sorted(set(domains))


def fingerprint(text: str, size: int = 3) -> frozenset[int]:
    """Stable word-shingle hashes (CRC32, not Python's per-process hash()).

    Purged rows keep only this fingerprint, so their text is wiped but similarity still works.
    """
    words = re.findall(r"[a-z0-9']+", text.lower())
    if not words:
        return frozenset()
    if len(words) < size:
        grams = [" ".join(words)]
    else:
        grams = [" ".join(words[i : i + size]) for i in range(len(words) - size + 1)]
    # Masked to 31 bits so values fit the INTEGER[] column in Postgres. Still stable across processes.
    return frozenset(zlib.crc32(g.encode()) & 0x7FFFFFFF for g in grams)


def jaccard(a: frozenset[int], b: frozenset[int]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def max_similarity(text: str, fingerprints: list[frozenset[int]]) -> float:
    fp = fingerprint(text)
    return max((jaccard(fp, known) for known in fingerprints), default=0.0)


def shingle_similarity(a: str, b: str) -> float:
    return jaccard(fingerprint(a), fingerprint(b))


def evaluate(facts: WriteFacts, allowed_domains: frozenset[str]) -> GateDecision:
    if not facts.session_id or not isinstance(facts.content, str) or not facts.content.strip():
        return GateDecision(Verdict.INCONCLUSIVE, ("missing_provenance_or_schema",))

    content = facts.content
    policy_flags: list[str] = []
    if IMPERATIVE.search(content):
        policy_flags.append("imperative_directive")
    if SENSITIVE_TOOL.search(content):
        policy_flags.append("sensitive_tool_name")
    for domain in referenced_domains(content):
        if domain not in allowed_domains:
            policy_flags.append(f"non_allowlisted_domain:{domain}")
    if CANARY_MARKER in content:
        policy_flags.append("canary_overlap")
    if facts.confirmed_poison_similar:
        policy_flags.append("similar_to_confirmed_poison")
    if policy_flags:
        return GateDecision(Verdict.POLICY_BLOCKED, tuple(policy_flags))

    review_flags: list[str] = []
    if facts.session_tainted:
        review_flags.append("tainted_session")
    if facts.writes_in_session > MAX_WRITES_PER_SESSION:
        review_flags.append("write_burst")
    if facts.overwrites_existing:
        review_flags.append("overwrite")
    if review_flags:
        return GateDecision(Verdict.TAINTED_UNREVIEWED, tuple(review_flags))

    return GateDecision(Verdict.CLEAN_USER, ())
