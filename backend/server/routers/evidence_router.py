"""Binizox 文档入库与 Evidence 检索 HTTP 边界。"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from binizox.evidence.contracts import DocumentPermission, SearchRequest
from binizox.evidence.document_service import (
    EvidenceConflict,
    EvidenceDocumentError,
    EvidenceNotFound,
    EvidencePermissionDenied,
    document_service,
)
from binizox.storage.postgres.models_business import User
from server.utils.auth_middleware import get_admin_user, get_required_user

evidence_router = APIRouter(prefix="/binizox/evidence", tags=["Binizox Evidence"])


class SearchBody(BaseModel):
    """客户端可控的检索参数；用户和租户由服务端认证上下文确定。"""

    knowledge_base_ids: list[str] = Field(min_length=1, max_length=20)
    query: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=8, ge=1, le=50)


def _raise_http(exc: EvidenceDocumentError) -> None:
    if isinstance(exc, EvidenceNotFound):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, EvidencePermissionDenied):
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if isinstance(exc, EvidenceConflict):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    raise HTTPException(status_code=422, detail=str(exc)) from exc


@evidence_router.post("/documents")
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
        permission = DocumentPermission(access_level=access_level, user_uids=json.loads(user_uids))
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
    except EvidenceDocumentError as exc:
        _raise_http(exc)


@evidence_router.get("/documents/{knowledge_base_id}/{document_id}/versions/{version}")
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
    except EvidenceDocumentError as exc:
        _raise_http(exc)


@evidence_router.post("/search")
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
    except EvidenceDocumentError as exc:
        _raise_http(exc)
