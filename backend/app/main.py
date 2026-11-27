"""FastAPI control layer: accepts a goal, plans, dispatches to a sandbox, returns verifiable output."""

from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from .config import load_settings
from .memory.proxy import router as memory_router
from .planner import Planner
from .runner import TaskRunner
from .sandbox import SandboxRunner

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"

app = FastAPI(title="Agent Sandbox Runner")
app.include_router(memory_router)
_tasks: dict[str, dict] = {}
_runner: TaskRunner | None = None


def get_runner() -> TaskRunner:
    global _runner
    if _runner is None:
        settings = load_settings()
        if not settings.inference_api_key or not settings.inference_model:
            raise HTTPException(
                status_code=500,
                detail="VULTR_INFERENCE_API_KEY and VULTR_INFERENCE_MODEL must be set (see .env.example)",
            )
        planner = Planner(
            AsyncOpenAI(base_url=settings.inference_base_url, api_key=settings.inference_api_key),
            settings.inference_model,
        )
        sandboxes = SandboxRunner(
            image=settings.sandbox_image,
            cpus=settings.sandbox_cpus,
            memory_mib=settings.sandbox_memory_mib,
            max_duration_s=settings.sandbox_max_duration_s,
            exec_timeout_s=settings.sandbox_exec_timeout_s,
        )
        _runner = TaskRunner(planner, sandboxes, max_attempts=settings.max_attempts)
    return _runner


class TaskRequest(BaseModel):
    goal: str = Field(min_length=3, max_length=2000)


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


@app.post("/tasks")
async def create_task(request: TaskRequest) -> dict:
    task_id = uuid4().hex[:12]
    _tasks[task_id] = {"id": task_id, "status": "running", "goal": request.goal, "steps": []}
    result = await get_runner().run(request.goal)
    _tasks[task_id] = {"id": task_id, **asdict(result)}
    return _tasks[task_id]


@app.get("/tasks/{task_id}")
def get_task(task_id: str) -> dict:
    if task_id not in _tasks:
        raise HTTPException(status_code=404, detail="unknown task")
    return _tasks[task_id]


@app.get("/")
def index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
