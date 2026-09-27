from types import SimpleNamespace

from yuxi.services.asterdesk_action_service import approval_denial_reason


def _action(*, applicant_uid: str = "applicant", tenant_id: str = "10") -> SimpleNamespace:
    return SimpleNamespace(applicant_uid=applicant_uid, tenant_id=tenant_id)


def _user(*, uid: str, role: str, department_id: int | None) -> SimpleNamespace:
    return SimpleNamespace(uid=uid, role=role, department_id=department_id)


def test_approval_policy_allows_same_tenant_admin_roles():
    action = _action()

    assert approval_denial_reason(action, _user(uid="admin", role="admin", department_id=10)) is None
    assert approval_denial_reason(action, _user(uid="root", role="superadmin", department_id=10)) is None


def test_approval_policy_rejects_self_plain_user_and_cross_tenant_admin():
    action = _action()

    assert approval_denial_reason(
        action, _user(uid="applicant", role="admin", department_id=10)
    ) == ("self_approval_forbidden", "申请人不能审批自己的申请")
    assert approval_denial_reason(
        action, _user(uid="plain", role="user", department_id=10)
    ) == ("approver_role_required", "需要管理员审批权限")
    assert approval_denial_reason(
        action, _user(uid="foreign", role="admin", department_id=11)
    ) == ("approver_tenant_mismatch", "审批人不属于申请租户")
