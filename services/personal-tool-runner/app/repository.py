"""SQLite 执行记录仓储。

工具服务拥有自己的持久化状态。Agent 或 API 不能直接修改该数据库，
只能通过 HTTP 契约提交调用或查询结果。
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


class IdempotencyConflictError(RuntimeError):
    """同一幂等键被用于不同参数。"""


@dataclass(frozen=True)
class StoredExecution:
    """数据库中的一次执行记录。"""

    idempotency_key: str
    parameter_digest: str
    status: str
    result: dict
    error: str | None
    created_at: str
    updated_at: str


class ExecutionRepository:
    """使用短事务保存工具执行状态。"""

    def __init__(self, database_path: Path):
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        """幂等地建立最小执行表。"""

        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS tool_executions (
                    idempotency_key TEXT PRIMARY KEY,
                    parameter_digest TEXT NOT NULL,
                    status TEXT NOT NULL,
                    result_json TEXT NOT NULL DEFAULT '{}',
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def reserve(self, *, idempotency_key: str, parameter_digest: str) -> tuple[StoredExecution, bool]:
        """原子占用幂等键，并返回记录及是否为本次新建。"""

        now = datetime.now(UTC).isoformat()
        connection = self._connect()
        try:
            # BEGIN IMMEDIATE 保证并发调用不会同时插入或越过摘要检查。
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM tool_executions WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            if row is not None:
                if row["parameter_digest"] != parameter_digest:
                    raise IdempotencyConflictError("同一幂等键对应的工具参数不一致")
                connection.commit()
                return self._from_row(row), False

            connection.execute(
                """
                INSERT INTO tool_executions (
                    idempotency_key, parameter_digest, status, result_json,
                    error, created_at, updated_at
                ) VALUES (?, ?, 'running', '{}', NULL, ?, ?)
                """,
                (idempotency_key, parameter_digest, now, now),
            )
            connection.commit()
            created = self.get(idempotency_key)
            if created is None:  # pragma: no cover - 数据库提交后的防御性检查
                raise RuntimeError("执行记录创建后无法读取")
            return created, True
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def complete(self, *, idempotency_key: str, result: dict) -> StoredExecution:
        """把运行中的调用结算为成功。"""

        now = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE tool_executions
                SET status = 'succeeded', result_json = ?, error = NULL, updated_at = ?
                WHERE idempotency_key = ?
                """,
                (json.dumps(result, ensure_ascii=False, sort_keys=True), now, idempotency_key),
            )
        completed = self.get(idempotency_key)
        if completed is None:  # pragma: no cover - 数据库写入后的防御性检查
            raise RuntimeError("执行成功后无法读取记录")
        return completed

    def fail(self, *, idempotency_key: str, error: str) -> StoredExecution:
        """保存确定失败，后续同键调用只回放该事实。"""

        now = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE tool_executions
                SET status = 'failed', error = ?, updated_at = ?
                WHERE idempotency_key = ?
                """,
                (error, now, idempotency_key),
            )
        failed = self.get(idempotency_key)
        if failed is None:  # pragma: no cover
            raise RuntimeError("执行失败后无法读取记录")
        return failed

    def get(self, idempotency_key: str) -> StoredExecution | None:
        """读取幂等键对应的最终或中间状态。"""

        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM tool_executions WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
        return self._from_row(row) if row is not None else None

    @staticmethod
    def _from_row(row: sqlite3.Row) -> StoredExecution:
        return StoredExecution(
            idempotency_key=row["idempotency_key"],
            parameter_digest=row["parameter_digest"],
            status=row["status"],
            result=json.loads(row["result_json"] or "{}"),
            error=row["error"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
