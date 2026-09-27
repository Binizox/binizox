"""AsterDesk 审批后动作的可恢复 ARQ worker。"""

from __future__ import annotations

import os
import uuid
from datetime import timedelta
from typing import Any

from arq.worker import Retry, RetryJob
from fastapi import HTTPException

from yuxi.repositories.asterdesk_action_repository import AsterDeskActionRepository
from yuxi.services.agent_run_service import create_agent_run_view
from yuxi.services.asterdesk_vpn_adapter import (
    VpnAdapterConflict,
    VpnAdapterRejected,
    VpnAdapterUnknown,
    execute_approved_vpn_action,
)
from yuxi.services.run_queue_service import get_arq_pool
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_asterdesk import ActionExecutionAttempt
from yuxi.storage.postgres.models_business import AgentRun
from yuxi.utils.datetime_utils import utc_now
from yuxi.utils.hash_utils import hash_id
from yuxi.utils.logging_config import logger

ACTION_LEASE_SECONDS = int(os.getenv("ASTERDESK_ACTION_LEASE_SECONDS", "120"))


async def enqueue_asterdesk_action(
    action_request_id: str,
    *,
    dispatch_id: str | None = None,
    fail_after_external_success: bool = False,
) -> None:
    """只投递申请 ID；执行参数始终回源 PostgreSQL。"""

    queue = await get_arq_pool()
    suffix = dispatch_id or uuid.uuid4().hex
    await queue.enqueue_job(
        "process_asterdesk_action",
        action_request_id,
        fail_after_external_success,
        _job_id=f"asterdesk-action:{action_request_id}:{suffix}",
    )


async def recover_asterdesk_actions() -> list[str]:
    """扫描批准/拒绝但尚未恢复原 Run 的持久意图。"""

    async with pg_manager.get_async_session_context() as db:
        ids = await AsterDeskActionRepository(db).list_recoverable_ids()
    for action_id in ids:
        try:
            await enqueue_asterdesk_action(action_id, dispatch_id=f"recovery-{uuid.uuid4().hex}")
            async with pg_manager.get_async_session_context() as db:
                await AsterDeskActionRepository(db).add_audit(
                    action_id,
                    "dispatch.recovered",
                    actor_type="dispatcher",
                    actor_id="asterdesk-reconciliation",
                    details={},
                )
        except Exception as exc:
            logger.warning(
                "Action recovery dispatch deferred: action={} type={}",
                action_id,
                type(exc).__name__,
            )
    return ids


async def _claim(action_request_id: str, worker_id: str) -> tuple[str, int | None]:
    """锁定申请并登记一次尝试；返回审批状态和尝试序号。"""

    now = utc_now()
    async with pg_manager.get_async_session_context() as db:
        repo = AsterDeskActionRepository(db)
        action = await repo.get(action_request_id, for_update=True)
        if action is None:
            return "missing", None
        if action.resume_run_id:
            return "resumed", None
        if action.status in {"rejected", "expired"}:
            return action.status, None
        if action.status != "approved":
            return "pending_approval", None
        if action.execution_status == "succeeded":
            return "succeeded", None
        if action.execution_status in {"rejected", "failed"}:
            return "execution_terminal", None
        if (
            action.execution_status == "executing"
            and action.execution_lease_expires_at is not None
            and action.execution_lease_expires_at > now
        ):
            return "leased", None

        attempt_no = await repo.next_attempt_no(action.id)
        prior = await repo.get_running_attempt(action.id)
        recovery_reason = "initial_dispatch"
        if action.execution_status == "unknown":
            recovery_reason = "retry_unknown_result"
        elif prior is not None:
            recovery_reason = f"takeover_attempt:{prior.attempt_no}"
            prior.status = "superseded"
            prior.finished_at = now
            prior.error_code = "execution_lease_expired"
            prior.error_message = "执行 lease 到期，由新 attempt 接管"
            prior.recovery_reason = "execution_lease_expired"
            prior.superseded_by_attempt_no = attempt_no
            await repo.add_audit(
                action.id,
                "execution.attempt.superseded",
                actor_type="worker",
                actor_id=worker_id,
                details={
                    "attempt_no": prior.attempt_no,
                    "superseded_by_attempt_no": attempt_no,
                    "reason": "execution_lease_expired",
                    "external_reference_id": prior.external_reference_id,
                },
            )
        elif action.execution_status == "executing":
            recovery_reason = "orphaned_execution_lease"
        action.execution_status = "executing"
        action.execution_worker_id = worker_id
        action.execution_lease_expires_at = now + timedelta(seconds=ACTION_LEASE_SECONDS)
        action.execution_error_code = None
        action.execution_error_message = None
        await repo.add_attempt(
            ActionExecutionAttempt(
                action_request_id=action.id,
                attempt_no=attempt_no,
                worker_id=worker_id,
                idempotency_key=action.idempotency_key,
                status="running",
                recovery_reason=recovery_reason,
            )
        )
        await repo.add_audit(
            action.id,
            "execution.attempt.started",
            actor_type="worker",
            actor_id=worker_id,
            details={
                "attempt_no": attempt_no,
                "idempotency_key": action.idempotency_key,
                "recovery_reason": recovery_reason,
            },
        )
        return "execute", attempt_no


async def _record_external_observation(
    action_request_id: str,
    attempt_no: int,
    result: dict[str, Any],
) -> None:
    """在 action 终态前持久化外部结果观察事实。"""

    async with pg_manager.get_async_session_context() as db:
        repo = AsterDeskActionRepository(db)
        attempt = await repo.get_attempt(action_request_id, attempt_no)
        if attempt is None:
            return
        external_reference_id = str(result.get("grant_id") or "") or None
        attempt.external_reference_id = external_reference_id
        attempt.external_observed_at = utc_now()
        await repo.add_audit(
            action_request_id,
            "execution.external.observed",
            actor_type="worker",
            actor_id=attempt.worker_id,
            details={
                "attempt_no": attempt_no,
                "external_reference_id": external_reference_id,
                "observation_source": result.get("_asterdesk_observation_source", "unknown"),
            },
        )


async def _finish_attempt(
    action_request_id: str,
    attempt_no: int,
    *,
    status: str,
    result: dict[str, Any] | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
) -> None:
    async with pg_manager.get_async_session_context() as db:
        repo = AsterDeskActionRepository(db)
        action = await repo.get(action_request_id, for_update=True)
        attempt = await repo.get_attempt(action_request_id, attempt_no)
        if action is None or attempt is None:
            return
        if action.execution_status == "succeeded":
            return
        if attempt.status != "running" or action.execution_worker_id != attempt.worker_id:
            await repo.add_audit(
                action.id,
                "execution.attempt.late_result_ignored",
                actor_type="worker",
                actor_id=attempt.worker_id,
                details={"attempt_no": attempt_no, "attempt_status": attempt.status},
            )
            return
        attempt.status = status
        attempt.finished_at = utc_now()
        attempt.error_code = error_code
        attempt.error_message = error_message
        action.execution_worker_id = None
        action.execution_lease_expires_at = None
        action.execution_error_code = error_code
        action.execution_error_message = error_message
        if status == "succeeded":
            persisted_result = {
                key: value for key, value in (result or {}).items() if not key.startswith("_asterdesk_")
            }
            action.execution_status = "succeeded"
            action.external_result = persisted_result
            action.external_reference_id = str(persisted_result.get("grant_id") or "") or None
            attempt.external_reference_id = action.external_reference_id
        elif status in {"rejected", "conflict"}:
            action.execution_status = "rejected"
        else:
            action.execution_status = "unknown"
        await repo.add_audit(
            action.id,
            f"execution.{status}",
            actor_type="worker",
            actor_id=attempt.worker_id,
            details={
                "attempt_no": attempt_no,
                "external_reference_id": action.external_reference_id,
                "error_code": error_code,
            },
        )


async def _resume_original_run(action_request_id: str) -> str | None:
    """通过 Yuxi 原生 resume Run 恢复同一 LangGraph checkpoint。"""

    async with pg_manager.get_async_session_context() as db:
        repo = AsterDeskActionRepository(db)
        action = await repo.get(action_request_id)
        if action is None or action.resume_run_id:
            return action.resume_run_id if action else None
        parent = await db.get(AgentRun, action.run_id)
        if parent is None:
            return None
        if parent.status != "interrupted":
            raise RetryJob()
        try:
            response = await create_agent_run_view(
                input_message=None,
                agent_slug=parent.agent_slug,
                thread_id=parent.conversation_thread_id,
                meta={"request_id": hash_id("action-resume:", action.id, length=64)},
                current_uid=action.applicant_uid,
                db=db,
                resume={"action_request_id": action.id, "source": "asterdesk_action_worker"},
                created_by_run_id=parent.id,
                source=parent.source,
                channel=parent.channel,
                external_id=parent.external_id,
                origin_metadata=parent.origin_metadata or {},
            )
        except HTTPException as exc:
            logger.warning("Action resume deferred: action={} detail={}", action.id, exc.detail)
            raise RetryJob() from exc
        resume_run_id = str(response["run_id"])

    async with pg_manager.get_async_session_context() as db:
        repo = AsterDeskActionRepository(db)
        action = await repo.get(action_request_id, for_update=True)
        if action is not None and not action.resume_run_id:
            action.resume_run_id = resume_run_id
            await repo.add_audit(
                action.id,
                "run.resume.created",
                actor_type="worker",
                actor_id="asterdesk-action-worker",
                details={"resume_run_id": resume_run_id},
            )
    return resume_run_id


async def process_asterdesk_action(
    ctx: dict,
    action_request_id: str,
    fail_after_external_success: bool = False,
) -> None:
    """执行或恢复一个持久申请；重复投递仍只产生一个外部授权。"""

    worker_id = f"{ctx.get('worker_id', 'worker')}:{ctx.get('job_try', 1)}:{uuid.uuid4().hex[:8]}"
    disposition, attempt_no = await _claim(action_request_id, worker_id)
    if disposition in {"missing", "resumed", "pending_approval"}:
        return
    if disposition == "leased":
        raise RetryJob()
    if disposition in {"rejected", "expired", "succeeded", "execution_terminal"}:
        await _resume_original_run(action_request_id)
        return
    if attempt_no is None:
        return

    try:
        result = await execute_approved_vpn_action(action_request_id)
        await _record_external_observation(action_request_id, attempt_no, result)
        failure_injection_enabled = os.getenv("ASTERDESK_ENABLE_FAILURE_INJECTION", "0") == "1"
        if fail_after_external_success and failure_injection_enabled and int(ctx.get("job_try", 1)) == 1:
            # 故障注入点：外部已经提交，本地尚未写入 succeeded。
            raise Retry(defer=ACTION_LEASE_SECONDS + 1)
        await _finish_attempt(action_request_id, attempt_no, status="succeeded", result=result)
    except VpnAdapterRejected as exc:
        await _finish_attempt(
            action_request_id,
            attempt_no,
            status="rejected",
            error_code="external_rejected",
            error_message=str(exc),
        )
    except VpnAdapterConflict as exc:
        await _finish_attempt(
            action_request_id,
            attempt_no,
            status="conflict",
            error_code="idempotency_conflict",
            error_message=str(exc),
        )
    except VpnAdapterUnknown as exc:
        await _finish_attempt(
            action_request_id,
            attempt_no,
            status="unknown",
            error_code="external_result_unknown",
            error_message=str(exc),
        )
        raise RetryJob() from exc

    await _resume_original_run(action_request_id)
