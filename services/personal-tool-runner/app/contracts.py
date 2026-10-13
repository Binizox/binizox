"""个人工具服务的公开数据契约。

本模块只描述 HTTP 边界，不负责执行文件写入。将契约与执行逻辑分开，
可以让 Agent 适配器、单元测试和未来的其他工具共享同一套字段语义。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class WriteNoteParameters(BaseModel):
    """写入个人工作区笔记所需的固定参数。"""

    relative_path: str = Field(
        min_length=1,
        max_length=240,
        description="相对个人工作区的 Markdown 或文本文件路径",
    )
    content: str = Field(min_length=1, max_length=1_000_000, description="需要写入的完整文本")
    source_citations: list[str] = Field(
        default_factory=list,
        max_length=100,
        description="生成内容时使用的 Evidence 引用；工具服务仅原样留存",
    )


class ToolInvocation(BaseModel):
    """由 Binizox worker 提交给独立工具服务的调用。"""

    uid: str = Field(min_length=1, max_length=256)
    run_id: str = Field(min_length=1, max_length=128)
    tool_call_id: str = Field(min_length=1, max_length=256)
    tool_name: Literal["workspace.write_note"]
    parameters: WriteNoteParameters
    idempotency_key: str = Field(min_length=8, max_length=200)


class ToolResult(BaseModel):
    """可持久化、可安全重放的工具执行结果。"""

    status: Literal["succeeded", "failed"]
    external_reference_id: str | None = None
    result: dict = Field(default_factory=dict)
    error: str | None = None
    idempotent_replay: bool = False


class ExecutionView(BaseModel):
    """按幂等键查询到的持久化执行事实。"""

    idempotency_key: str
    parameter_digest: str
    status: Literal["running", "succeeded", "failed"]
    result: dict = Field(default_factory=dict)
    error: str | None = None
    created_at: str
    updated_at: str
