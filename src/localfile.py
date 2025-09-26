"""本地文件系统相关的辅助函数。"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Generator, List, Tuple


def ensure_directory(path: str | Path) -> Path:
    """确保路径存在并返回解析后的目录路径。"""
    directory = Path(path).expanduser().resolve()
    if not directory.is_dir():
        raise NotADirectoryError(f"未找到目录: {path}")
    return directory


def iter_directories_sorted(root_dir: str | Path) -> Generator[Path, None, None]:
    """按照字母顺序遍历根目录及其子目录。"""
    base_path = ensure_directory(root_dir)
    yield base_path
    for current, dirnames, _ in os.walk(base_path):
        dirnames.sort()
        current_path = Path(current)
        for dirname in dirnames:
            yield current_path / dirname


def iter_files_sorted(root_dir: str | Path) -> Generator[Path, None, None]:
    """按照目录优先、文件名次序遍历根目录中的所有文件。"""
    base_path = ensure_directory(root_dir)
    for current, dirnames, filenames in os.walk(base_path):
        dirnames.sort()
        filenames.sort()
        current_path = Path(current)
        for filename in filenames:
            yield current_path / filename


def relative_path(file_path: str | Path, root_dir: str | Path) -> Path:
    """返回文件相对于根目录的 Path 对象。"""
    base_path = ensure_directory(root_dir)
    resolved_file = Path(file_path).expanduser().resolve()
    if not resolved_file.exists():
        raise FileNotFoundError(f"未找到文件: {file_path}")
    return resolved_file.relative_to(base_path)


def relative_posix(file_path: str | Path, root_dir: str | Path) -> str:
    """返回文件相对于根目录的 POSIX 风格字符串路径。"""
    return relative_path(file_path, root_dir).as_posix()


def snapshot_tree(root_dir: str | Path) -> Tuple[List[Path], List[Path]]:
    """采集根目录下的所有目录和文件列表。"""
    base_path = ensure_directory(root_dir)
    directories: List[Path] = []
    files: List[Path] = []
    for current, dirnames, filenames in os.walk(base_path):
        dirnames.sort()
        filenames.sort()
        current_path = Path(current)
        directories.append(current_path)
        for filename in filenames:
            files.append(current_path / filename)
    return directories, files


def remove_file(path: str | Path) -> None:
    """删除指定的本地文件。"""
    file_path = Path(path).expanduser().resolve()
    if not file_path.exists():
        raise FileNotFoundError(f"未找到文件: {path}")
    if not file_path.is_file():
        raise IsADirectoryError(f"路径不是文件: {path}")
    file_path.unlink()


def remove_empty_directories(root_dir: str | Path, *, preserve_root: bool = True) -> int:
    """递归删除空目录，返回删除的目录数量。"""
    base_path = ensure_directory(root_dir)
    removed = 0
    for current, dirnames, filenames in os.walk(base_path, topdown=False):
        if filenames:
            continue
        current_path = Path(current)
        # 如果包含子目录，需要确认子目录是否为空（因为 topdown=False 时已处理子目录）
        if any(current_path.iterdir()):
            continue
        if preserve_root and current_path == base_path:
            continue
        try:
            current_path.rmdir()
            removed += 1
        except OSError:
            continue
    return removed
