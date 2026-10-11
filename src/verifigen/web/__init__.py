"""Local workbench over the public QualityLoop SDK."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from ..config import ModelSettings
from ..domains.rag_review import CitationGate
from ..domains.report_review import MetricSource, ReportFactsGate, render_report
from ..domains.support import SupportSource
from ..domains.support_review import SupportFactsGate, render_support
from ..jsonutil import json_copy
from ..policy import QualityPolicy
from ..quality import QualityLoop
from ..review import Criterion, QualityBudget, QualityTask
from .limits import RequestBodyLimit

DIRECTORY = Path(__file__).parent


class CriterionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1, max_length=2000)


class RunInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenario: str = Field(default="custom", max_length=32)
    source: dict[str, Any]
    prompt: str = Field(min_length=1, max_length=32000)
    criteria: list[CriterionInput] = Field(min_length=1, max_length=20)
    output_schema: dict[str, Any]
    instructions: str = Field(default="", max_length=8000)
    fallback_text: str = Field(
        default="当前内容尚未通过校验，请稍后重试或交由人工核实。", min_length=1, max_length=1000
    )
    fallback_by_reason: dict[str, str] = Field(default_factory=dict, max_length=20)
    initial: Any = None
    generate: bool = False
    citation_gate: bool = False
    max_repair_rounds: int = Field(default=2, ge=0, le=2, strict=True)
    max_model_calls: int = Field(default=5, ge=0, le=7, strict=True)
    deadline_seconds: float = Field(default=120, gt=0, le=180)
    min_pass_score: float = Field(default=0.8, ge=0, le=1)
    max_observed_tokens: int | None = Field(default=None, gt=0, le=100000, strict=True)
    score_patience: int | None = Field(default=None, ge=1, le=3, strict=True)
    judge_history: Literal["full", "none"] = "full"
    initial_refinement: bool = False
    max_protocol_retries: int = Field(default=1, ge=0, le=1, strict=True)
    enable_thinking: bool = False
    validate_judge_quotes: bool = False

    def task(self) -> QualityTask:
        if self.scenario == "support":
            SupportSource.model_validate(self.source)
        elif self.scenario == "report":
            MetricSource.model_validate(self.source)
        if self.citation_gate:
            chunks = self.source.get("retrieved_chunks")
            if not isinstance(chunks, list) or any(
                not isinstance(c, dict) or not isinstance(c.get("chunk_id"), str) for c in chunks
            ):
                raise ValueError("引用关卡需要带 chunk_id 的 retrieved_chunks")
        return QualityTask(
            source=self.source,
            prompt=self.prompt,
            criteria=tuple(Criterion(c.id, c.description) for c in self.criteria),
            output_schema=self.output_schema,
            instructions=self.instructions,
            fallback_text=self.fallback_text,
            fallback_by_reason=self.fallback_by_reason,
            renderer=render_support
            if self.scenario == "support"
            else render_report
            if self.scenario == "report"
            else None,
        )


class Job:
    def __init__(self, payload: RunInput, model: str) -> None:
        self.id = uuid.uuid4().hex
        self.created_at = datetime.now(UTC).isoformat()
        self.payload = payload.model_dump()
        self.model = model
        self.state = "running"
        self.events: list[dict[str, Any]] = []
        self.result: dict[str, Any] | None = None
        self.future: asyncio.Task[None] | None = None
        self.changed = asyncio.Event()

    def emit(self, event: dict[str, Any]) -> None:
        self.events.append(json_copy(event))
        self.changed.set()

    def record(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "created_at": self.created_at,
            "model": self.model,
            "state": self.state,
            "input": self.payload,
            "events": self.events,
            "result": self.result,
        }


def create_app(
    *, settings: ModelSettings | None = None, run_dir: Path | None = None, stack: Any = None
) -> FastAPI:
    configured = settings or ModelSettings.from_env(Path.cwd() / ".env.local")
    destination = run_dir or Path.cwd() / "runs/web"
    jobs: dict[str, Job] = {}

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        pending = [job.future for job in jobs.values() if job.future and not job.future.done()]
        for future in pending:
            future.cancel()
        await asyncio.gather(*pending, return_exceptions=True)

    app = FastAPI(title="VerifiGen Workbench", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]", "testserver"]
    )
    app.add_middleware(RequestBodyLimit)

    @app.middleware("http")
    async def local_requests(request: Request, call_next: Any) -> Any:
        origin = request.headers.get("origin")
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            if origin and origin.rstrip("/") != str(request.base_url).rstrip("/"):
                from fastapi.responses import JSONResponse

                return JSONResponse(
                    {"detail": "Cross-origin requests are not allowed"}, status_code=403
                )
            if request.headers.get("sec-fetch-site") == "cross-site":
                from fastapi.responses import JSONResponse

                return JSONResponse(
                    {"detail": "Cross-site requests are not allowed"}, status_code=403
                )
            length = request.headers.get("content-length", "0")
            if not length.isdigit() or int(length) > 512000:
                from fastapi.responses import JSONResponse

                return JSONResponse({"detail": "Request exceeds 512 KB"}, status_code=413)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'"
        )
        return response

    def saved(identifier: str) -> dict[str, Any]:
        if not re.fullmatch(r"[a-f0-9]{32}", identifier):
            raise HTTPException(404, "Run not found")
        if identifier in jobs:
            return jobs[identifier].record()
        path = destination / f"{identifier}.json"
        if not path.exists():
            raise HTTPException(404, "Run not found")
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            if (
                not isinstance(value, dict)
                or value.get("id") != identifier
                or "events" not in value
            ):
                raise ValueError("Invalid stored run")
            return value
        except (ValueError, OSError):
            raise HTTPException(404, "Stored run is unavailable") from None

    @app.get("/api/config")
    async def configuration() -> dict[str, Any]:
        return {
            "model": configured.model,
            "configured": bool(configured.api_key or stack),
            "mode": "live",
            "max_concurrent_runs": 3,
        }

    @app.get("/api/presets")
    async def presets() -> Any:
        return json.loads((DIRECTORY / "data/presets.json").read_text(encoding="utf-8"))

    @app.get("/api/evaluations")
    async def evaluations() -> Any:
        return json.loads((DIRECTORY / "data/evaluations.json").read_text(encoding="utf-8"))

    @app.get("/api/comparison")
    async def comparison() -> Any:
        return json.loads((DIRECTORY / "data/comparison.json").read_text(encoding="utf-8"))

    def persist(job: Job) -> None:
        destination.mkdir(parents=True, exist_ok=True)
        path = destination / f"{job.id}.json"
        temporary = path.with_suffix(".tmp")
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(job.record(), handle, ensure_ascii=False)
        temporary.replace(path)

    async def execute(job: Job, payload: RunInput, task: QualityTask, agents: Any) -> None:
        try:
            loop = QualityLoop(
                generator=agents.generator,
                judge=agents.judge,
                repairer=agents.repairer,
                budget=QualityBudget(
                    max_model_calls=payload.max_model_calls,
                    max_repair_rounds=payload.max_repair_rounds,
                    deadline_seconds=payload.deadline_seconds,
                    min_pass_score=payload.min_pass_score,
                    max_observed_tokens=payload.max_observed_tokens,
                ),
                policy=QualityPolicy(score_patience=payload.score_patience),
                judge_history=payload.judge_history,
                initial_refiner=agents.generator if payload.initial_refinement else None,
                max_protocol_retries=payload.max_protocol_retries,
                gates=(
                    *((CitationGate(),) if payload.citation_gate else ()),
                    *((SupportFactsGate(),) if payload.scenario == "support" else ()),
                    *((ReportFactsGate(),) if payload.scenario == "report" else ()),
                ),
            )
            if payload.generate:
                result = await loop.run(task, on_event=job.emit)
            else:
                result = await loop.run(task, initial=payload.initial, on_event=job.emit)
            job.result = result.to_dict()
            job.state = result.status
        except asyncio.CancelledError:
            job.state = "cancelled"
        except Exception:
            job.state = "error"
            job.emit({"event": "run_error", "details": {"reason": "execution_error"}})
        finally:
            job.emit({"event": "complete", "details": {"state": job.state, "result": job.result}})
            try:
                persist(job)
            except OSError:
                job.emit({"event": "storage_error", "details": {"reason": "history_not_saved"}})

    @app.post("/api/runs", status_code=202)
    async def start(payload: RunInput) -> dict[str, str]:
        if sum(job.state == "running" for job in jobs.values()) >= 3:
            raise HTTPException(429, "Three runs are already active")
        if len(json.dumps(payload.model_dump(), ensure_ascii=False)) > 512000:
            raise HTTPException(413, "Request exceeds 512 KB")
        try:
            task = payload.task()
            agents = stack or configured.stack(
                enable_thinking=payload.enable_thinking,
                validate_judge_quotes=payload.validate_judge_quotes,
            )
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        if len(jobs) >= 100:
            oldest = next(
                (identifier for identifier, job in jobs.items() if job.state != "running"), None
            )
            if oldest:
                del jobs[oldest]
        job = Job(payload, configured.model)
        jobs[job.id] = job
        job.future = asyncio.create_task(execute(job, payload, task, agents))
        return {"id": job.id, "events_url": f"/api/runs/{job.id}/events"}

    @app.get("/api/runs/{identifier}")
    async def result(identifier: str) -> dict[str, Any]:
        return saved(identifier)

    @app.delete("/api/runs/{identifier}")
    async def delete(identifier: str) -> dict[str, str]:
        record = saved(identifier)
        if record["state"] == "running":
            raise HTTPException(409, "Cancel the active run before deleting it")
        try:
            (destination / f"{identifier}.json").unlink(missing_ok=True)
        except OSError:
            raise HTTPException(500, "Stored run could not be deleted") from None
        jobs.pop(identifier, None)
        return {"state": "deleted"}

    @app.post("/api/runs/{identifier}/cancel")
    async def cancel(identifier: str) -> dict[str, str]:
        saved(identifier)
        job = jobs.get(identifier)
        if job and job.future and job.state == "running":
            job.future.cancel()
            await asyncio.gather(job.future, return_exceptions=True)
            if job.state == "running":
                job.state = "cancelled"
                job.emit({"event": "complete", "details": {"state": job.state, "result": None}})
                persist(job)
        return {"state": saved(identifier)["state"]}

    @app.get("/api/runs/{identifier}/events")
    async def events(identifier: str, request: Request, after: int = -1) -> StreamingResponse:
        if after < -1:
            raise HTTPException(422, "Invalid event cursor")
        saved(identifier)
        last = request.headers.get("last-event-id")
        if last and last.isdigit():
            after = max(after, int(last))

        async def stream() -> AsyncIterator[str]:
            cursor = after
            while not await request.is_disconnected():
                record = saved(identifier)
                for index in range(cursor + 1, len(record["events"])):
                    yield f"id: {index}\ndata: {json.dumps(record['events'][index], ensure_ascii=False)}\n\n"
                    cursor = index
                if record["state"] != "running":
                    return
                job = jobs[identifier]
                job.changed.clear()
                try:
                    await asyncio.wait_for(job.changed.wait(), timeout=10)
                except TimeoutError:
                    yield ": heartbeat\n\n"

        return StreamingResponse(stream(), media_type="text/event-stream")

    @app.get("/api/history")
    async def history() -> list[dict[str, Any]]:
        records = {identifier: job.record() for identifier, job in jobs.items()}
        for path in sorted(
            destination.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True
        )[:100]:
            if path.stem not in records:
                if not re.fullmatch(r"[a-f0-9]{32}", path.stem):
                    continue
                try:
                    value = saved(path.stem)
                    if not all(
                        key in value for key in ("created_at", "model", "state", "input", "result")
                    ):
                        continue
                    if not isinstance(value["input"], dict) or "scenario" not in value["input"]:
                        continue
                    records[path.stem] = value
                except HTTPException:
                    continue
        return sorted(
            [
                {
                    "id": r["id"],
                    "created_at": r["created_at"],
                    "model": r["model"],
                    "state": r["state"],
                    "scenario": r["input"]["scenario"],
                    "reason": (r["result"] or {}).get("reason"),
                    "model_calls": (r["result"] or {}).get("model_calls"),
                }
                for r in records.values()
            ],
            key=lambda r: r["created_at"],
            reverse=True,
        )[:100]

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(DIRECTORY / "static/index.html")

    app.mount("/static", StaticFiles(directory=DIRECTORY / "static"), name="static")
    return app


def main() -> None:
    import uvicorn

    parser = argparse.ArgumentParser(description="Start the local VerifiGen workbench")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--env-file", type=Path, default=Path.cwd() / ".env.local")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("Port must be 1..65535")
    uvicorn.run(
        create_app(settings=ModelSettings.from_env(args.env_file)), host="127.0.0.1", port=args.port
    )
