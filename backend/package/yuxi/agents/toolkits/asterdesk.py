"""AsterDesk 经过服务端权限过滤的证据检索工具。"""

from __future__ import annotations

import json
from datetime import date

from langgraph.prebuilt.tool_node import ToolRuntime
from langgraph.types import interrupt
from pydantic import BaseModel, Field

from yuxi.agents.toolkits.registry import tool
from yuxi.asterdesk.contracts import SearchRequest
from yuxi.asterdesk.document_service import document_service
from yuxi.repositories.user_repository import UserRepository
from yuxi.services.asterdesk_action_service import (
    ActionRequestError,
    create_vpn_action_request,
    get_action_for_tool,
)


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


class VpnAccessRequestInput(BaseModel):
    """模型只能在材料齐全且已取得本轮政策 Evidence 后创建申请。"""

    knowledge_base_ids: list[str] = Field(min_length=1, description="政策 Evidence 所在知识库 ID")
    evidence_chunk_ids: list[str] = Field(min_length=1, description="本轮检索实际返回且用于申请的 chunk_id")
    target_user_uid: str = Field(min_length=1, description="目标用户 UID；第三阶段必须是申请人本人")
    permission_scope: str = Field(description="vpn_standard 或 vpn_privileged")
    valid_until: date = Field(description="VPN 权限到期日期，YYYY-MM-DD")
    business_reason: str = Field(min_length=1, description="业务用途，不得猜测")
    device_asset_id: str = Field(min_length=1, description="受管设备资产编号，不得猜测")
    manager_approval_reference: str = Field(min_length=1, description="直属经理确认单号，不得猜测")


@tool(
    category="buildin",
    tags=["AsterDesk", "VPN", "审批"],
    display_name="提交 VPN 权限申请",
    description=(
        "把材料齐全的 VPN 申请固化为待审批 ActionRequest 并暂停当前 Run。"
        "该工具不会自行批准或执行授权；必须传入本轮服务端检索返回的 Evidence chunk_id。"
    ),
    args_schema=VpnAccessRequestInput,
)
async def request_vpn_access(
    knowledge_base_ids: list[str],
    evidence_chunk_ids: list[str],
    target_user_uid: str,
    permission_scope: str,
    valid_until: date,
    business_reason: str,
    device_asset_id: str,
    manager_approval_reference: str,
    runtime: ToolRuntime,
) -> str:
    """固化申请、LangGraph interrupt，恢复时只读取数据库终态。"""

    uid = str(getattr(runtime.context, "uid", "") or "")
    run_id = str(getattr(runtime.context, "run_id", "") or "")
    thread_id = str(getattr(runtime.context, "thread_id", "") or "")
    tool_call_id = str(getattr(runtime, "tool_call_id", "") or "")
    if not all((uid, run_id, thread_id, tool_call_id)):
        return json.dumps({"error": "agent_run_context_incomplete"}, ensure_ascii=False)
    applicant = await UserRepository().get_by_uid(uid)
    if applicant is None:
        return json.dumps({"error": "run_user_unavailable"}, ensure_ascii=False)
    try:
        action = await create_vpn_action_request(
            run_id=run_id,
            thread_id=thread_id,
            tool_call_id=tool_call_id,
            applicant=applicant,
            knowledge_base_ids=knowledge_base_ids,
            evidence_chunk_ids=evidence_chunk_ids,
            target_user_uid=target_user_uid,
            permission_scope=permission_scope,
            valid_until=valid_until,
            business_reason=business_reason,
            device_asset_id=device_asset_id,
            manager_approval_reference=manager_approval_reference,
        )
    except ActionRequestError as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)

    if action["status"] == "pending":
        interrupt(
            {
                "source": "asterdesk_vpn_action",
                "action_requests": [
                    {
                        "name": "request_vpn_access",
                        "args": action["normalized_parameters"],
                        "description": "VPN 权限申请（参数已固化，业务审批以数据库记录为准）",
                    }
                ],
                "review_configs": [
                    {
                        "action_request_id": action["action_request_id"],
                        "parameter_digest": action["parameter_digest"],
                        "allowed_decisions": ["approved", "rejected"],
                    }
                ],
            }
        )

    persisted = await get_action_for_tool(
        action_request_id=action["action_request_id"],
        applicant_uid=uid,
    )
    return json.dumps(
        {
            "action_request_id": persisted["action_request_id"],
            "approval_status": persisted["status"],
            "execution_status": persisted["execution_status"],
            "decision_reason": persisted.get("decision_reason"),
            "external_reference_id": persisted.get("external_reference_id"),
            "external_result": persisted.get("external_result"),
            "policy_evidence": persisted["policy_evidence"],
            "parameter_digest": persisted["parameter_digest"],
        },
        ensure_ascii=False,
    )
