"""Binizox 文档版本、片段和权限过滤的数据访问层。"""

from __future__ import annotations

import hashlib
from typing import Any

from sqlalchemy import delete, func, select

from binizox.permissions import ResourcePermission, resolve_knowledge_base_permission
from binizox.storage.postgres.manager import pg_manager
from binizox.storage.postgres.models_business import User
from binizox.storage.postgres.models_knowledge import KnowledgeBase, KnowledgeChunk, KnowledgeFile

EVIDENCE_METADATA_KEY = "binizox_evidence"
LEGACY_EVIDENCE_METADATA_KEY = "asterdesk"


def document_file_id(*, tenant_id: str, kb_id: str, document_id: str, version: str) -> str:
    """为不可变文档版本生成稳定且满足 Binizox 长度约束的 file_id。"""

    identity = "\0".join((tenant_id, kb_id, document_id, version))
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def evidence_metadata(record: KnowledgeFile | KnowledgeChunk) -> dict[str, Any]:
    """读取当前 Evidence metadata，并兼容迁入数据库中的旧命名空间。"""

    raw = record.processing_params if isinstance(record, KnowledgeFile) else record.extraction_result
    if not isinstance(raw, dict):
        return {}
    value = raw.get(EVIDENCE_METADATA_KEY)
    if not isinstance(value, dict):
        value = raw.get(LEGACY_EVIDENCE_METADATA_KEY)
    return value if isinstance(value, dict) else {}


def document_visible_to_user(record: KnowledgeFile, user: User) -> bool:
    """在租户命中后判断文档级 ACL。"""

    metadata = evidence_metadata(record)
    if str(metadata.get("tenant_id")) != str(user.department_id):
        return False
    permission = metadata.get("permission") or {}
    access_level = permission.get("access_level")
    if access_level == "tenant":
        return True
    return access_level == "user" and str(user.uid) in set(permission.get("user_uids") or [])


class EvidenceDocumentRepository:
    """复用 Binizox 知识表并维护文档版本、发布和 ACL 不变量。"""

    async def get_knowledge_base(self, kb_id: str) -> KnowledgeBase | None:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(KnowledgeBase).where(KnowledgeBase.kb_id == kb_id))
            return result.scalar_one_or_none()

    async def get_document(self, file_id: str) -> KnowledgeFile | None:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(KnowledgeFile).where(KnowledgeFile.file_id == file_id))
            return result.scalar_one_or_none()

    async def prepare_document(self, data: dict[str, Any]) -> tuple[KnowledgeFile, bool]:
        """锁定逻辑版本并创建或重置记录，返回是否为已完成的幂等命中。"""

        file_id = str(data["file_id"])
        async with pg_manager.get_async_session_context() as session:
            await session.execute(select(func.pg_advisory_xact_lock(func.hashtext(file_id))))
            result = await session.execute(select(KnowledgeFile).where(KnowledgeFile.file_id == file_id))
            record = result.scalar_one_or_none()
            if record is not None:
                if record.content_hash != data["content_hash"]:
                    raise ValueError("同一文档版本已存在不同内容")
                if record.status == "active":
                    return record, True
                for key, value in data.items():
                    if key != "file_id":
                        setattr(record, key, value)
                record.error_message = None
                return record, False

            record = KnowledgeFile(**data)
            session.add(record)
            await session.flush()
            return record, False

    async def update_document(self, file_id: str, **values: Any) -> KnowledgeFile:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(KnowledgeFile).where(KnowledgeFile.file_id == file_id).with_for_update()
            )
            record = result.scalar_one()
            for key, value in values.items():
                setattr(record, key, value)
            await session.flush()
            return record

    async def replace_chunks(self, file_id: str, chunks: list[dict[str, Any]]) -> None:
        """在一个事务中替换单个未发布版本的全部片段。"""

        async with pg_manager.get_async_session_context() as session:
            await session.execute(delete(KnowledgeChunk).where(KnowledgeChunk.file_id == file_id))
            session.add_all(KnowledgeChunk(**chunk) for chunk in chunks)

    async def delete_chunks(self, file_id: str) -> None:
        async with pg_manager.get_async_session_context() as session:
            await session.execute(delete(KnowledgeChunk).where(KnowledgeChunk.file_id == file_id))

    async def activate_document(self, file_id: str) -> KnowledgeFile:
        """只在索引完成后发布新版本，并把同一逻辑文档的旧活动版本降级。"""

        async with pg_manager.get_async_session_context() as session:
            current_result = await session.execute(
                select(KnowledgeFile).where(KnowledgeFile.file_id == file_id).with_for_update()
            )
            current = current_result.scalar_one()
            metadata = evidence_metadata(current)
            lock_key = "|".join(
                (
                    str(metadata.get("tenant_id")),
                    current.kb_id,
                    str(metadata.get("document_id")),
                )
            )
            await session.execute(select(func.pg_advisory_xact_lock(func.hashtext(lock_key))))
            candidates = list(
                (
                    await session.execute(
                        select(KnowledgeFile).where(
                            KnowledgeFile.kb_id == current.kb_id,
                            KnowledgeFile.status == "active",
                            KnowledgeFile.file_id != current.file_id,
                        )
                    )
                )
                .scalars()
                .all()
            )
            for candidate in candidates:
                candidate_metadata = evidence_metadata(candidate)
                if str(candidate_metadata.get("tenant_id")) == str(
                    metadata.get("tenant_id")
                ) and candidate_metadata.get("document_id") == metadata.get("document_id"):
                    candidate.status = "superseded"
            current.status = "active"
            await session.flush()
            return current

    async def list_visible_active_chunks(
        self,
        *,
        user: User,
        knowledge_base_ids: list[str],
        chunk_ids: list[str] | None = None,
    ) -> list[tuple[KnowledgeFile, KnowledgeChunk]]:
        """先确定可见文档，再读取片段，避免未授权正文越过 repository 边界。"""

        normalized_ids = sorted({item.strip() for item in knowledge_base_ids if item.strip()})
        if not normalized_ids:
            return []
        async with pg_manager.get_async_session_context() as session:
            bases = list(
                (await session.execute(select(KnowledgeBase).where(KnowledgeBase.kb_id.in_(normalized_ids))))
                .scalars()
                .all()
            )
            visible_kb_ids = {
                base.kb_id for base in bases if resolve_knowledge_base_permission(user, base) != ResourcePermission.NONE
            }
            if not visible_kb_ids:
                return []

            files = list(
                (
                    await session.execute(
                        select(KnowledgeFile).where(
                            KnowledgeFile.kb_id.in_(visible_kb_ids),
                            KnowledgeFile.status == "active",
                        )
                    )
                )
                .scalars()
                .all()
            )
            visible_files = {record.file_id: record for record in files if document_visible_to_user(record, user)}
            if not visible_files:
                return []

            chunk_query = select(KnowledgeChunk).where(KnowledgeChunk.file_id.in_(visible_files))
            if chunk_ids is not None:
                normalized_chunk_ids = sorted({item.strip() for item in chunk_ids if item.strip()})
                if not normalized_chunk_ids:
                    return []
                chunk_query = chunk_query.where(KnowledgeChunk.chunk_id.in_(normalized_chunk_ids))
            chunks = list(
                (
                    await session.execute(chunk_query.order_by(KnowledgeChunk.file_id, KnowledgeChunk.chunk_index))
                )
                .scalars()
                .all()
            )
            return [(visible_files[chunk.file_id], chunk) for chunk in chunks]
