import os
from pathlib import Path, PurePosixPath
from urllib.parse import quote

import requests
from dotenv import load_dotenv

class OpenlistClient:
    """
    一个用于与 Openlist API 交互的客户端。
    """
    def __init__(self):
        """
        初始化客户端，并从 .env 文件加载配置。
        """
        load_dotenv()
        self.base_url = os.getenv("OPENLIST_API_BASE_URL")
        self.username = os.getenv("OPENLIST_USERNAME")
        self.password = os.getenv("OPENLIST_PASSWORD")
        self.token = None

        if not all([self.base_url, self.username, self.password]):
            raise ValueError("请确保 .env 文件中已正确设置 OPENLIST_API_BASE_URL, OPENLIST_USERNAME, 和 OPENLIST_PASSWORD")

    def authenticate(self):
        """
        与 API 进行身份验证并获取令牌。
        如果成功，令牌将存储在 self.token 中。
        """
        """
        使用用户名和密码与 API 进行身份验证并获取 JWT 令牌。
        如果成功，令牌将存储在 self.token 中。
        """
        auth_url = f"{self.base_url}/api/auth/login"
        payload = {
            "username": self.username,
            "password": self.password
        }
        
        try:
            response = requests.post(auth_url, json=payload)
            response.raise_for_status()  # 如果状态码不是 2xx，则会引发 HTTPError

            response_data = response.json()
            if response_data.get("code") == 200 and response_data.get("data"):
                self.token = response_data["data"]["token"]
                print("认证成功！")
                return True
            else:
                print(f"认证失败: {response_data.get('message', '未知错误')}")
                return False

        except requests.exceptions.RequestException as e:
            print(f"请求时发生错误: {e}")
            return False

    def _normalize_remote_path(self, remote_path: str) -> str:
        """把用户传入的远程路径规范化为以 `/` 开头的 POSIX 风格路径。"""
        normalized = remote_path.replace("\\", "/")
        if not normalized.startswith("/"):
            normalized = f"/{normalized}"
        return normalized

    def upload_file(
        self,
        local_path: str,
        remote_path: str,
        *,
        as_task: bool = True,
        reauthenticate: bool = True,
    ) -> dict:
        """
        使用 Openlist 的流式上传接口上传单个文件。

        Args:
            local_path: 待上传的本地文件路径。
            remote_path: 上传到 Openlist 的目标绝对路径。
            as_task: 是否以任务的方式提交 (对应 `As-Task` 头)。
            reauthenticate: 如果为 True，则在上传前强制重新获取 token。

        Returns:
            Openlist 返回的数据字典。如果响应体不是 JSON，将抛出异常。
        """
        file_path = Path(local_path)
        if not file_path.is_file():
            raise FileNotFoundError(f"未找到文件: {local_path}")

        if reauthenticate or not self.token:
            if not self.authenticate():
                raise RuntimeError("重新认证失败，无法上传文件。")

        target_path = self._normalize_remote_path(remote_path)
        if target_path.endswith("/"):
            raise ValueError("远程路径必须包含文件名，不能以 '/' 结尾。")
        headers = {
            "Authorization": self.token,
            "File-Path": quote(target_path, safe="/%"),
            "Content-Type": "application/octet-stream",
            "Content-Length": str(file_path.stat().st_size),
        }
        if as_task:
            headers["As-Task"] = "true"

        upload_url = f"{self.base_url}/api/fs/put"
        try:
            with file_path.open("rb") as stream:
                response = requests.put(upload_url, headers=headers, data=stream)
                response.raise_for_status()
        except requests.exceptions.RequestException as exc:
            raise RuntimeError(f"上传文件时发生请求错误: {exc}") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError("上传成功，但响应不是有效的 JSON。") from exc

        if payload.get("code") != 200:
            raise RuntimeError(f"上传失败: {payload.get('message', '未知错误')}")

        return payload.get("data", {})

    def list_directory(
        self,
        path: str,
        *,
        page: int = 1,
        per_page: int = 0,
        refresh: bool = False,
        reauthenticate: bool = True,
    ) -> dict:
        """调用 Openlist 接口列出指定目录内容。"""
        normalized_path = self._normalize_remote_path(path)

        if reauthenticate or not self.token:
            if not self.authenticate():
                raise RuntimeError("重新认证失败，无法列出远程目录。")

        url = f"{self.base_url}/api/fs/list"
        headers = {
            "Authorization": self.token,
            "Content-Type": "application/json",
        }
        payload = {
            "path": normalized_path,
            "page": page,
            "per_page": per_page,
            "refresh": refresh,
        }

        try:
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()
        except requests.exceptions.RequestException as exc:
            raise RuntimeError(f"列出目录时发生请求错误: {exc}") from exc

        try:
            body = response.json()
        except ValueError as exc:
            raise RuntimeError("目录列出成功，但响应不是有效的 JSON。") from exc

        if body.get("code") != 200:
            raise RuntimeError(f"列出目录失败: {body.get('message', '未知错误')}")

        return body.get("data", {})

    def remote_file_exists(self, remote_path: str, *, reauthenticate: bool = True) -> bool:
        """检查远程路径下的文件是否存在。"""
        normalized_path = self._normalize_remote_path(remote_path)
        pure_path = PurePosixPath(normalized_path)
        if pure_path.name == "":
            raise ValueError("远程路径必须包含文件名。")

        parent = str(pure_path.parent)
        directory = parent if parent != "." else "/"

        directory_data = self.list_directory(directory, reauthenticate=reauthenticate)
        contents = directory_data.get("content", [])
        for item in contents:
            if not isinstance(item, dict):
                continue
            if item.get("is_dir"):
                continue
            if item.get("name") == pure_path.name:
                return True
        return False
