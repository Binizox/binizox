"""受限个人文件工具的执行逻辑。"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from pathlib import Path, PurePosixPath

from .contracts import ToolInvocation, ToolResult
from .repository import (
    ExecutionClaimLostError,
    ExecutionInProgressError,
    ExecutionRepository,
    IdempotencyConflictError,
    StoredExecution,
)


class UnsafeWorkspacePathError(ValueError):
    """工具参数试图越过个人工作区。"""


class ExistingFileConflictError(RuntimeError):
    """目标文件已经存在，但内容与本次调用不同。"""


def canonical_digest(invocation: ToolInvocation) -> str:
    """对真正影响外部副作用的参数计算稳定摘要。"""

    payload = {
        "uid": invocation.uid,
        "run_id": invocation.run_id,
        "tool_call_id": invocation.tool_call_id,
        "tool_name": invocation.tool_name,
        "parameters": invocation.parameters.model_dump(mode="json"),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


class PersonalToolExecutor:
    """仅在固定工作区内执行白名单工具。"""

    def __init__(self, *, workspace_root: Path, repository: ExecutionRepository, lease_seconds: int = 60):
        self.workspace_root = workspace_root.resolve()
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        self.repository = repository
        self.lease_seconds = lease_seconds

    def execute(self, invocation: ToolInvocation) -> ToolResult:
        """执行或安全回放一次写笔记调用。"""

        digest = canonical_digest(invocation)
        reservation = self.repository.reserve(
            idempotency_key=invocation.idempotency_key,
            parameter_digest=digest,
            lease_seconds=self.lease_seconds,
        )
        if reservation.disposition == "terminal":
            return self._to_result(reservation.execution, replay=True)

        claim_token = reservation.claim_token
        if claim_token is None:  # pragma: no cover - repository 契约防御
            raise ExecutionClaimLostError("执行租约缺少所有权令牌")

        try:
            result = self._write_note(invocation)
            stored = self.repository.complete(
                idempotency_key=invocation.idempotency_key,
                claim_token=claim_token,
                result=result,
            )
            return self._to_result(stored, replay=reservation.disposition == "recovered")
        except (UnsafeWorkspacePathError, ExistingFileConflictError, OSError) as exc:
            self.repository.fail(
                idempotency_key=invocation.idempotency_key,
                claim_token=claim_token,
                error=str(exc),
            )
            raise

    def _write_note(self, invocation: ToolInvocation) -> dict:
        parameters = invocation.parameters
        relative_path = self._normalize_relative_path(parameters.relative_path)
        if self._supports_secure_dir_fd():
            size_bytes = self._write_note_posix(invocation.uid, relative_path, parameters.content)
        else:
            size_bytes = self._write_note_portable(invocation.uid, relative_path, parameters.content)

        return {
            "relative_path": relative_path.as_posix(),
            "workspace_uid": self._workspace_uid_dirname(invocation.uid),
            "size_bytes": size_bytes,
            "content_sha256": hashlib.sha256(parameters.content.encode()).hexdigest(),
            "source_citations": parameters.source_citations,
        }

    @staticmethod
    def _workspace_uid_dirname(uid: str) -> str:
        """与主工程 workspace_uid_dirname 保持相同的文件系统映射。"""

        value = str(uid or "").strip()
        if not value:
            raise UnsafeWorkspacePathError("用户身份不能为空")
        if re.fullmatch(r"[A-Za-z0-9_-]+", value):
            return value
        return f"uid-{hashlib.sha256(value.encode('utf-8')).hexdigest()}"

    @staticmethod
    def _normalize_relative_path(raw_path: str) -> PurePosixPath:
        normalized = PurePosixPath(raw_path.strip().replace("\\", "/"))
        if normalized.is_absolute() or ".." in normalized.parts or not normalized.parts:
            raise UnsafeWorkspacePathError("文件路径必须是工作区内不含跳转的相对路径")
        if normalized.suffix.lower() not in {".md", ".txt"}:
            raise UnsafeWorkspacePathError("第一版只允许写入 .md 或 .txt 文件")
        return normalized

    @staticmethod
    def _supports_secure_dir_fd() -> bool:
        """生产 Linux 必须使用 dir_fd；Windows 本地测试使用显式拒绝 symlink 的降级实现。"""

        return (
            os.name != "nt"
            and hasattr(os, "O_DIRECTORY")
            and hasattr(os, "O_NOFOLLOW")
            and os.open in os.supports_dir_fd
            and os.mkdir in os.supports_dir_fd
        )

    @staticmethod
    def _open_directory_at(parent_fd: int, name: str) -> int:
        try:
            os.mkdir(name, mode=0o700, dir_fd=parent_fd)
        except FileExistsError:
            pass
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        try:
            directory_fd = os.open(name, flags, dir_fd=parent_fd)
        except OSError as exc:
            raise UnsafeWorkspacePathError(f"工作区目录不是安全的真实目录：{name}") from exc
        if not stat.S_ISDIR(os.fstat(directory_fd).st_mode):  # pragma: no cover - O_DIRECTORY 已保证
            os.close(directory_fd)
            raise UnsafeWorkspacePathError(f"工作区路径不是目录：{name}")
        return directory_fd

    def _write_note_posix(self, uid: str, relative_path: PurePosixPath, content: str) -> int:
        """使用稳定目录句柄和 O_NOFOLLOW 原子创建文件，关闭 symlink/TOCTOU 窗口。"""

        root_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        current_fd = os.open(self.workspace_root, root_flags)
        try:
            directory_parts = ("shared", self._workspace_uid_dirname(uid), "workspace", *relative_path.parts[:-1])
            for part in directory_parts:
                next_fd = self._open_directory_at(current_fd, part)
                os.close(current_fd)
                current_fd = next_fd

            filename = relative_path.name
            encoded = content.encode("utf-8")
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
            try:
                file_fd = os.open(filename, flags, 0o600, dir_fd=current_fd)
            except FileExistsError:
                self._confirm_existing_file_at(current_fd, filename, content)
                return len(encoded)
            try:
                with os.fdopen(file_fd, "w", encoding="utf-8", newline="\n", closefd=True) as handle:
                    handle.write(content)
            except Exception:
                # fdopen 接管了 file_fd；失败时让上层保存确定失败事实。
                raise
            return len(encoded)
        finally:
            os.close(current_fd)

    @staticmethod
    def _confirm_existing_file_at(parent_fd: int, filename: str, expected: str) -> None:
        expected_bytes = expected.encode("utf-8")
        try:
            file_fd = os.open(
                filename,
                os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                dir_fd=parent_fd,
            )
        except OSError as exc:
            raise UnsafeWorkspacePathError("已有目标不是安全的普通文件") from exc
        try:
            if not stat.S_ISREG(os.fstat(file_fd).st_mode):
                raise UnsafeWorkspacePathError("已有目标不是普通文件")
            with os.fdopen(file_fd, "rb", closefd=True) as handle:
                file_fd = -1
                if handle.read(len(expected_bytes) + 1) != expected_bytes:
                    raise ExistingFileConflictError("目标文件已存在且内容不同，拒绝覆盖")
        finally:
            if file_fd >= 0:
                os.close(file_fd)

    def _write_note_portable(self, uid: str, relative_path: PurePosixPath, content: str) -> int:
        """Windows 开发降级路径；逐级拒绝 symlink，生产容器不使用此分支。"""

        user_workspace = self.workspace_root
        for part in ("shared", self._workspace_uid_dirname(uid), "workspace"):
            user_workspace = user_workspace / part
            self._ensure_real_directory(user_workspace)
        target_parent = user_workspace
        for part in relative_path.parts[:-1]:
            target_parent = target_parent / part
            self._ensure_real_directory(target_parent)
        target = target_parent / relative_path.name
        if target.is_symlink():
            raise UnsafeWorkspacePathError("目标文件不能是符号链接")
        try:
            with target.open("x", encoding="utf-8", newline="\n") as handle:
                handle.write(content)
        except FileExistsError:
            if target.is_symlink() or not target.is_file():
                raise UnsafeWorkspacePathError("已有目标不是安全的普通文件") from None
            expected_bytes = content.encode("utf-8")
            if target.stat().st_size != len(expected_bytes):
                raise ExistingFileConflictError("目标文件已存在且内容不同，拒绝覆盖") from None
            with target.open("rb") as handle:
                actual = handle.read(len(expected_bytes) + 1)
            if actual != expected_bytes:
                raise ExistingFileConflictError("目标文件已存在且内容不同，拒绝覆盖") from None
        return len(content.encode("utf-8"))

    @staticmethod
    def _ensure_real_directory(path: Path) -> None:
        if path.is_symlink():
            raise UnsafeWorkspacePathError("工作区目录不能是符号链接")
        path.mkdir(mode=0o700, exist_ok=True)
        if path.is_symlink() or not path.is_dir():
            raise UnsafeWorkspacePathError("工作区路径不是安全目录")

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
    "ExecutionClaimLostError",
    "ExecutionInProgressError",
    "IdempotencyConflictError",
    "PersonalToolExecutor",
    "UnsafeWorkspacePathError",
    "canonical_digest",
]
