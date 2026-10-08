"""受限个人文件工具的执行逻辑。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath

from .contracts import ToolInvocation, ToolResult
from .repository import ExecutionRepository, IdempotencyConflictError, StoredExecution


class UnsafeWorkspacePathError(ValueError):
    """工具参数试图越过个人工作区。"""


class ExistingFileConflictError(RuntimeError):
    """目标文件已经存在，但内容与本次调用不同。"""


def canonical_digest(invocation: ToolInvocation) -> str:
    """对真正影响外部副作用的参数计算稳定摘要。"""

    payload = {
        "tool_name": invocation.tool_name,
        "parameters": invocation.parameters.model_dump(mode="json"),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


class PersonalToolExecutor:
    """仅在固定工作区内执行白名单工具。"""

    def __init__(self, *, workspace_root: Path, repository: ExecutionRepository):
        self.workspace_root = workspace_root.resolve()
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        self.repository = repository

    def execute(self, invocation: ToolInvocation) -> ToolResult:
        """执行或安全回放一次写笔记调用。"""

        digest = canonical_digest(invocation)
        stored, created = self.repository.reserve(
            idempotency_key=invocation.idempotency_key,
            parameter_digest=digest,
        )
        if not created and stored.status in {"succeeded", "failed"}:
            return self._to_result(stored, replay=True)

        try:
            result = self._write_note(invocation)
            stored = self.repository.complete(
                idempotency_key=invocation.idempotency_key,
                result=result,
            )
            return self._to_result(stored, replay=not created)
        except (UnsafeWorkspacePathError, ExistingFileConflictError, OSError) as exc:
            self.repository.fail(idempotency_key=invocation.idempotency_key, error=str(exc))
            raise

    def _write_note(self, invocation: ToolInvocation) -> dict:
        parameters = invocation.parameters
        target = self._resolve_relative_path(parameters.relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)

        if target.exists():
            # worker 在文件写成功、数据库尚未记成功时崩溃，恢复后会走到这里。
            # 内容一致代表同一次副作用已经发生，可直接确认而不重复覆盖。
            if target.read_text(encoding="utf-8") != parameters.content:
                raise ExistingFileConflictError("目标文件已存在且内容不同，拒绝覆盖")
        else:
            # x 模式提供操作系统级的“不覆盖”保证，并发请求也不能互相覆盖。
            try:
                with target.open("x", encoding="utf-8", newline="\n") as handle:
                    handle.write(parameters.content)
            except FileExistsError:
                # 两个同键请求可能在 reserve 后并发到达。另一个请求若已经写入
                # 完全相同的内容，本请求只确认该事实；不同内容仍然拒绝覆盖。
                if target.read_text(encoding="utf-8") != parameters.content:
                    raise ExistingFileConflictError("并发创建的目标文件内容不同，拒绝覆盖") from None

        return {
            "relative_path": target.relative_to(self.workspace_root).as_posix(),
            "size_bytes": target.stat().st_size,
            "content_sha256": hashlib.sha256(parameters.content.encode()).hexdigest(),
            "source_citations": parameters.source_citations,
        }

    def _resolve_relative_path(self, raw_path: str) -> Path:
        normalized = PurePosixPath(raw_path.strip().replace("\\", "/"))
        if normalized.is_absolute() or ".." in normalized.parts or not normalized.parts:
            raise UnsafeWorkspacePathError("文件路径必须是工作区内不含跳转的相对路径")
        if normalized.suffix.lower() not in {".md", ".txt"}:
            raise UnsafeWorkspacePathError("第一版只允许写入 .md 或 .txt 文件")

        target = (self.workspace_root / Path(*normalized.parts)).resolve()
        if not target.is_relative_to(self.workspace_root):
            raise UnsafeWorkspacePathError("目标路径超出个人工作区")
        return target

    @staticmethod
    def _to_result(stored: StoredExecution, *, replay: bool) -> ToolResult:
        reference = stored.result.get("relative_path") if stored.result else None
        return ToolResult(
            status="succeeded" if stored.status == "succeeded" else "failed",
            external_reference_id=reference,
            result=stored.result,
            error=stored.error,
            idempotent_replay=replay,
        )


__all__ = [
    "ExistingFileConflictError",
    "IdempotencyConflictError",
    "PersonalToolExecutor",
    "UnsafeWorkspacePathError",
    "canonical_digest",
]
