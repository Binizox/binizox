"""Binizox 个人工具执行服务 HTTP 入口。"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException

from .contracts import ExecutionView, ToolInvocation, ToolResult
from .executor import (
    ExistingFileConflictError,
    PersonalToolExecutor,
    UnsafeWorkspacePathError,
)
from .repository import ExecutionRepository, IdempotencyConflictError


def create_app() -> FastAPI:
    """按环境变量创建可测试的 FastAPI 应用。"""

    workspace_root = Path(os.getenv("BINIZOX_WORKSPACE_ROOT", ".runtime/binizox/workspace"))
    state_path = Path(os.getenv("BINIZOX_TOOL_STATE_PATH", ".runtime/binizox/tool-runner.sqlite3"))
    repository = ExecutionRepository(state_path)
    executor = PersonalToolExecutor(workspace_root=workspace_root, repository=repository)

    application = FastAPI(title="Binizox Personal Tool Runner", version="0.1.0")
    application.state.repository = repository
    application.state.executor = executor

    @application.get("/health")
    def health() -> dict:
        return {"status": "ok", "service": "binizox-personal-tool-runner"}

    @application.post("/v1/invocations", response_model=ToolResult)
    def invoke(invocation: ToolInvocation) -> ToolResult:
        """执行白名单工具；人工确认由 Yuxi LangGraph 中间件先行完成。"""

        try:
            return executor.execute(invocation)
        except IdempotencyConflictError as exc:
            raise HTTPException(status_code=409, detail={"code": "idempotency_conflict", "message": str(exc)}) from exc
        except ExistingFileConflictError as exc:
            raise HTTPException(status_code=409, detail={"code": "target_conflict", "message": str(exc)}) from exc
        except UnsafeWorkspacePathError as exc:
            raise HTTPException(status_code=422, detail={"code": "unsafe_path", "message": str(exc)}) from exc

    @application.get("/v1/executions/{idempotency_key}", response_model=ExecutionView)
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
