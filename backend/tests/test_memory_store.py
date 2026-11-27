"""Pure parts of app.memory_store: verdict mapping, risk score and judge-failure escalation."""

from app import gate
from app.memory_store import DB_VERDICT, judge_failure_update, risk_score


def test_verdict_mapping_matches_schema_names():
    assert DB_VERDICT[gate.TAINTED_UNREVIEWED] == "NEEDS_REVIEW"
    assert DB_VERDICT[gate.POLICY_BLOCKED] == "BLOCKED"
    assert DB_VERDICT[gate.INCONCLUSIVE] == "FAIL_CLOSED"


def test_risk_score_sums_and_caps():
    assert risk_score("NEEDS_REVIEW", ("tainted_session",)) == 25
    flags = ("tainted_session", "imperative_directive", "external_email")
    assert risk_score("BLOCKED", flags) == 100  # 110 capped


def test_fail_closed_floor():
    assert risk_score("FAIL_CLOSED", ("missing_provenance",)) == 85


def test_judge_failure_escalates_needs_review():
    assert judge_failure_update("NEEDS_REVIEW", 25, ["tainted_session"]) == (
        "FAIL_CLOSED",
        85,
        ["tainted_session", "judge_failed"],
    )


def test_judge_failure_keeps_blocked():
    assert judge_failure_update("BLOCKED", 100, ["external_email"]) == (
        "BLOCKED",
        100,
        ["external_email", "judge_failed"],
    )


def test_judge_failure_flag_added_once():
    _, _, flags = judge_failure_update("FAIL_CLOSED", 90, ["judge_failed"])
    assert flags == ["judge_failed"]
