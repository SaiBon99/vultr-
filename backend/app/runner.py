"""Plan -> execute -> retry loop (Pattern A: sandboxed code execution)."""

from dataclasses import dataclass, field
from typing import Protocol

from .sandbox import ExecResult


class CodeWriter(Protocol):
    async def write_code(
        self,
        goal: str,
        previous_code: str | None = None,
        previous_error: str | None = None,
    ) -> str: ...


class CodeExecutor(Protocol):
    async def run_python(self, code: str) -> ExecResult: ...


@dataclass
class Step:
    attempt: int
    code: str
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool


@dataclass
class TaskResult:
    goal: str
    status: str  # "succeeded" | "failed"
    steps: list[Step] = field(default_factory=list)
    output: str | None = None


class TaskRunner:
    def __init__(self, planner: CodeWriter, sandboxes: CodeExecutor, max_attempts: int = 3):
        self.planner = planner
        self.sandboxes = sandboxes
        self.max_attempts = max_attempts

    async def run(self, goal: str) -> TaskResult:
        steps: list[Step] = []
        previous_code: str | None = None
        previous_error: str | None = None

        for attempt in range(1, self.max_attempts + 1):
            code = await self.planner.write_code(goal, previous_code, previous_error)
            result = await self.sandboxes.run_python(code)
            steps.append(
                Step(
                    attempt=attempt,
                    code=code,
                    stdout=result.stdout,
                    stderr=result.stderr,
                    exit_code=result.exit_code,
                    timed_out=result.timed_out,
                )
            )
            if result.ok:
                return TaskResult(goal, "succeeded", steps, output=result.stdout)
            previous_code = code
            previous_error = result.stderr or f"process exited with code {result.exit_code}"

        return TaskResult(goal, "failed", steps)
