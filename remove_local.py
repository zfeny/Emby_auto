"""临时脚本：根据 .env 配置校验远端文件后删除本地文件。"""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv

from src.localfile import (
    ensure_directory,
    iter_files_sorted,
    relative_posix,
    remove_empty_directories,
    remove_file,
)
from src.openlist import OpenlistClient


def main() -> int:
    load_dotenv()

    source_dir = os.getenv("LOCAL_SOURCE_DIR")
    remote_root = os.getenv("OPENLIST_REMOTE_ROOT")

    if not source_dir or not remote_root:
        print("请在 .env 中配置 LOCAL_SOURCE_DIR 与 OPENLIST_REMOTE_ROOT。")
        return 1

    try:
        base_path = ensure_directory(source_dir)
    except NotADirectoryError as exc:
        print(exc)
        return 1

    normalized_remote_root = remote_root.replace("\\", "/").rstrip("/")
    if not normalized_remote_root:
        normalized_remote_root = "/"

    try:
        client = OpenlistClient()
    except ValueError as exc:
        print(f"初始化失败: {exc}")
        return 1

    processed = 0
    removed = 0

    for file_path in iter_files_sorted(base_path):
        relative_remote = relative_posix(file_path, base_path)
        if normalized_remote_root == "/":
            remote_path = f"/{relative_remote}"
        else:
            remote_path = f"{normalized_remote_root}/{relative_remote}"

        processed += 1
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
                print(f"远端存在，已删除本地文件: {file_path}")
            except (FileNotFoundError, IsADirectoryError) as exc:
                print(f"删除本地文件失败 {file_path}: {exc}")
        else:
            print(f"远端未找到文件，保留本地文件: {file_path}")

    if processed == 0:
        print("未在本地目录中找到需要处理的文件。")
    else:
        print(f"处理完成，共检查 {processed} 个文件，删除 {removed} 个。")

    removed_dirs = remove_empty_directories(base_path)
    if removed_dirs:
        print(f"已额外清理空目录 {removed_dirs} 个。")

    return 0


if __name__ == "__main__":
    sys.exit(main())
