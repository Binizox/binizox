"""AsterDesk 文档入库与检索 HTTP 边界。"""

from __future__ import annotations

import json
import os

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from pydantic import BaseModel, Field

from server.utils.auth_middleware import get_admin_user, get_required_user
from yuxi.asterdesk.contracts import DocumentPermission, SearchRequest
from yuxi.asterdesk.contracts import ApprovalDecision as ApprovalDecisionContract
from yuxi.asterdesk.document_service import (
    AsterDeskConflict,
    AsterDeskDocumentError,
    AsterDeskNotFound,
    AsterDeskPermissionDenied,
    document_service,
)
from yuxi.storage.postgres.models_business import User
from yuxi.services.asterdesk_action_service import (
    ActionConflict,
    ActionNotFound,
    ActionPermissionDenied,
    ActionRequestError,
    decide_action_request,
    get_action_request,
)
from yuxi.services.asterdesk_action_worker import enqueue_asterdesk_action

asterdesk = APIRouter(prefix="/asterdesk", tags=["AsterDesk"])


class SearchBody(BaseModel):
    """客户端可控的检索参数；用户和租户不接受客户端输入。"""

    knowledge_base_ids: list[str] = Field(min_length=1, max_length=20)
    query: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=8, ge=1, le=50)


def _raise_http(exc: AsterDeskDocumentError) -> None:
    if isinstance(exc, AsterDeskNotFound):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, AsterDeskPermissionDenied):
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if isinstance(exc, AsterDeskConflict):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    raise HTTPException(status_code=422, detail=str(exc)) from exc


def _raise_action_http(exc: ActionRequestError) -> None:
    if isinstance(exc, ActionNotFound):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, ActionPermissionDenied):
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if isinstance(exc, ActionConflict):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    raise HTTPException(status_code=422, detail=str(exc)) from exc


@asterdesk.post("/documents")
async def upload_document(
    knowledge_base_id: str = Form(...),
    document_id: str = Form(...),
    version: str = Form(...),
    access_level: str = Form("tenant"),
    user_uids: str = Form("[]"),
    title: str | None = Form(None),
    file: UploadFile = File(...),
    current_user: User = Depends(get_admin_user),
) -> dict:
    try:
        allowed_users = json.loads(user_uids)
        permission = DocumentPermission(access_level=access_level, user_uids=allowed_users)
        data = await file.read(25 * 1024 * 1024 + 1)
        result = await document_service.ingest(
            user=current_user,
            knowledge_base_id=knowledge_base_id,
            document_id=document_id,
            version=version,
            filename=file.filename or "document",
            data=data,
            permission=permission,
            title=title,
        )
        return result.to_dict()
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="user_uids 必须是 JSON 字符串数组") from exc
    except AsterDeskDocumentError as exc:
        _raise_http(exc)


@asterdesk.get("/documents/{knowledge_base_id}/{document_id}/versions/{version}")
async def get_document_status(
    knowledge_base_id: str,
    document_id: str,
    version: str,
    current_user: User = Depends(get_required_user),
) -> dict:
    try:
        result = await document_service.get_document(
            user=current_user,
            knowledge_base_id=knowledge_base_id,
            document_id=document_id,
            version=version,
        )
        return result.to_dict()
    except AsterDeskDocumentError as exc:
        _raise_http(exc)


@asterdesk.post("/search")
async def search(body: SearchBody, current_user: User = Depends(get_required_user)) -> dict:
    request = SearchRequest(
        user_id=str(current_user.uid),
        tenant_id=str(current_user.department_id),
        knowledge_base_ids=body.knowledge_base_ids,
        query=body.query,
        top_k=body.top_k,
    )
    try:
        evidence = await document_service.search(user=current_user, request=request)
        return {"evidence": [item.model_dump(mode="json") for item in evidence]}
    except AsterDeskDocumentError as exc:
        _raise_http(exc)


@asterdesk.get("/actions/{action_request_id}")
async def read_action_request(
    action_request_id: str,
    current_user: User = Depends(get_required_user),
) -> dict:
    try:
        return await get_action_request(action_request_id=action_request_id, user=current_user)
    except ActionRequestError as exc:
        _raise_action_http(exc)


@asterdesk.post("/actions/{action_request_id}/decision")
async def decide_action(
    action_request_id: str,
    body: ApprovalDecisionContract,
    current_user: User = Depends(get_required_user),
    failure_injection: str | None = Header(default=None, alias="X-AsterDesk-Failure-Injection"),
) -> dict:
    """提交唯一审批决定；事务提交后投递执行/恢复任务。"""

    try:
        inject_after_success = failure_injection == "after-external-success"
        if inject_after_success and os.getenv("ASTERDESK_ENABLE_FAILURE_INJECTION", "0") != "1":
            raise HTTPException(status_code=403, detail="故障注入仅在隔离测试环境开放")
        action, replayed = await decide_action_request(
            action_request_id=action_request_id,
            approver=current_user,
            decision=body,
        )
        await enqueue_asterdesk_action(
            action_request_id,
            fail_after_external_success=inject_after_success,
        )
        return {"action": action, "replayed": replayed}
    except ActionRequestError as exc:
        _raise_action_http(exc)
