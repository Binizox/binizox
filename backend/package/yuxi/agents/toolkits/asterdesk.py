"""AsterDesk 经过服务端权限过滤的证据检索工具。"""

from __future__ import annotations

import json

from langgraph.prebuilt.tool_node import ToolRuntime
from pydantic import BaseModel, Field

from yuxi.agents.toolkits.registry import tool
from yuxi.asterdesk.contracts import SearchRequest
from yuxi.asterdesk.document_service import document_service
from yuxi.repositories.user_repository import UserRepository


class EvidenceSearchInput(BaseModel):
    """Agent 可提交的检索参数，不包含身份或租户。"""

    query: str = Field(min_length=1, description="用户原始问题或需要检索的关键词")
    knowledge_base_ids: list[str] = Field(min_length=1, description="本次检索的知识库 ID")
    top_k: int = Field(default=8, ge=1, le=20)


@tool(
    category="buildin",
    tags=["AsterDesk", "知识检索", "权限"],
    display_name="检索 AsterDesk 证据",
    description=(
        "从 AsterDesk 已发布文档中检索证据。用户和租户从当前 Agent Run 推导，"
        "返回结果已经在服务端按知识库与文档权限过滤。回答只能引用本次返回的 citation。"
    ),
    args_schema=EvidenceSearchInput,
)
async def search_asterdesk_evidence(
    query: str,
    knowledge_base_ids: list[str],
    runtime: ToolRuntime,
    top_k: int = 8,
) -> str:
    """返回当前 Run 用户可见的 Evidence JSON。"""

    uid = str(getattr(runtime.context, "uid", "") or "")
    user = await UserRepository().get_by_uid(uid)
    if user is None or user.department_id is None:
        return json.dumps({"evidence": [], "error": "run_user_unavailable"}, ensure_ascii=False)
    request = SearchRequest(
        user_id=str(user.uid),
        tenant_id=str(user.department_id),
        knowledge_base_ids=knowledge_base_ids,
        query=query,
        top_k=top_k,
    )
    evidence = await document_service.search(user=user, request=request)
    return json.dumps(
        {"evidence": [item.model_dump(mode="json") for item in evidence]},
        ensure_ascii=False,
    )
