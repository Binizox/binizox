import errno
import os
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

_DIRECTORY_OPEN_FLAGS = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)


def supports_secure_dir_fd() -> bool:
    """返回当前平台是否支持 Linux 生产路径使用的安全 dir_fd 操作。"""

    return (
        os.name != "nt"
        and hasattr(os, "O_DIRECTORY")
        and hasattr(os, "O_NOFOLLOW")
        and os.open in os.supports_dir_fd
        and os.mkdir in os.supports_dir_fd
    )


def open_directory_fd(root: Path | int, parts: tuple[str, ...], *, create: bool = False) -> int:
    """从可信目录逐层 no-follow 打开路径，返回调用方负责关闭的 fd。

    ``parts`` 必须是已校验的单路径组件；传入 fd 时函数复制而不接管原 fd。
    """
    if not supports_secure_dir_fd():
        raise NotImplementedError("secure dir_fd traversal is unavailable on this platform")
    directory_fd = os.dup(root) if isinstance(root, int) else os.open(root, _DIRECTORY_OPEN_FLAGS)
    try:
        for part in parts:
            if create:
                try:
                    os.mkdir(part, 0o700, dir_fd=directory_fd)
                except FileExistsError:
                    pass
            try:
                child_fd = os.open(part, _DIRECTORY_OPEN_FLAGS, dir_fd=directory_fd)
            except OSError as exc:
                if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
                    try:
                        item_stat = os.stat(part, dir_fd=directory_fd, follow_symlinks=False)
                    except OSError:
                        raise exc
                    if stat.S_ISLNK(item_stat.st_mode):
                        raise OSError(errno.ELOOP, os.strerror(errno.ELOOP), part) from exc
                raise
            previous_fd = directory_fd
            directory_fd = child_fd
            os.close(previous_fd)
        return directory_fd
    except BaseException:
        os.close(directory_fd)
        raise


@contextmanager
def open_regular_file_fd(
    root: Path | int,
    parts: tuple[str, ...],
    *,
    writable: bool = False,
) -> Iterator[tuple[int, os.stat_result]]:
    """从可信根 no-follow 打开普通文件，并在同一 fd 上校验类型。"""
    if not parts:
        raise IsADirectoryError(str(root))
    if not supports_secure_dir_fd():
        if isinstance(root, int):
            raise NotImplementedError("portable file traversal requires a Path root")
        target = _portable_regular_file_path(root, parts)
        flags = os.O_WRONLY if writable else os.O_RDONLY
        file_fd = os.open(target, flags)
        try:
            file_stat = os.fstat(file_fd)
            if not stat.S_ISREG(file_stat.st_mode):
                raise PermissionError("only regular files are allowed")
            yield file_fd, file_stat
        finally:
            os.close(file_fd)
        return
    try:
        parent_fd = open_directory_fd(root, parts[:-1])
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise PermissionError("symlink paths are not allowed") from exc
        raise
    file_fd = None
    try:
        flags = (os.O_WRONLY if writable else os.O_RDONLY) | os.O_NOFOLLOW | os.O_NONBLOCK
        try:
            file_fd = os.open(parts[-1], flags, dir_fd=parent_fd)
        except OSError as exc:
            if exc.errno == errno.ELOOP:
                raise PermissionError("symlink paths are not allowed") from exc
            raise
        file_stat = os.fstat(file_fd)
        if stat.S_ISDIR(file_stat.st_mode):
            raise IsADirectoryError(parts[-1])
        if not stat.S_ISREG(file_stat.st_mode):
            raise PermissionError("only regular files are allowed")
        yield file_fd, file_stat
    finally:
        if file_fd is not None:
            os.close(file_fd)
        os.close(parent_fd)


def _portable_regular_file_path(root: Path, parts: tuple[str, ...]) -> Path:
    """Windows 本地开发路径：逐级拒绝 symlink 后返回普通文件。"""

    current = root
    if current.is_symlink() or not current.is_dir():
        raise PermissionError("workspace root must be a real directory")
    for part in parts[:-1]:
        current = current / part
        if current.is_symlink():
            raise PermissionError("symlink paths are not allowed")
        if not current.is_dir():
            raise NotADirectoryError(str(current))
    target = current / parts[-1]
    if target.is_symlink():
        raise PermissionError("symlink paths are not allowed")
    if not target.is_file():
        if target.exists():
            raise PermissionError("only regular files are allowed")
        raise FileNotFoundError(str(target))
    return target


def ensure_within_root(path: Path, root: Path, *, error_message: str) -> Path:
    """确认真实路径位于指定根目录内，否则拒绝越界访问。"""
    try:
        path.relative_to(root)
    except ValueError:
        raise ValueError(error_message) from None
    return path


__all__ = [
    "open_directory_fd",
    "open_regular_file_fd",
    "ensure_within_root",
    "supports_secure_dir_fd",
]
