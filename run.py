#!/usr/bin/env python3

import os
import sys
import time
from contextlib import redirect_stderr, redirect_stdout
from itertools import chain
from pathlib import Path
from typing import List, Tuple, TextIO
from fcntl import flock, LOCK_EX, LOCK_NB

from dotenv import load_dotenv

from src.localfile import (
    ensure_directory,
    iter_files_sorted,
    relative_posix,
    remove_empty_directories,
    remove_file,
)
from src.rclone_client import RcloneClient


LOG_FILE_PATH = Path("logs/run.log")
ERROR_LOG_PATH = Path("logs/error.log")
LOCK_FILE_PATH = Path("run.lock")


class _TeeStream:
    """Mirror writes to multiple text streams."""

    def __init__(self, *targets: TextIO):
        self._targets = targets

    def write(self, data: str) -> int:
        for target in self._targets:
            target.write(data)
            target.flush()
        return len(data)

    def flush(self) -> None:
        for target in self._targets:
            target.flush()


class _TimestampStream:
    """Prefix each line with a timestamp."""

    def __init__(self, target: TextIO):
        self._target = target
        self._buffer = ""

    def _timestamp(self) -> str:
        return time.strftime("%Y/%m/%d %H:%M", time.localtime())

    def write(self, data: str) -> int:
        self._buffer += data
        written = 0
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            out = f"{self._timestamp()} {line}\n"
            self._target.write(out)
            self._target.flush()
            written += len(data)
        return written

    def flush(self) -> None:
        if self._buffer:
            out = f"{self._timestamp()} {self._buffer}"
            self._target.write(out)
            self._buffer = ""
        self._target.flush()


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
            pairs.append((local_dir, remote_root))

    if pairs:
        return pairs

    fallback_remote = os.getenv("RCLONE_REMOTE_ROOT") or os.getenv("OPENLIST_REMOTE_ROOT")
    sources = load_source_dirs()
    if fallback_remote and sources:
        return [(source, fallback_remote) for source in sources]

    return []


def _acquire_lock() -> TextIO:
    """
    防止重复运行：基于文件锁。
    如果已有实例持有锁，则直接退出。
    """
    LOCK_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    lock_file = LOCK_FILE_PATH.open("w")
    try:
        flock(lock_file, LOCK_EX | LOCK_NB)
    except BlockingIOError:
        print("检测到已有运行中的实例，禁止重复启动。")
        sys.exit(1)

    lock_file.write(str(os.getpid()))
    lock_file.flush()
    return lock_file


def _run_upload() -> None:
    """
    主执行函数
    """
    try:
        load_dotenv()
        client = RcloneClient()

        directory_pairs = load_directory_pairs()

        if directory_pairs:
            file_count = 0
            cleaned_dirs = 0
            for source_dir, remote_root in directory_pairs:
                try:
                    base_path = ensure_directory(source_dir)
                except NotADirectoryError as exc:
                    print(f"跳过目录 {source_dir}: {exc}")
                    continue

                normalized_remote_root = _normalize_remote_root(remote_root)
                files_iter = iter_files_sorted(base_path)
                try:
                    first_file = next(files_iter)
                except StopIteration:
                    print(f"扫描目录: {base_path} -> 远端根 {normalized_remote_root} (无待上传文件)")
                    removed_count = remove_empty_directories(base_path)
                    cleaned_dirs += removed_count
                    if removed_count:
                        print(f"目录 {base_path} 清理空目录 {removed_count} 个。")
                    continue

                print(f"扫描目录: {base_path} -> 远端根 {normalized_remote_root}")
                for file_path in chain((first_file,), files_iter):
                    relative_remote = relative_posix(file_path, base_path)
                    if normalized_remote_root == "/":
                        remote_path = f"/{relative_remote}"
                    else:
                        remote_path = f"{normalized_remote_root}/{relative_remote}"

                    start = time.time()
                    print(f"开始上传 {file_path} -> {remote_path}")
                    client.upload_file(str(file_path), remote_path)
                    elapsed = time.time() - start
                    print(f"完成上传 {file_path} -> {remote_path} 用时 {elapsed:.1f}s")
                    file_count += 1

                    try:
                        remove_file(file_path)
                        print(f"已删除本地文件 {file_path}")
                    except (FileNotFoundError, IsADirectoryError) as exc:
                        print(f"删除本地文件失败 {file_path}: {exc}")

                removed_count = remove_empty_directories(base_path)
                cleaned_dirs += removed_count
                if removed_count:
                    print(f"目录 {base_path} 清理空目录 {removed_count} 个。")

            if file_count:
                message = f"批量上传完成，共上传 {file_count} 个文件。"
                if cleaned_dirs:
                    message += f" 同时清理空目录 {cleaned_dirs} 个。"
                print(message)
            else:
                if cleaned_dirs:
                    print(f"扫描完成，未上传文件，但清理空目录 {cleaned_dirs} 个。")
                else:
                    print("扫描完成，未发现需要上传的文件。")
        else:
            print("未找到任何有效的本地与远端目录映射，跳过批量上传步骤。")

    except ValueError as e:
        print(f"初始化失败: {e}")
    except (FileNotFoundError, NotADirectoryError, RuntimeError) as exc:
        print(f"执行过程中发生错误: {exc}")
        sys.exit(1)


def main() -> None:
    LOG_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    # 清空正常日志，错误日志持续累积
    LOG_FILE_PATH.open("w").close()
    ERROR_LOG_PATH.touch()

    lock_file: TextIO | None = None
    try:
        lock_file = _acquire_lock()
        with LOG_FILE_PATH.open("a", encoding="utf-8") as log_file, ERROR_LOG_PATH.open(
            "a", encoding="utf-8"
        ) as err_file:
            stdout_stream = _TimestampStream(_TeeStream(sys.stdout, log_file))
            stderr_stream = _TimestampStream(_TeeStream(sys.stderr, log_file, err_file))
            with redirect_stdout(stdout_stream), redirect_stderr(stderr_stream):
                _run_upload()
    finally:
        if lock_file:
            lock_file.close()

if __name__ == "__main__":
    main()
