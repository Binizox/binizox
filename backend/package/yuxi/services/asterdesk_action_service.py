"""AsterDesk VPN ActionRequest 创建、审批与查询用例。"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from yuxi.asterdesk.contracts import ActionRequest as ActionRequestContract
from yuxi.asterdesk.contracts import ApprovalDecision as ApprovalDecisionContract
from yuxi.asterdesk.document_service import AsterDeskPermissionDenied, document_service
from yuxi.repositories.asterdesk_action_repository import AsterDeskActionRepository
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_asterdesk import ActionRequest, ApprovalDecision
from yuxi.storage.postgres.models_business import AgentRun, User
from yuxi.utils.datetime_utils import utc_now
from yuxi.utils.hash_utils import hash_id

VPN_TOOL_NAME = "request_vpn_access"
VPN_TARGET_SYSTEM = "vpn-simulator"
VPN_PERMISSION_SCOPES = frozenset({"vpn_standard", "vpn_privileged"})
VPN_APPROVER_ROLES = frozenset({"admin", "superadmin"})


class ActionRequestError(RuntimeError):
    """可映射到稳定 HTTP 状态的 ActionRequest 领域错误。"""


class ActionNotFound(ActionRequestError):
    pass


class ActionPermissionDenied(ActionRequestError):
    pass


class ActionConflict(ActionRequestError):
    pass


def normalize_vpn_parameters(
    *,
    target_user_uid: str,
    permission_scope: str,
    valid_until: date,
    business_reason: str,
    device_asset_id: str,
    manager_approval_reference: str,
) -> dict[str, str]:
    """校验并固定最终交给 VPN 系统的参数。"""

    values = {
        "target_user_uid": target_user_uid.strip(),
        "target_system": VPN_TARGET_SYSTEM,
        "permission_scope": permission_scope.strip(),
        "valid_until": valid_until.isoformat(),
        "business_reason": business_reason.strip(),
        "device_asset_id": device_asset_id.strip(),
        "manager_approval_reference": manager_approval_reference.strip(),
    }
    missing = [key for key, value in values.items() if not value]
    if missing:
        raise ActionRequestError(f"VPN 申请材料不完整: {', '.join(missing)}")
    if values["permission_scope"] not in VPN_PERMISSION_SCOPES:
        raise ActionRequestError("不支持的 VPN 权限范围")
    if valid_until <= date.today():
        raise ActionRequestError("VPN 权限有效期必须晚于今天")
    return values


def parameter_digest(parameters: dict[str, Any]) -> str:
    payload = json.dumps(parameters, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def approval_denial_reason(record: ActionRequest, approver: User) -> tuple[str, str] | None:
    """返回审批授权失败代码和可展示原因。"""

    if str(approver.uid) == record.applicant_uid:
        return "self_approval_forbidden", "申请人不能审批自己的申请"
    if approver.role not in VPN_APPROVER_ROLES:
        return "approver_role_required", "需要管理员审批权限"
    if approver.department_id is None or str(approver.department_id) != record.tenant_id:
        return "approver_tenant_mismatch", "审批人不属于申请租户"
    return None


def _serialize_action(record: ActionRequest) -> dict[str, Any]:
    return ActionRequestContract(
        action_request_id=record.id,
        run_id=record.run_id,
        applicant_uid=record.applicant_uid,
        tenant_id=record.tenant_id,
        target_user_uid=record.target_user_uid,
        target_system=record.target_system,
        permission_scope=record.permission_scope,
        valid_until=record.valid_until,
        policy_evidence=record.policy_evidence,
        tool_name=record.tool_name,
        normalized_parameters=record.normalized_parameters,
        parameter_digest=record.parameter_digest,
        idempotency_key=record.idempotency_key,
        status=record.status,
        execution_status=record.execution_status,
        decision_by_uid=record.decision_by_uid,
        decision_reason=record.decision_reason,
        external_reference_id=record.external_reference_id,
        external_result=record.external_result,
        execution_error_code=record.execution_error_code,
        execution_error_message=record.execution_error_message,
        resume_run_id=record.resume_run_id,
        created_at=record.created_at,
        updated_at=record.updated_at,
    ).model_dump(mode="json")


async def create_vpn_action_request(
    *,
    run_id: str,
    thread_id: str,
    tool_call_id: str,
    applicant: User,
    knowledge_base_ids: list[str],
    evidence_chunk_ids: list[str],
    target_user_uid: str,
    permission_scope: str,
    valid_until: date,
    business_reason: str,
    device_asset_id: str,
    manager_approval_reference: str,
) -> dict[str, Any]:
    """固化参数和当前用户可见 Evidence；相同工具调用安全重放。"""

    if applicant.department_id is None:
        raise ActionPermissionDenied("申请人未绑定租户")
    parameters = normalize_vpn_parameters(
        target_user_uid=target_user_uid,
        permission_scope=permission_scope,
        valid_until=valid_until,
        business_reason=business_reason,
        device_asset_id=device_asset_id,
        manager_approval_reference=manager_approval_reference,
    )
    if parameters["target_user_uid"] != str(applicant.uid):
        raise ActionPermissionDenied("第三阶段只允许员工为自己申请 VPN 权限")
    try:
        evidence = await document_service.get_evidence_by_chunk_ids(
            user=applicant,
            knowledge_base_ids=knowledge_base_ids,
            chunk_ids=evidence_chunk_ids,
        )
    except AsterDeskPermissionDenied as exc:
        raise ActionPermissionDenied(str(exc)) from exc
    if not evidence:
        raise ActionPermissionDenied("VPN 申请必须绑定当前用户可访问的政策 Evidence")

    digest = parameter_digest(parameters)
    action_id = hash_id(
        "vpn-action:",
        f"{applicant.department_id}:{thread_id}:{tool_call_id}",
        length=64,
    )
    idempotency_key = f"vpn:{action_id}:{digest[:24]}"
    evidence_payload = [item.model_dump(mode="json") for item in evidence]

    async with pg_manager.get_async_session_context() as db:
        repo = AsterDeskActionRepository(db)
        existing = await repo.get(action_id)
        if existing:
            current_run = (await db.execute(select(AgentRun).where(AgentRun.id == run_id))).scalar_one_or_none()
            is_original_or_resume = bool(
                current_run
                and current_run.uid == str(applicant.uid)
                and current_run.conversation_thread_id == thread_id
                and (current_run.id == existing.run_id or current_run.created_by_run_id == existing.run_id)
            )
            if existing.parameter_digest != digest or not is_original_or_resume:
                raise ActionConflict("同一工具调用对应的 VPN 申请参数发生冲突")
            return _serialize_action(existing)

        run = (await db.execute(select(AgentRun).where(AgentRun.id == run_id))).scalar_one_or_none()
        if run is None or run.uid != str(applicant.uid) or run.conversation_thread_id != thread_id:
            raise ActionPermissionDenied("ActionRequest 必须绑定当前申请人的 AgentRun")
        target = (await db.execute(select(User).where(User.uid == parameters["target_user_uid"]))).scalar_one_or_none()
        if target is None or str(target.department_id) != str(applicant.department_id):
            raise ActionPermissionDenied("目标用户不属于当前租户")

        record = ActionRequest(
            id=action_id,
            run_id=run_id,
            applicant_uid=str(applicant.uid),
            tenant_id=str(applicant.department_id),
            target_user_uid=parameters["target_user_uid"],
            target_system=VPN_TARGET_SYSTEM,
            permission_scope=parameters["permission_scope"],
            valid_until=valid_until,
            policy_evidence=evidence_payload,
            tool_name=VPN_TOOL_NAME,
            normalized_parameters=parameters,
            parameter_digest=digest,
            idempotency_key=idempotency_key,
            status="pending",
            execution_status="not_requested",
        )
        try:
            await repo.add_action(record)
        except IntegrityError as exc:
            raise ActionConflict("当前 AgentRun 已存在 VPN 操作申请") from exc
        await repo.add_audit(
            action_id,
            "action.created",
            actor_type="applicant",
            actor_id=str(applicant.uid),
            details={"run_id": run_id, "parameter_digest": digest, "evidence_count": len(evidence_payload)},
        )
        return _serialize_action(record)


async def decide_action_request(
    *,
    action_request_id: str,
    approver: User,
    decision: ApprovalDecisionContract,
) -> tuple[dict[str, Any], bool]:
    """原子写入唯一审批决定与待执行意图。"""

    denial: tuple[type[ActionRequestError], str] | None = None
    result: tuple[dict[str, Any], bool] | None = None
    async with pg_manager.get_async_session_context() as db:
        repo = AsterDeskActionRepository(db)
        record = await repo.get(action_request_id, for_update=True)
        if record is None:
            raise ActionNotFound("操作申请不存在")

        permission_denial = approval_denial_reason(record, approver)
        if permission_denial:
            reason_code, reason = permission_denial
            await repo.add_audit(
                record.id,
                "approval.denied",
                actor_type="approver",
                actor_id=str(approver.uid),
                details={"reason_code": reason_code, "requested_decision": decision.decision},
            )
            denial = (ActionPermissionDenied, reason)
        elif record.status == "pending" and record.valid_until <= date.today():
            record.status = "expired"
            record.execution_status = "not_requested"
            await repo.add_audit(
                record.id,
                "approval.denied",
                actor_type="approver",
                actor_id=str(approver.uid),
                details={"reason_code": "requested_validity_expired", "requested_decision": decision.decision},
            )
            denial = (ActionConflict, "申请有效期已到，不能审批")
        elif decision.parameter_digest != record.parameter_digest:
            await repo.add_audit(
                record.id,
                "approval.denied",
                actor_type="approver",
                actor_id=str(approver.uid),
                details={"reason_code": "parameter_digest_mismatch", "requested_decision": decision.decision},
            )
            denial = (ActionConflict, "审批参数摘要与申请快照不一致")
        elif decision.decision == "rejected" and not (decision.reason or "").strip():
            await repo.add_audit(
                record.id,
                "approval.denied",
                actor_type="approver",
                actor_id=str(approver.uid),
                details={"reason_code": "rejection_reason_required", "requested_decision": decision.decision},
            )
            denial = (ActionRequestError, "拒绝申请时必须填写原因")
        else:
            persisted = await repo.get_decision(action_request_id)
            if record.status != "pending" or persisted is not None:
                if (
                    persisted is not None
                    and persisted.approver_uid == str(approver.uid)
                    and persisted.decision == decision.decision
                    and persisted.parameter_digest == decision.parameter_digest
                ):
                    result = (_serialize_action(record), True)
                else:
                    await repo.add_audit(
                        record.id,
                        "approval.denied",
                        actor_type="approver",
                        actor_id=str(approver.uid),
                        details={"reason_code": "decision_already_exists", "requested_decision": decision.decision},
                    )
                    denial = (ActionConflict, "该申请已经产生审批决定")
            else:
                now = utc_now()
                record.status = decision.decision
                record.decision_by_uid = str(approver.uid)
                record.decision_reason = decision.reason
                record.decided_at = now
                record.execution_status = "pending" if decision.decision == "approved" else "not_requested"
                await repo.add_decision(
                    ApprovalDecision(
                        action_request_id=record.id,
                        decision=decision.decision,
                        approver_uid=str(approver.uid),
                        approver_role=str(approver.role),
                        parameter_digest=record.parameter_digest,
                        reason=decision.reason,
                        decided_at=now,
                    )
                )
                await repo.add_audit(
                    record.id,
                    f"approval.{decision.decision}",
                    actor_type="approver",
                    actor_id=str(approver.uid),
                    details={
                        "parameter_digest": record.parameter_digest,
                        "reason": decision.reason,
                        "execution_intent": record.execution_status,
                    },
                )
                await db.refresh(record)
                result = (_serialize_action(record), False)

    if denial:
        error_type, message = denial
        raise error_type(message)
    if result is None:
        raise RuntimeError("审批事务没有产生结果")
    return result


def _can_view_action(user: User, action: ActionRequest) -> bool:
    if str(user.uid) == action.applicant_uid:
        return True
    return user.role in VPN_APPROVER_ROLES and str(user.department_id) == action.tenant_id


async def list_action_requests(
    *,
    user: User,
    statuses: tuple[str, ...],
    limit: int,
    offset: int,
) -> dict[str, Any]:
    """返回当前审批人租户内的工作台列表。"""

    if user.role not in VPN_APPROVER_ROLES or user.department_id is None:
        raise ActionPermissionDenied("需要管理员审批权限")
    async with pg_manager.get_async_session_context() as db:
        rows, total = await AsterDeskActionRepository(db).list_actions(
            tenant_id=str(user.department_id),
            statuses=statuses,
            limit=limit,
            offset=offset,
        )
        return {"items": [_serialize_action(row) for row in rows], "total": total, "limit": limit, "offset": offset}


async def get_action_request(*, action_request_id: str, user: User) -> dict[str, Any]:
    """返回申请、执行尝试和追加式审计。"""

    async with pg_manager.get_async_session_context() as db:
        repo = AsterDeskActionRepository(db)
        record = await repo.get(action_request_id)
        if record is None or not _can_view_action(user, record):
            raise ActionNotFound("操作申请不存在")
        attempts = await repo.list_attempts(record.id)
        audit = await repo.list_audit(record.id)
        result = _serialize_action(record)
        result["execution_attempts"] = [
            {
                "attempt_no": item.attempt_no,
                "worker_id": item.worker_id,
                "status": item.status,
                "idempotency_key": item.idempotency_key,
                "external_reference_id": item.external_reference_id,
                "external_observed_at": item.external_observed_at,
                "superseded_by_attempt_no": item.superseded_by_attempt_no,
                "recovery_reason": item.recovery_reason,
                "error_code": item.error_code,
                "error_message": item.error_message,
                "started_at": item.started_at,
                "finished_at": item.finished_at,
            }
            for item in attempts
        ]
        result["audit"] = [
            {
                "event_type": item.event_type,
                "actor_type": item.actor_type,
                "actor_id": item.actor_id,
                "details": item.details,
                "created_at": item.created_at,
            }
            for item in audit
        ]
        return result


async def record_action_dispatch(
    *,
    action_request_id: str,
    event_type: str,
    actor_id: str,
    details: dict[str, Any] | None = None,
) -> None:
    """追加审批提交后的队列投递事实。"""

    async with pg_manager.get_async_session_context() as db:
        repo = AsterDeskActionRepository(db)
        if await repo.get(action_request_id) is None:
            raise ActionNotFound("操作申请不存在")
        await repo.add_audit(
            action_request_id,
            event_type,
            actor_type="dispatcher",
            actor_id=actor_id,
            details=details,
        )


async def get_action_for_tool(*, action_request_id: str, applicant_uid: str) -> dict[str, Any]:
    """恢复后的 Agent 工具只读取本申请人的持久终态。"""

    async with pg_manager.get_async_session_context() as db:
        record = await AsterDeskActionRepository(db).get(action_request_id)
        if record is None or record.applicant_uid != applicant_uid:
            raise ActionNotFound("操作申请不存在")
        return _serialize_action(record)
