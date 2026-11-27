"""Unit tests for the plan -> execute -> retry loop. No network, no KVM: fakes only."""

from backend.app.runner import TaskRunner
from backend.app.sandbox import ExecResult


class FakePlanner:
    def __init__(self, codes: list[str]) -> None:
        self._codes = iter(codes)
        self.calls: list[tuple[str | None, str | None]] = []

    async def write_code(self, goal, previous_code=None, previous_error=None):
        self.calls.append((previous_code, previous_error))
        return next(self._codes)


class FakeSandboxes:
    def __init__(self, results: list[ExecResult]) -> None:
        self._results = iter(results)
        self.codes_run: list[str] = []

    async def run_python(self, code: str) -> ExecResult:
        self.codes_run.append(code)
        return next(self._results)


async def test_succeeds_on_first_attempt():
    planner = FakePlanner(["print(1)\n"])
    sandboxes = FakeSandboxes([ExecResult("1\n", "", 0)])

    result = await TaskRunner(planner, sandboxes, max_attempts=3).run("print one")

    assert result.status == "succeeded"
    assert result.output == "1\n"
    assert len(result.steps) == 1


async def test_feeds_stderr_back_and_retries():
    planner = FakePlanner(["bad()\n", "print('fixed')\n"])
    sandboxes = FakeSandboxes([ExecResult("", "NameError: boom", 1), ExecResult("fixed\n", "", 0)])

    result = await TaskRunner(planner, sandboxes, max_attempts=3).run("do it")

    assert result.status == "succeeded"
    assert len(result.steps) == 2
    assert planner.calls[1] == ("bad()\n", "NameError: boom")


async def test_fails_after_max_attempts():
    planner = FakePlanner(["a\n", "b\n"])
    sandboxes = FakeSandboxes([ExecResult("", "err1", 1), ExecResult("", "err2", 2)])

    result = await TaskRunner(planner, sandboxes, max_attempts=2).run("do it")

    assert result.status == "failed"
    assert result.output is None
    assert [s.exit_code for s in result.steps] == [1, 2]


async def test_timeout_counts_as_failure_and_is_retried():
    timed_out = ExecResult("", "execution exceeded 30s and was killed", -1, timed_out=True)
    planner = FakePlanner(["while True: pass\n", "print('ok')\n"])
    sandboxes = FakeSandboxes([timed_out, ExecResult("ok\n", "", 0)])

    result = await TaskRunner(planner, sandboxes, max_attempts=3).run("do it")

    assert result.status == "succeeded"
    assert result.steps[0].timed_out is True
    assert planner.calls[1][1] == "execution exceeded 30s and was killed"


async def test_nonzero_exit_without_stderr_still_reports_a_reason():
    planner = FakePlanner(["import sys; sys.exit(3)\n", "print('ok')\n"])
    sandboxes = FakeSandboxes([ExecResult("", "", 3), ExecResult("ok\n", "", 0)])

    await TaskRunner(planner, sandboxes, max_attempts=2).run("do it")

    assert planner.calls[1][1] == "process exited with code 3"
