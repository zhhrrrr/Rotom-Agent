from pathlib import Path
from typing import Any

from app.core.config import settings


MAX_READ_BYTES = 200_000
MAX_WRITE_BYTES = 200_000


def _workspace_root(workspace_root: str | None = None) -> Path:
    # WORKSPACE_ROOT 来自 .env。
    # resolve() 会把相对路径、符号链接、.. 都规整成真实绝对路径。
    if workspace_root is not None:
        return Path(workspace_root).resolve()
    return settings.workspace_root.resolve()


def _resolve_workspace_path(path: str, workspace_root: str | None = None) -> Path:
    """把用户传入路径解析成 WORKSPACE_ROOT 内部的安全路径。"""

    root = _workspace_root(workspace_root)
    raw_path = Path(path)

    # 绝对路径例如 /etc/passwd 不允许直接使用。
    # 即使后面还有边界检查，这里先明确拒绝，错误更清楚。
    if raw_path.is_absolute():
        raise ValueError("Path must be relative to WORKSPACE_ROOT")

    # root / raw_path 后再 resolve，可以把 a/../b 规整成真实路径。
    target = (root / raw_path).resolve()

    # relative_to(root) 能证明 target 仍在 root 内部。
    # 如果 path 是 ../../etc，resolve 后会跑到 root 外面，这里会抛 ValueError。
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValueError("Path escapes WORKSPACE_ROOT") from exc

    return target


def _relative_workspace_path(path: Path, workspace_root: str | None = None) -> str:
    # 返回给模型看的路径使用相对 WORKSPACE_ROOT 的形式，避免泄露容器绝对路径。
    relative_path = path.relative_to(_workspace_root(workspace_root))
    return "." if str(relative_path) == "." else relative_path.as_posix()


def _is_inside_workspace(path: Path, workspace_root: str | None = None) -> bool:
    try:
        path.resolve().relative_to(_workspace_root(workspace_root))
    except ValueError:
        return False

    return True


def list_dir(path: str = ".", workspace_root: str | None = None) -> list[dict[str, Any]]:
    """列出 WORKSPACE_ROOT 内部某个目录下的文件和子目录。"""

    target = _resolve_workspace_path(path, workspace_root)

    if not target.exists():
        raise FileNotFoundError(f"Directory not found: {path}")
    if not target.is_dir():
        raise NotADirectoryError(f"Not a directory: {path}")

    entries: list[dict[str, Any]] = []
    for item in sorted(target.iterdir(), key=lambda item: (item.is_file(), item.name.lower())):
        # 如果工作区里有符号链接指向外部，不能跟随它去读外部文件信息。
        if item.is_symlink() and not _is_inside_workspace(item, workspace_root):
            item_type = "symlink"
            size = None
        else:
            item_type = "directory" if item.is_dir() else "file"
            size = item.stat().st_size if item.is_file() else None

        entries.append(
            {
                "name": item.name,
                "path": _relative_workspace_path(item, workspace_root),
                "type": item_type,
                "size": size,
            }
        )

    return entries


def read_file(path: str, workspace_root: str | None = None) -> str:
    """读取 WORKSPACE_ROOT 内部的 UTF-8 文本文件。"""

    target = _resolve_workspace_path(path, workspace_root)

    if not target.exists():
        raise FileNotFoundError(f"File not found: {path}")
    if not target.is_file():
        raise IsADirectoryError(f"Not a file: {path}")
    if target.stat().st_size > MAX_READ_BYTES:
        raise ValueError(f"File is too large to read safely: {path}")

    return target.read_text(encoding="utf-8")


def write_file(path: str, content: str, workspace_root: str | None = None) -> dict[str, Any]:
    """向 WORKSPACE_ROOT 内部写入 UTF-8 文本文件。"""

    target = _resolve_workspace_path(path, workspace_root)
    encoded_content = content.encode("utf-8")

    if len(encoded_content) > MAX_WRITE_BYTES:
        raise ValueError(f"Content is too large to write safely: {path}")
    if target.exists() and target.is_dir():
        raise IsADirectoryError(f"Cannot write file over directory: {path}")

    # 自动创建父目录，但父目录本身仍然必须在 WORKSPACE_ROOT 内部。
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")

    return {
        "path": _relative_workspace_path(target, workspace_root),
        "bytes": len(encoded_content),
    }
