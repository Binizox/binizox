"""Binizox 个人工具执行服务 HTTP 入口。"""

from __future__ import annotations

import os
import secrets
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException

from .contracts import ExecutionView, ToolInvocation, ToolResult
from .executor import (
    ExistingFileConflictError,
    ExecutionClaimLostError,
    ExecutionInProgressError,
    PersonalToolExecutor,
    UnsafeWorkspacePathError,
)
from .repository import ExecutionRepository, IdempotencyConflictError


def create_app() -> FastAPI:
    """按环境变量创建可测试的 FastAPI 应用。"""

    workspace_root = Path(os.getenv("BINIZOX_WORKSPACE_ROOT", ".runtime/binizox/workspace"))
    state_path = Path(os.getenv("BINIZOX_TOOL_STATE_PATH", ".runtime/binizox/tool-runner.sqlite3"))
    repository = ExecutionRepository(state_path)
    lease_seconds = int(os.getenv("BINIZOX_TOOL_LEASE_SECONDS", "60"))
    if lease_seconds < 1:
        raise RuntimeError("BINIZOX_TOOL_LEASE_SECONDS must be positive")
    executor = PersonalToolExecutor(
        workspace_root=workspace_root,
        repository=repository,
        lease_seconds=lease_seconds,
    )
    raw_service_token = os.getenv("BINIZOX_TOOL_RUNNER_TOKEN", "")
    service_token = raw_service_token.strip()
    if not service_token:
        raise RuntimeError("BINIZOX_TOOL_RUNNER_TOKEN is required")
    if raw_service_token != service_token:
        raise RuntimeError("BINIZOX_TOOL_RUNNER_TOKEN must not contain surrounding whitespace")
    if len(service_token) < 32:
        raise RuntimeError("BINIZOX_TOOL_RUNNER_TOKEN must contain at least 32 characters")
    for other_name in (
        "JWT_SECRET_KEY",
        "API_KEY_DERIVATION_SECRET",
        "SANDBOX_PROVISIONER_TOKEN",
    ):
        other_value = os.getenv(other_name, "").strip()
        if other_value and secrets.compare_digest(service_token, other_value):
            raise RuntimeError(f"BINIZOX_TOOL_RUNNER_TOKEN must be independent from {other_name}")

    application = FastAPI(title="Binizox Personal Tool Runner", version="0.1.0")
    application.state.repository = repository
    application.state.executor = executor

    def require_service_token(authorization: str | None = Header(default=None)) -> None:
        scheme, _, supplied = (authorization or "").partition(" ")
        if scheme.lower() != "bearer" or not supplied or not secrets.compare_digest(supplied, service_token):
            raise HTTPException(status_code=401, detail={"code": "invalid_service_token"})

    @application.get("/health")
    def health() -> dict:
        return {"status": "ok", "service": "binizox-personal-tool-runner"}

    @application.post("/v1/invocations", response_model=ToolResult, dependencies=[Depends(require_service_token)])
    def invoke(invocation: ToolInvocation) -> ToolResult:
        """执行白名单工具；人工确认由 Binizox LangGraph 中间件先行完成。"""

        try:
            return executor.execute(invocation)
        except IdempotencyConflictError as exc:
            raise HTTPException(status_code=409, detail={"code": "idempotency_conflict", "message": str(exc)}) from exc
        except ExecutionInProgressError as exc:
            raise HTTPException(status_code=409, detail={"code": "execution_in_progress", "message": str(exc)}) from exc
        except ExecutionClaimLostError as exc:
            raise HTTPException(status_code=409, detail={"code": "execution_claim_lost", "message": str(exc)}) from exc
        except ExistingFileConflictError as exc:
            raise HTTPException(status_code=409, detail={"code": "target_conflict", "message": str(exc)}) from exc
        except UnsafeWorkspacePathError as exc:
            raise HTTPException(status_code=422, detail={"code": "unsafe_path", "message": str(exc)}) from exc

    @application.get(
        "/v1/executions/{idempotency_key}",
        response_model=ExecutionView,
        dependencies=[Depends(require_service_token)],
    )
    def get_execution(idempotency_key: str) -> ExecutionView:
        stored = repository.get(idempotency_key)
        if stored is None:
            raise HTTPException(status_code=404, detail={"code": "execution_not_found"})
        return ExecutionView(
            idempotency_key=stored.idempotency_key,
            parameter_digest=stored.parameter_digest,
            status=stored.status,
            result=stored.result,
            error=stored.error,
            created_at=stored.created_at,
            updated_at=stored.updated_at,
        )

    return application


app = create_app()
