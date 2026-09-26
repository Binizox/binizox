"""AsterDesk 跨解析、检索、工具和 Skill 边界的数据契约。"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class DocumentFormat(StrEnum):
    """允许进入解析边界的文档格式。"""

    PDF = "pdf"
    DOCX = "docx"
    MARKDOWN = "markdown"
    TEXT = "text"


class DocumentStatus(StrEnum):
    """AsterDesk 文档版本从接收到发布的状态。"""

    UPLOADED = "uploaded"
    PARSING = "parsing"
    PARSE_FAILED = "parse_failed"
    INDEXING = "indexing"
    INDEX_FAILED = "index_failed"
    INDEXED = "indexed"
    ACTIVE = "active"
    SUPERSEDED = "superseded"


class DocumentPermission(BaseModel):
    """租户内的文档可见范围；租户边界始终由服务端额外校验。"""

    access_level: Literal["tenant", "user"] = "tenant"
    user_uids: list[str] = Field(default_factory=list)


class DocumentRef(BaseModel):
    """指向一个有版本且属于知识库的原始文档。"""

    document_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    storage_uri: str = Field(min_length=1)
    format: DocumentFormat
    version: str = Field(min_length=1)
    knowledge_base_id: str = Field(min_length=1)
    filename: str = Field(min_length=1)
    title: str | None = None
    content_hash: str | None = None
    permission: DocumentPermission = Field(default_factory=DocumentPermission)


class SourceLocation(BaseModel):
    """正文块在不可变文档版本中的可复核位置。"""

    page: int | None = Field(default=None, ge=1)
    section: str | None = None
    block_index: int = Field(ge=0)
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=0)
    table_index: int | None = Field(default=None, ge=0)
    row_start: int | None = Field(default=None, ge=0)
    row_end: int | None = Field(default=None, ge=0)
    bbox: tuple[float, float, float, float] | None = None


class ParsedBlock(BaseModel):
    """解析后的正文或标题块。"""

    block_id: str = Field(min_length=1)
    kind: Literal["heading", "paragraph", "list", "code"]
    text: str
    heading_path: list[str] = Field(default_factory=list)
    location: SourceLocation


class ParsedTable(BaseModel):
    """保留行列与原文位置的表格。"""

    table_id: str = Field(min_length=1)
    rows: list[list[str]]
    location: SourceLocation


class ParseError(BaseModel):
    """允许部分成功时返回的结构化解析错误。"""

    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    recoverable: bool = False
    location: SourceLocation | None = None


class ParsedDocument(BaseModel):
    """解析服务的完整输出。"""

    document: DocumentRef
    status: Literal["succeeded", "failed"]
    blocks: list[ParsedBlock] = Field(default_factory=list)
    tables: list[ParsedTable] = Field(default_factory=list)
    errors: list[ParseError] = Field(default_factory=list)


class SearchRequest(BaseModel):
    """在后端权限边界内执行的检索请求。"""

    user_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    knowledge_base_ids: list[str] = Field(min_length=1)
    query: str = Field(min_length=1)
    top_k: int = Field(default=8, ge=1, le=100)


class Evidence(BaseModel):
    """可引用且绑定文档版本的检索证据。"""

    text: str = Field(min_length=1)
    chunk_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    document_version: str = Field(min_length=1)
    knowledge_base_id: str = Field(min_length=1)
    title: str | None = None
    heading_path: list[str] = Field(default_factory=list)
    location: SourceLocation
    score: float
    citation: str = Field(min_length=1)


class ToolSpec(BaseModel):
    """工具能力及其授权、审批和超时要求。"""

    name: str = Field(min_length=1)
    parameters_schema: dict[str, Any]
    required_permissions: list[str] = Field(default_factory=list)
    approval_required: bool = False
    timeout_seconds: int = Field(default=30, ge=1, le=86400)


class ToolInvocation(BaseModel):
    """具有稳定幂等键的单次工具调用意图。"""

    run_id: str = Field(min_length=1)
    tool_name: str = Field(min_length=1)
    arguments: dict[str, Any]
    idempotency_key: str = Field(min_length=1, max_length=256)


class ToolResult(BaseModel):
    """工具执行器返回并可供审计的结果。"""

    status: Literal["succeeded", "failed", "timed_out", "rejected"]
    output: Any | None = None
    error: str | None = None
    external_reference_id: str | None = None


class SkillManifest(BaseModel):
    """Skill 的加载、工具依赖、权限和来源清单。"""

    name: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    version: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    required_tools: list[str] = Field(default_factory=list)
    required_permissions: list[str] = Field(default_factory=list)
    source: str = Field(min_length=1)
    visibility: Literal["private", "tenant", "public"] = "private"
