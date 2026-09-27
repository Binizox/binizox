"""受控 VPN 工具适配器：执行前重验审批事实，再调用独立模拟系统。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx
from sqlalchemy import select

from yuxi.repositories.asterdesk_action_repository import AsterDeskActionRepository
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import User


class VpnAdapterError(RuntimeError):
    """可稳定分类的 VPN 工具边界错误。"""


class VpnAdapterRejected(VpnAdapterError):
    pass


class VpnAdapterConflict(VpnAdapterError):
    pass


class VpnAdapterUnknown(VpnAdapterError):
    pass


@dataclass(frozen=True)
class ApprovedVpnInvocation:
    action_request_id: str
    tenant_id: str
    parameters: dict[str, Any]
    parameter_digest: str
    idempotency_key: str


async def load_approved_invocation(action_request_id: str) -> ApprovedVpnInvocation:
    """从数据库重新构造调用；绝不相信队列消息携带的参数。"""

    async with pg_manager.get_async_session_context() as db:
        repo = AsterDeskActionRepository(db)
        action = await repo.get(action_request_id)
        decision = await repo.get_decision(action_request_id)
        if action is None or decision is None:
            raise VpnAdapterRejected("申请或审批记录不存在")
        if action.status != "approved" or decision.decision != "approved":
            raise VpnAdapterRejected("申请未获批准")
        if decision.parameter_digest != action.parameter_digest:
            raise VpnAdapterConflict("审批摘要与参数快照不一致")
        approver = (
            await db.execute(select(User).where(User.uid == decision.approver_uid, User.is_deleted == 0))
        ).scalar_one_or_none()
        if approver is None or approver.role not in {"admin", "superadmin"}:
            raise VpnAdapterRejected("审批人的执行权限已失效")
        if str(approver.uid) == action.applicant_uid:
            raise VpnAdapterRejected("申请人不能执行自己的审批")
        if approver.role != "superadmin" and str(approver.department_id) != action.tenant_id:
            raise VpnAdapterRejected("审批人的租户权限已失效")
        if not action.tenant_id or not action.idempotency_key:
            raise VpnAdapterRejected("申请缺少租户或幂等键")
        return ApprovedVpnInvocation(
            action_request_id=action.id,
            tenant_id=action.tenant_id,
            parameters=dict(action.normalized_parameters),
            parameter_digest=action.parameter_digest,
            idempotency_key=action.idempotency_key,
        )


async def execute_approved_vpn_action(action_request_id: str) -> dict[str, Any]:
    """GET-before-POST 调用模拟系统；网络不确定性不会被误报成确定失败。"""

    invocation = await load_approved_invocation(action_request_id)
    base_url = os.getenv("ASTERDESK_VPN_SIMULATOR_URL", "http://asterdesk-vpn-simulator:8091").rstrip("/")
    timeout = httpx.Timeout(float(os.getenv("ASTERDESK_VPN_TIMEOUT_SECONDS", "10")))
    headers = {
        "X-AsterDesk-Tenant": invocation.tenant_id,
        "Idempotency-Key": invocation.idempotency_key,
    }
    payload = {
        "business_request_id": invocation.action_request_id,
        "tenant_id": invocation.tenant_id,
        "parameter_digest": invocation.parameter_digest,
        "parameters": invocation.parameters,
    }
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            lookup = await client.get(
                f"{base_url}/v1/grants/by-request/{invocation.action_request_id}",
                headers=headers,
            )
            if lookup.status_code == 200:
                result = lookup.json()
                result["_asterdesk_observation_source"] = "lookup"
                return result
            if lookup.status_code != 404:
                raise VpnAdapterUnknown(f"外部结果查询返回 HTTP {lookup.status_code}")
            response = await client.post(f"{base_url}/v1/grants", headers=headers, json=payload)
            if response.status_code == 409:
                raise VpnAdapterConflict("模拟 VPN 系统报告幂等键参数冲突")
            if response.status_code == 422:
                raise VpnAdapterRejected("模拟 VPN 系统拒绝执行")
            response.raise_for_status()
            result = response.json()
            result["_asterdesk_observation_source"] = "create_response"
            return result
    except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError) as exc:
        raise VpnAdapterUnknown(f"VPN 外部结果未知: {type(exc).__name__}") from exc
    except ValueError as exc:
        raise VpnAdapterUnknown("VPN 模拟系统返回了无效 JSON") from exc
