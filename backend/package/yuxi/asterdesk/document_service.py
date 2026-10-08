"""AsterDesk 文档入库、版本发布与权限过滤检索服务。"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import PurePath
from typing import Any

import httpx

from yuxi.asterdesk.contracts import (
    DocumentFormat,
    DocumentPermission,
    DocumentRef,
    Evidence,
    ParsedDocument,
    SearchRequest,
)
from yuxi.asterdesk.repository import (
    AsterDeskDocumentRepository,
    asterdesk_metadata,
    document_file_id,
    document_visible_to_user,
)
from yuxi.permissions import ResourcePermission, require_knowledge_base_permission
from yuxi.storage.minio import get_minio_client
from yuxi.storage.postgres.models_business import User
from yuxi.storage.postgres.models_knowledge import KnowledgeFile

MAX_DOCUMENT_BYTES = 25 * 1024 * 1024
DOCUMENT_BUCKET = "knowledgebases"


class AsterDeskDocumentError(RuntimeError):
    """文档管道可映射到 HTTP 的领域错误。"""


class AsterDeskNotFound(AsterDeskDocumentError):
    """资源不存在或对当前用户不可见。"""


class AsterDeskPermissionDenied(AsterDeskDocumentError):
    """当前用户没有所需权限。"""


class AsterDeskConflict(AsterDeskDocumentError):
    """不可变版本与已有内容冲突。"""


@dataclass(frozen=True)
class IngestResult:
    """上传接口返回的稳定文档投影。"""

    file_id: str
    document_id: str
    version: str
    knowledge_base_id: str
    status: str
    chunk_count: int
    errors: list[dict[str, Any]]
    idempotent_replay: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_id": self.file_id,
            "document_id": self.document_id,
            "version": self.version,
            "knowledge_base_id": self.knowledge_base_id,
            "status": self.status,
            "chunk_count": self.chunk_count,
            "errors": self.errors,
            "idempotent_replay": self.idempotent_replay,
        }


def _metadata(record: KnowledgeFile) -> dict[str, Any]:
    return asterdesk_metadata(record)


def _project(record: KnowledgeFile, *, idempotent_replay: bool = False) -> IngestResult:
    metadata = _metadata(record)
    return IngestResult(
        file_id=record.file_id,
        document_id=str(metadata.get("document_id") or ""),
        version=str(metadata.get("version") or ""),
        knowledge_base_id=record.kb_id,
        status=record.status,
        chunk_count=int(record.chunk_count or 0),
        errors=list(metadata.get("parse_errors") or []),
        idempotent_replay=idempotent_replay,
    )


def _search_terms(text: str) -> set[str]:
    normalized = text.lower()
    terms = {token for token in re.findall(r"[a-z0-9_]{2,}", normalized)}
    cjk = "".join(re.findall(r"[\u4e00-\u9fff]", normalized))
    terms.update(cjk[index : index + 2] for index in range(max(len(cjk) - 1, 0)))
    return terms


def _score(query: str, text: str) -> float:
    query_terms = _search_terms(query)
    if not query_terms:
        return 0.0
    text_terms = _search_terms(text)
    overlap = query_terms & text_terms
    phrase_bonus = 0.25 if query.strip().lower() in text.lower() else 0.0
    return round(min(1.0, len(overlap) / len(query_terms) + phrase_bonus), 6)


class AsterDeskDocumentService:
    """协调对象存储、解析 sidecar 与 Yuxi 知识表。"""

    def __init__(self, repository: AsterDeskDocumentRepository | None = None):
        self.repository = repository or AsterDeskDocumentRepository()

    async def _require_kb(self, user: User, kb_id: str, permission: ResourcePermission):
        knowledge_base = await self.repository.get_knowledge_base(kb_id)
        if knowledge_base is None:
            raise AsterDeskNotFound(f"知识库 {kb_id} 不存在")
        try:
            require_knowledge_base_permission(user, knowledge_base, permission)
        except PermissionError as exc:
            raise AsterDeskPermissionDenied("无权操作该知识库") from exc
        return knowledge_base

    async def ingest(
        self,
        *,
        user: User,
        knowledge_base_id: str,
        document_id: str,
        version: str,
        filename: str,
        data: bytes,
        permission: DocumentPermission,
        title: str | None = None,
    ) -> IngestResult:
        """同步完成一个小文档版本的上传、解析、索引和原子发布。"""

        await self._require_kb(user, knowledge_base_id, ResourcePermission.MANAGE)
        if not data:
            raise AsterDeskDocumentError("文档为空")
        if len(data) > MAX_DOCUMENT_BYTES:
            raise AsterDeskDocumentError("文档超过 25 MiB 限制")
        suffix = PurePath(filename).suffix.lower().lstrip(".")
        if suffix not in {DocumentFormat.PDF.value, DocumentFormat.DOCX.value}:
            raise AsterDeskDocumentError("仅支持 PDF 和 DOCX")
        if permission.access_level == "user" and not permission.user_uids:
            raise AsterDeskDocumentError("用户范围至少需要一个 user_uid")

        tenant_id = str(user.department_id)
        content_hash = hashlib.sha256(data).hexdigest()
        file_id = document_file_id(
            tenant_id=tenant_id,
            kb_id=knowledge_base_id,
            document_id=document_id,
            version=version,
        )
        object_prefix = f"asterdesk/{tenant_id}/{knowledge_base_id}/{document_id}/{version}"
        source_object = f"{object_prefix}/source.{suffix}"
        parsed_object = f"{object_prefix}/parsed.json"
        source_uri = f"minio://{DOCUMENT_BUCKET}/{source_object}"
        parsed_uri = f"minio://{DOCUMENT_BUCKET}/{parsed_object}"
        metadata = {
            "contract_version": 2,
            "tenant_id": tenant_id,
            "document_id": document_id,
            "version": version,
            "title": title or filename,
            "permission": permission.model_dump(mode="json"),
            "source_uri": source_uri,
            "parsed_uri": parsed_uri,
            "parse_errors": [],
        }
        try:
            record, replay = await self.repository.prepare_document(
                {
                    "file_id": file_id,
                    "kb_id": knowledge_base_id,
                    "filename": filename,
                    "original_filename": filename,
                    "file_type": suffix,
                    "path": source_object,
                    "minio_url": source_uri,
                    "markdown_file": parsed_uri,
                    "status": "uploaded",
                    "content_hash": content_hash,
                    "file_size": len(data),
                    "chunk_count": 0,
                    "content_type": ("application/pdf" if suffix == "pdf" else "application/docx"),
                    "processing_params": {"asterdesk": metadata},
                    "is_folder": False,
                    "created_by": str(user.uid),
                    "updated_by": str(user.uid),
                }
            )
        except ValueError as exc:
            raise AsterDeskConflict(str(exc)) from exc
        if replay:
            return _project(record, idempotent_replay=True)

        minio = get_minio_client()
        await minio.aupload_file(DOCUMENT_BUCKET, source_object, data, record.content_type)
        await self.repository.update_document(file_id, status="parsing", error_message=None)

        document_ref = DocumentRef(
            document_id=document_id,
            tenant_id=tenant_id,
            storage_uri=source_uri,
            format=DocumentFormat(suffix),
            version=version,
            knowledge_base_id=knowledge_base_id,
            filename=filename,
            title=title or filename,
            content_hash=content_hash,
            permission=permission,
        )
        parsed = await self._parse(document_ref, filename, data)
        metadata["parse_errors"] = [error.model_dump(mode="json") for error in parsed.errors]
        if parsed.status == "failed":
            await self.repository.delete_chunks(file_id)
            failed = await self.repository.update_document(
                file_id,
                status="parse_failed",
                processing_params={"asterdesk": metadata},
                error_message=metadata["parse_errors"][0]["message"] if metadata["parse_errors"] else "解析失败",
                chunk_count=0,
            )
            return _project(failed)

        serialized = parsed.model_dump_json(indent=2).encode("utf-8")
        await minio.aupload_file(DOCUMENT_BUCKET, parsed_object, serialized, "application/json")
        await self.repository.update_document(
            file_id,
            status="indexing",
            processing_params={"asterdesk": metadata},
            error_message=None,
        )
        try:
            chunks = self._chunks(parsed, file_id)
            if not chunks:
                raise AsterDeskDocumentError("解析结果没有可索引内容")
            await self.repository.replace_chunks(file_id, chunks)
            indexed = await self.repository.update_document(
                file_id,
                status="indexed",
                chunk_count=len(chunks),
                processing_params={"asterdesk": metadata},
            )
            active = await self.repository.activate_document(indexed.file_id)
            return _project(active)
        except Exception as exc:
            await self.repository.delete_chunks(file_id)
            failed = await self.repository.update_document(
                file_id,
                status="index_failed",
                chunk_count=0,
                error_message=str(exc)[:2000],
            )
            return _project(failed)

    async def _parse(self, document: DocumentRef, filename: str, data: bytes) -> ParsedDocument:
        # Binizox 新环境使用自己的变量名；旧 AsterDesk Compose 仍可通过
        # ASTERDESK_PARSER_URL 继续运行，避免为了品牌迁移破坏已有数据环境。
        parser_url = (
            os.getenv("BINIZOX_PARSER_URL")
            or os.getenv("ASTERDESK_PARSER_URL")
            or "http://asterdesk-parser:8090"
        ).rstrip("/")
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
                response = await client.post(
                    f"{parser_url}/v1/parse",
                    data={"document": document.model_dump_json()},
                    files={"file": (filename, data, "application/octet-stream")},
                )
                response.raise_for_status()
                return ParsedDocument.model_validate(response.json())
        except (httpx.HTTPError, ValueError) as exc:
            return ParsedDocument(
                document=document,
                status="failed",
                errors=[
                    {
                        "code": "sidecar_unavailable",
                        "message": str(exc)[:1000],
                        "recoverable": True,
                    }
                ],
            )

    @staticmethod
    def _chunks(parsed: ParsedDocument, file_id: str) -> list[dict[str, Any]]:
        chunks: list[dict[str, Any]] = []
        document = parsed.document
        common = {
            "tenant_id": document.tenant_id,
            "document_id": document.document_id,
            "version": document.version,
            "title": document.title,
            "permission": document.permission.model_dump(mode="json"),
        }
        for block in parsed.blocks:
            if not block.text.strip():
                continue
            index = len(chunks)
            location = block.location.model_dump(mode="json")
            metadata = {**common, "kind": block.kind, "heading_path": block.heading_path, "location": location}
            chunks.append(
                {
                    "chunk_id": f"{file_id}:{index}",
                    "file_id": file_id,
                    "kb_id": document.knowledge_base_id,
                    "chunk_index": index,
                    "content": block.text,
                    "start_char_pos": location.get("char_start"),
                    "end_char_pos": location.get("char_end"),
                    "extraction_result": {"asterdesk": metadata},
                }
            )
        for table in parsed.tables:
            index = len(chunks)
            content = "\n".join(" | ".join(cell for cell in row) for row in table.rows)
            location = table.location.model_dump(mode="json")
            metadata = {**common, "kind": "table", "heading_path": [], "location": location}
            chunks.append(
                {
                    "chunk_id": f"{file_id}:{index}",
                    "file_id": file_id,
                    "kb_id": document.knowledge_base_id,
                    "chunk_index": index,
                    "content": content,
                    "extraction_result": {"asterdesk": metadata},
                }
            )
        return chunks

    async def get_document(
        self,
        *,
        user: User,
        knowledge_base_id: str,
        document_id: str,
        version: str,
    ) -> IngestResult:
        await self._require_kb(user, knowledge_base_id, ResourcePermission.READ)
        file_id = document_file_id(
            tenant_id=str(user.department_id),
            kb_id=knowledge_base_id,
            document_id=document_id,
            version=version,
        )
        record = await self.repository.get_document(file_id)
        if record is None or not document_visible_to_user(record, user):
            raise AsterDeskNotFound("文档版本不存在")
        return _project(record)

    async def search(self, *, user: User, request: SearchRequest) -> list[Evidence]:
        """只对 repository 已完成权限过滤的片段评分并生成证据。"""

        if request.user_id != str(user.uid) or request.tenant_id != str(user.department_id):
            raise AsterDeskPermissionDenied("检索主体必须由服务端当前用户派生")
        candidates = await self.repository.list_visible_active_chunks(
            user=user,
            knowledge_base_ids=request.knowledge_base_ids,
        )
        ranked: list[tuple[float, Evidence]] = []
        for record, chunk in candidates:
            score = _score(request.query, chunk.content)
            if score <= 0:
                continue
            evidence = self._build_evidence(record, chunk, score=score)
            ranked.append((score, evidence))
        ranked.sort(key=lambda item: (-item[0], item[1].chunk_id))
        return [evidence for _, evidence in ranked[: request.top_k]]

    async def get_evidence_by_chunk_ids(
        self,
        *,
        user: User,
        knowledge_base_ids: list[str],
        chunk_ids: list[str],
    ) -> list[Evidence]:
        """在同一 ACL 边界内重读 Agent 提交的 Evidence 标识。"""

        requested = {item.strip() for item in chunk_ids if item.strip()}
        candidates = await self.repository.list_visible_active_chunks(
            user=user,
            knowledge_base_ids=knowledge_base_ids,
            chunk_ids=list(requested),
        )
        evidence = [self._build_evidence(record, chunk, score=1.0) for record, chunk in candidates]
        if {item.chunk_id for item in evidence} != requested:
            raise AsterDeskPermissionDenied("政策 Evidence 不存在、未发布或当前用户无权访问")
        return evidence

    @staticmethod
    def _build_evidence(record: KnowledgeFile, chunk, *, score: float) -> Evidence:
        metadata = asterdesk_metadata(chunk)
        location = metadata.get("location") or {"block_index": int(chunk.chunk_index)}
        title = metadata.get("title") or record.filename
        page = location.get("page")
        heading_path = list(metadata.get("heading_path") or [])
        anchor = f"p.{page}" if page else f"block {location.get('block_index', chunk.chunk_index)}"
        if heading_path:
            anchor = f"{anchor}, {' > '.join(heading_path)}"
        return Evidence(
            text=chunk.content,
            chunk_id=chunk.chunk_id,
            document_id=str(metadata["document_id"]),
            document_version=str(metadata["version"]),
            knowledge_base_id=chunk.kb_id,
            title=str(title),
            heading_path=heading_path,
            location=location,
            score=score,
            citation=f"[{title} {metadata['document_id']} v{metadata['version']}, {anchor}, chunk {chunk.chunk_id}]",
        )


document_service = AsterDeskDocumentService()
