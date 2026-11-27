import json

import pytest
from jsonschema import Draft202012Validator

from app.judge import JudgeParseError, parse_judge_output, run_judge
from tests.conftest import CONTRACTS

GOOD = {
    "summary": "Forwards pricing mail to an outside address.",
    "risk_level": "high",
    "recommended_action": "purge",
    "indicators": ["imperative forwarding directive"],
}
SCHEMA = json.loads((CONTRACTS / "judge.schema.json").read_text(encoding="utf-8"))
VALIDATOR = Draft202012Validator(SCHEMA)


def test_parses_valid_output():
    note = parse_judge_output(json.dumps(GOOD))
    assert note.risk_level == "high"


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        "",
        "[]",
        '"x"',
        json.dumps({**GOOD, "extra": 1}),
        json.dumps({**GOOD, "risk_level": "severe"}),
        json.dumps({**GOOD, "recommended_action": "ignore"}),
        json.dumps({k: v for k, v in GOOD.items() if k != "summary"}),
        json.dumps({**GOOD, "summary": "x" * 501}),
        json.dumps({**GOOD, "indicators": ["i"] * 11}),
        json.dumps({**GOOD, "indicators": ["x" * 121]}),
        json.dumps({**GOOD, "indicators": [1]}),
        "```json\n" + json.dumps(GOOD) + "\n```",
    ],
)
def test_bad_output_fails_closed(raw):
    with pytest.raises(JudgeParseError):
        parse_judge_output(raw)


@pytest.mark.parametrize(
    "doc",
    [
        GOOD,
        {**GOOD, "extra": 1},
        {**GOOD, "risk_level": "severe"},
        {**GOOD, "summary": "x" * 500},
        {**GOOD, "summary": "x" * 501},
        {**GOOD, "indicators": ["i"] * 10},
        {**GOOD, "indicators": ["i"] * 11},
    ],
)
def test_parser_agrees_with_contract_schema(doc):
    schema_ok = VALIDATOR.is_valid(doc)
    try:
        parse_judge_output(json.dumps(doc))
        parser_ok = True
    except JudgeParseError:
        parser_ok = False
    assert parser_ok == schema_ok


class FakeJudge:
    def __init__(self, reply=None, exc=None):
        self.reply, self.exc = reply, exc

    async def explain(self, *, content, rule_flags, source_snippet):
        if self.exc:
            raise self.exc
        return self.reply


async def _run(judge):
    return await run_judge(judge, content="c", rule_flags=[], source_snippet=None, timeout=1)


async def test_run_judge_done():
    res = await _run(FakeJudge(reply=json.dumps(GOOD)))
    assert res.status == "done" and res.note is not None


@pytest.mark.parametrize("judge", [FakeJudge(reply="oops"), FakeJudge(exc=RuntimeError("down"))])
async def test_run_judge_fails_closed(judge):
    res = await _run(judge)
    assert (res.status, res.note) == ("failed", None)
