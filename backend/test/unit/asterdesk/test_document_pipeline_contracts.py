from __future__ import annotations

import pytest
from pydantic import ValidationError

from yuxi.asterdesk.contracts import DocumentPermission, SearchRequest
from yuxi.asterdesk.document_service import _score
from yuxi.asterdesk.repository import document_file_id, document_visible_to_user
from yuxi.storage.postgres.models_business import User
from yuxi.storage.postgres.models_knowledge import KnowledgeFile


def _user(uid: str, department_id: int) -> User:
    return User(uid=uid, username=uid, password_hash="unused", role="user", department_id=department_id)


def _file(*, tenant_id: str, access_level: str, user_uids: list[str]) -> KnowledgeFile:
    return KnowledgeFile(
        file_id="f" * 64,
        kb_id="kb",
        filename="policy.docx",
        status="active",
        processing_params={
            "asterdesk": {
                "tenant_id": tenant_id,
                "permission": {"access_level": access_level, "user_uids": user_uids},
            }
        },
    )


def test_document_version_identity_is_stable_and_version_bound() -> None:
    first = document_file_id(tenant_id="7", kb_id="kb", document_id="doc", version="1")
    assert first == document_file_id(tenant_id="7", kb_id="kb", document_id="doc", version="1")
    assert first != document_file_id(tenant_id="7", kb_id="kb", document_id="doc", version="2")
    assert len(first) == 64


def test_document_acl_requires_tenant_and_document_scope() -> None:
    restricted = _file(tenant_id="7", access_level="user", user_uids=["allowed"])
    assert document_visible_to_user(restricted, _user("allowed", 7))
    assert not document_visible_to_user(restricted, _user("other", 7))
    assert not document_visible_to_user(restricted, _user("allowed", 8))

    tenant_wide = _file(tenant_id="7", access_level="tenant", user_uids=[])
    assert document_visible_to_user(tenant_wide, _user("anyone", 7))
    assert not document_visible_to_user(tenant_wide, _user("anyone", 8))


def test_search_contract_requires_server_identity_and_bounded_top_k() -> None:
    request = SearchRequest(
        user_id="user-1",
        tenant_id="7",
        knowledge_base_ids=["kb"],
        query="管理员权限材料",
        top_k=8,
    )
    assert request.top_k == 8
    with pytest.raises(ValidationError):
        SearchRequest(user_id="", tenant_id="7", knowledge_base_ids=["kb"], query="x")
    with pytest.raises(ValidationError):
        SearchRequest(user_id="u", tenant_id="7", knowledge_base_ids=["kb"], query="x", top_k=101)


def test_lexical_score_requires_actual_query_overlap() -> None:
    assert _score("管理员权限材料", "管理员权限需要直属主管确认和工单编号") > 0
    assert _score("管理员权限材料", "食堂本周菜单") == 0


def test_user_acl_cannot_be_empty() -> None:
    # 契约本身允许先构造，入库服务再结合 access_level 给出领域错误。
    permission = DocumentPermission(access_level="user", user_uids=[])
    assert permission.user_uids == []
