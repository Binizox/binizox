"""Binizox 个人知识检索与工作区工具。"""

from __future__ import annotations

import hashlib
import json

from langgraph.prebuilt.tool_node import ToolRuntime
from pydantic import BaseModel, Field

from binizox.agents.toolkits.registry import tool
from binizox.evidence.contracts import SearchRequest
from binizox.evidence.document_service import document_service
from binizox.personal.search_scope import resolve_knowledge_base_scope
from binizox.personal.tool_runner_client import PersonalToolRunnerError, invoke_personal_tool
from binizox.repositories.user_repository import UserRepository


class BinizoxEvidenceSearchInput(BaseModel):
    """个人 Agent 可提交的检索参数，用户身份由当前 Run 注入。"""

    query: str = Field(min_length=1, description="用户问题或需要检索的关键词")
    knowledge_base_ids: list[str] = Field(
        default_factory=list,
        max_length=100,
        description="可选知识库 ID；留空时查询当前 Agent 已启用且用户可见的全部知识库",
    )
    top_k: int = Field(default=8, ge=1, le=20)


@tool(
    category="buildin",
    tags=["Binizox", "个人知识", "Evidence"],
    display_name="检索 Binizox 个人证据",
    description="检索当前用户可见的已发布文档，返回带文档版本和来源位置的 Evidence。",
    args_schema=BinizoxEvidenceSearchInput,
)
async def search_binizox_evidence(
    query: str,
    knowledge_base_ids: list[str],
    runtime: ToolRuntime,
    top_k: int = 8,
) -> str:
    """在服务端 ACL 边界内检索当前用户可见的个人 Evidence。"""

    uid = str(getattr(runtime.context, "uid", "") or "")
    user = await UserRepository().get_by_uid(uid)
    if user is None or user.department_id is None:
        return json.dumps({"evidence": [], "error": "run_user_unavailable"}, ensure_ascii=False)
    visible_knowledge_bases = getattr(runtime.context, "_visible_knowledge_bases", [])
    effective_knowledge_base_ids = resolve_knowledge_base_scope(
        visible_knowledge_bases,
        knowledge_base_ids,
    )
    if not effective_knowledge_base_ids:
        return json.dumps({"evidence": [], "error": "no_visible_knowledge_base"}, ensure_ascii=False)
    request = SearchRequest(
        user_id=str(user.uid),
        tenant_id=str(user.department_id),
        knowledge_base_ids=effective_knowledge_base_ids,
        query=query,
        top_k=top_k,
    )
    evidence = await document_service.search(user=user, request=request)
    return json.dumps(
        {"evidence": [item.model_dump(mode="json") for item in evidence]},
        ensure_ascii=False,
    )


class SaveNoteInput(BaseModel):
    """保存个人笔记的固定参数。"""

    relative_path: str = Field(
        min_length=1,
        max_length=240,
        description="个人工作区内的相对路径，只允许 .md 或 .txt",
    )
    content: str = Field(min_length=1, max_length=1_000_000, description="需要写入的完整文本")
    source_citations: list[str] = Field(
        default_factory=list,
        max_length=100,
        description="生成笔记时实际使用的 Evidence citation",
    )


@tool(
    category="buildin",
    tags=["Binizox", "个人工作区", "需要确认"],
    display_name="保存 Binizox 个人笔记",
    description=(
        "把完整内容写入 Binizox 个人工作区。默认审批模式下，LangGraph 会先展示固定参数并等待用户确认；"
        "工具本身通过独立 HTTP 服务执行，支持幂等重放且不覆盖不同内容的已有文件。"
    ),
    args_schema=SaveNoteInput,
)
async def save_binizox_note(
    relative_path: str,
    content: str,
    source_citations: list[str],
    runtime: ToolRuntime,
) -> str:
    """把用户确认后的笔记写入受限工作区。"""

    run_id = str(getattr(runtime.context, "run_id", "") or "")
    uid = str(getattr(runtime.context, "uid", "") or "")
    tool_call_id = str(getattr(runtime, "tool_call_id", "") or "")
    if not run_id or not uid or not tool_call_id:
        return json.dumps({"status": "failed", "error": "agent_run_context_incomplete"}, ensure_ascii=False)

    # 幂等键同时绑定用户、Run 和 LangGraph tool_call，避免跨用户碰撞。
    idempotency_key = hashlib.sha256(f"{uid}:{run_id}:save_binizox_note:{tool_call_id}".encode()).hexdigest()
    payload = {
        "uid": uid,
        "run_id": run_id,
        "tool_call_id": tool_call_id,
        "tool_name": "workspace.write_note",
        "parameters": {
            "relative_path": relative_path,
            "content": content,
            "source_citations": source_citations,
        },
        "idempotency_key": idempotency_key,
    }
    try:
        result = await invoke_personal_tool(payload)
    except PersonalToolRunnerError as exc:
        return json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False)
    return json.dumps(result, ensure_ascii=False)
