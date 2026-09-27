"""AsterDesk 审批、执行和审计业务表。"""

from sqlalchemy import Column, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func

from yuxi.storage.postgres.models_business import Base, JSON_VALUE


class ActionRequest(Base):
    """绑定 AgentRun 的不可变 VPN 操作申请。"""

    __tablename__ = "asterdesk_action_requests"

    id = Column(String(64), primary_key=True)
    run_id = Column(String(64), ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, unique=True)
    applicant_uid = Column(String(64), ForeignKey("users.uid"), nullable=False, index=True)
    tenant_id = Column(String(64), nullable=False, index=True)
    target_user_uid = Column(String(64), ForeignKey("users.uid"), nullable=False)
    target_system = Column(String(64), nullable=False)
    permission_scope = Column(String(128), nullable=False)
    valid_until = Column(Date, nullable=False)
    policy_evidence = Column(JSON_VALUE, nullable=False)
    tool_name = Column(String(128), nullable=False)
    normalized_parameters = Column(JSON_VALUE, nullable=False)
    parameter_digest = Column(String(64), nullable=False)
    idempotency_key = Column(String(128), nullable=False, unique=True)
    status = Column(String(32), nullable=False, default="pending", index=True)
    execution_status = Column(String(32), nullable=False, default="not_requested", index=True)
    decision_by_uid = Column(String(64), ForeignKey("users.uid"))
    decision_reason = Column(Text)
    decided_at = Column(DateTime(timezone=True))
    external_reference_id = Column(String(128))
    external_result = Column(JSON_VALUE)
    execution_error_code = Column(String(64))
    execution_error_message = Column(Text)
    execution_worker_id = Column(String(128))
    execution_lease_expires_at = Column(DateTime(timezone=True))
    resume_run_id = Column(String(64), ForeignKey("agent_runs.id", ondelete="SET NULL"), unique=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class ApprovalDecision(Base):
    """ActionRequest 唯一且绑定参数摘要的审批决定。"""

    __tablename__ = "asterdesk_approval_decisions"
    __table_args__ = (UniqueConstraint("action_request_id", name="uq_asterdesk_approval_action"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    action_request_id = Column(
        String(64), ForeignKey("asterdesk_action_requests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    decision = Column(String(16), nullable=False)
    approver_uid = Column(String(64), ForeignKey("users.uid"), nullable=False)
    approver_role = Column(String(32), nullable=False)
    parameter_digest = Column(String(64), nullable=False)
    reason = Column(Text)
    decided_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ActionExecutionAttempt(Base):
    """一次可审计的 worker 外部执行尝试。"""

    __tablename__ = "asterdesk_action_execution_attempts"
    __table_args__ = (
        UniqueConstraint("action_request_id", "attempt_no", name="uq_asterdesk_action_attempt"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    action_request_id = Column(
        String(64), ForeignKey("asterdesk_action_requests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    attempt_no = Column(Integer, nullable=False)
    worker_id = Column(String(128), nullable=False)
    idempotency_key = Column(String(128), nullable=False)
    status = Column(String(32), nullable=False)
    external_reference_id = Column(String(128))
    external_observed_at = Column(DateTime(timezone=True))
    superseded_by_attempt_no = Column(Integer)
    recovery_reason = Column(String(128))
    error_code = Column(String(64))
    error_message = Column(Text)
    started_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    finished_at = Column(DateTime(timezone=True))


class ActionAuditEvent(Base):
    """申请、审批、执行与恢复的追加式审计事件。"""

    __tablename__ = "asterdesk_action_audit_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    action_request_id = Column(
        String(64), ForeignKey("asterdesk_action_requests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type = Column(String(64), nullable=False, index=True)
    actor_type = Column(String(32), nullable=False)
    actor_id = Column(String(128), nullable=False)
    details = Column(JSON_VALUE, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


Index(
    "ix_asterdesk_action_recovery",
    ActionRequest.status,
    ActionRequest.execution_status,
    ActionRequest.updated_at,
)
