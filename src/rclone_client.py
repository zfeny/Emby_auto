"""Minimal rclone wrapper used by the upload scripts."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
from pathlib import Path, PurePosixPath
from typing import Iterable, List

from dotenv import load_dotenv


class RcloneClient:
    """Lightweight helper around rclone CLI."""

    def __init__(self) -> None:
        load_dotenv()
        self.remote = os.getenv("RCLONE_REMOTE", "123").strip()
        extra_args = os.getenv("RCLONE_GLOBAL_ARGS", "").strip()
        self.global_args: List[str] = shlex.split(extra_args) if extra_args else []
        if not self.remote:
            raise ValueError("请在 .env 中配置 RCLONE_REMOTE（如 123）。")

    @staticmethod
    def _normalize_remote_path(remote_path: str) -> str:
        """Return a POSIX-style absolute path for rclone."""
        normalized = remote_path.replace("\\", "/")
        if not normalized.startswith("/"):
            normalized = f"/{normalized}"
        return normalized

    def _run(self, args: Iterable[str]) -> subprocess.CompletedProcess[str]:
        cmd = ["rclone", *self.global_args, *args]
        return subprocess.run(cmd, check=True, capture_output=True, text=True)

    def upload_file(self, local_path: str, remote_path: str) -> None:
        """Copy a single file to remote path."""
        file_path = Path(local_path)
        if not file_path.is_file():
            raise FileNotFoundError(f"未找到文件: {local_path}")

        target = self._normalize_remote_path(remote_path)
        dest = f"{self.remote}:{target}"

        cmd: List[str] = [
            "rclone",
            *self.global_args,
            "copyto",
            str(file_path),
            dest,
            "--progress=false",
            "--stats=0",
        ]

        process = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        if process.returncode != 0:
            message = process.stderr.strip() or f"退出码 {process.returncode}"
            raise RuntimeError(f"上传失败: {message}")

    def remote_file_exists(self, remote_path: str) -> bool:
        """Check whether a file exists on the remote."""
        normalized = self._normalize_remote_path(remote_path)
        pure = PurePosixPath(normalized)
        if pure.name == "":
            raise ValueError("远程路径必须包含文件名。")

        parent = str(pure.parent)
        parent_path = "/" if parent == "." else parent

        try:
            result = self._run(
                [
                    "lsjson",
                    f"{self.remote}:{parent_path}",
                    "--files-only",
                    "--no-modtime",
                    "--no-mimetype",
                ]
            )
        except subprocess.CalledProcessError as exc:
            message = exc.stderr.strip() or exc.stdout.strip() or str(exc)
            raise RuntimeError(f"远程检查失败: {message}") from exc

        try:
            entries = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError("远程检查返回的 JSON 无法解析。") from exc

        for entry in entries:
            if entry.get("IsDir"):
                continue
            if entry.get("Name") == pure.name:
                return True
        return False
