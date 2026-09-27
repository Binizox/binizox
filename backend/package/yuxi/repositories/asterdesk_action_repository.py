"""AsterDesk ActionRequest 的 PostgreSQL 数据访问层。"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from yuxi.storage.postgres.models_asterdesk import (
    ActionAuditEvent,
    ActionExecutionAttempt,
    ActionRequest,
    ApprovalDecision,
)


class AsterDeskActionRepository:
    """集中持有申请、审批、执行尝试和审计查询。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get(self, action_request_id: str, *, for_update: bool = False) -> ActionRequest | None:
        query = select(ActionRequest).where(ActionRequest.id == action_request_id)
        if for_update:
            query = query.with_for_update()
        return (await self.db.execute(query)).scalar_one_or_none()

    async def get_by_run(self, run_id: str) -> ActionRequest | None:
        return (
            await self.db.execute(select(ActionRequest).where(ActionRequest.run_id == run_id))
        ).scalar_one_or_none()

    async def add_action(self, action: ActionRequest) -> None:
        self.db.add(action)
        await self.db.flush()

    async def get_decision(self, action_request_id: str) -> ApprovalDecision | None:
        return (
            await self.db.execute(
                select(ApprovalDecision).where(ApprovalDecision.action_request_id == action_request_id)
            )
        ).scalar_one_or_none()

    async def add_decision(self, decision: ApprovalDecision) -> None:
        self.db.add(decision)
        await self.db.flush()

    async def next_attempt_no(self, action_request_id: str) -> int:
        value = await self.db.scalar(
            select(func.coalesce(func.max(ActionExecutionAttempt.attempt_no), 0)).where(
                ActionExecutionAttempt.action_request_id == action_request_id
            )
        )
        return int(value or 0) + 1

    async def add_attempt(self, attempt: ActionExecutionAttempt) -> None:
        self.db.add(attempt)
        await self.db.flush()

    async def get_attempt(self, action_request_id: str, attempt_no: int) -> ActionExecutionAttempt | None:
        return (
            await self.db.execute(
                select(ActionExecutionAttempt).where(
                    ActionExecutionAttempt.action_request_id == action_request_id,
                    ActionExecutionAttempt.attempt_no == attempt_no,
                )
            )
        ).scalar_one_or_none()

    async def list_attempts(self, action_request_id: str) -> list[ActionExecutionAttempt]:
        return list(
            (
                await self.db.execute(
                    select(ActionExecutionAttempt)
                    .where(ActionExecutionAttempt.action_request_id == action_request_id)
                    .order_by(ActionExecutionAttempt.attempt_no)
                )
            )
            .scalars()
            .all()
        )

    async def add_audit(
        self,
        action_request_id: str,
        event_type: str,
        *,
        actor_type: str,
        actor_id: str,
        details: dict | None = None,
    ) -> None:
        self.db.add(
            ActionAuditEvent(
                action_request_id=action_request_id,
                event_type=event_type,
                actor_type=actor_type,
                actor_id=actor_id,
                details=details or {},
            )
        )
        await self.db.flush()

    async def list_audit(self, action_request_id: str) -> list[ActionAuditEvent]:
        return list(
            (
                await self.db.execute(
                    select(ActionAuditEvent)
                    .where(ActionAuditEvent.action_request_id == action_request_id)
                    .order_by(ActionAuditEvent.id)
                )
            )
            .scalars()
            .all()
        )

    async def list_recoverable_ids(self) -> list[str]:
        result = await self.db.execute(
            select(ActionRequest.id).where(
                ActionRequest.status.in_(("approved", "rejected")),
                ActionRequest.resume_run_id.is_(None),
                ActionRequest.execution_status.in_(
                    ("not_requested", "pending", "unknown", "executing", "succeeded", "rejected", "failed")
                ),
            )
        )
        return [str(value) for value in result.scalars().all()]
