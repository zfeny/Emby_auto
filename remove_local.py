"""临时脚本：根据 .env 配置校验远端文件后删除本地文件。"""

from __future__ import annotations

import os
import sys
from typing import List, Tuple

from dotenv import load_dotenv

from src.localfile import (
    ensure_directory,
    iter_files_sorted,
    relative_posix,
    remove_empty_directories,
    remove_file,
)
from src.rclone_client import RcloneClient


def _split_env_values(raw_value: str) -> List[str]:
    """Split a raw env var value into individual entries."""
    parts: List[str] = [raw_value]
    for separator in (";", ",", "\n"):
        next_parts: List[str] = []
        for part in parts:
            next_parts.extend(part.split(separator))
        parts = next_parts
    return [part.strip() for part in parts if part.strip()]


def load_source_dirs() -> List[str]:
    """Load one or multiple local source directories from environment variables."""
    directories: List[str] = []
    raw_multiple = os.getenv("LOCAL_SOURCE_DIRS")
    if raw_multiple:
        directories.extend(_split_env_values(raw_multiple))

    single = os.getenv("LOCAL_SOURCE_DIR")
    if single:
        directories.append(single.strip())

    seen = set()
    ordered: List[str] = []
    for directory in directories:
        if directory in seen:
            continue
        seen.add(directory)
        ordered.append(directory)
    return ordered


def _normalize_remote_root(remote_root: str) -> str:
    """Convert configured remote root to POSIX style without trailing slash."""
    normalized = remote_root.replace("\\", "/").rstrip("/")
    if not normalized:
        return "/"
    if not normalized.startswith("/"):
        normalized = f"/{normalized}"
    return normalized


def load_directory_pairs() -> List[Tuple[str, str]]:
    """Return (local_dir, remote_root) pairs based on environment variables."""
    pairs: List[Tuple[str, str]] = []
    raw_pairs = os.getenv("LOCAL_REMOTE_MAPS")

    if raw_pairs:
        seen_pairs = set()
        for entry in _split_env_values(raw_pairs):
            if "=>" not in entry:
                print(f"跳过映射 '{entry}': 缺少 '=>'")
                continue
            local_raw, remote_raw = entry.split("=>", 1)
            local_dir = local_raw.strip()
            remote_root = remote_raw.strip()
            if not local_dir or not remote_root:
                print(f"跳过映射 '{entry}': 本地或远端目录为空")
                continue
            pair = (local_dir, remote_root)
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            pairs.append(pair)

    if pairs:
        return pairs

    fallback_remote = os.getenv("RCLONE_REMOTE_ROOT") or os.getenv("OPENLIST_REMOTE_ROOT")
    sources = load_source_dirs()
    if fallback_remote and sources:
        return [(source, fallback_remote) for source in sources]

    return []


def main() -> int:
    load_dotenv()

    directory_pairs = load_directory_pairs()

    if not directory_pairs:
        print("请在 .env 中配置 LOCAL_REMOTE_MAPS 或 LOCAL_SOURCE_DIR(S) + RCLONE_REMOTE_ROOT。")
        return 1

    try:
        client = RcloneClient()
    except ValueError as exc:
        print(f"初始化失败: {exc}")
        return 1

    total_processed = 0
    total_removed = 0
    total_cleaned_dirs = 0

    for source_dir, remote_root in directory_pairs:
        try:
            base_path = ensure_directory(source_dir)
        except NotADirectoryError as exc:
            print(f"跳过目录 {source_dir}: {exc}")
            continue

        normalized_remote_root = _normalize_remote_root(remote_root)
        print(f"处理目录: {base_path} -> 远端根 {normalized_remote_root}")

        processed = 0
        removed = 0

        for file_path in iter_files_sorted(base_path):
            relative_remote = relative_posix(file_path, base_path)
            if normalized_remote_root == "/":
                remote_path = f"/{relative_remote}"
            else:
                remote_path = f"{normalized_remote_root}/{relative_remote}"

            processed += 1
            total_processed += 1
            print(f"检查 {file_path} -> {remote_path}")
            try:
                exists = client.remote_file_exists(remote_path)
            except RuntimeError as exc:
                print(f"校验失败，保留本地文件 {file_path}: {exc}")
                continue

            if exists:
                try:
                    remove_file(file_path)
                    removed += 1
                    total_removed += 1
                    print(f"远端存在，已删除本地文件: {file_path}")
                except (FileNotFoundError, IsADirectoryError) as exc:
                    print(f"删除本地文件失败 {file_path}: {exc}")
            else:
                print(f"远端未找到文件，保留本地文件: {file_path}")

        if processed == 0:
            print(f"目录 {base_path} 中未找到需要处理的文件。")
        else:
            print(f"目录 {base_path} 处理完成，共检查 {processed} 个文件，删除 {removed} 个。")

        removed_dirs = remove_empty_directories(base_path)
        total_cleaned_dirs += removed_dirs
        if removed_dirs:
            print(f"目录 {base_path} 额外清理空目录 {removed_dirs} 个。")

    if total_processed == 0:
        print("未在任何本地目录中找到需要处理的文件。")
    else:
        print(
            f"全部完成，共检查 {total_processed} 个文件，删除 {total_removed} 个，"
            f"清理空目录 {total_cleaned_dirs} 个。"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
