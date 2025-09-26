import os
import sys

from src.localfile import ensure_directory, iter_files_sorted, relative_posix
from src.openlist import OpenlistClient

def main():
    """
    主执行函数
    """
    try:
        # 1. 创建客户端实例
        # 这会自动从 .env 文件加载配置
        client = OpenlistClient()
        print("已加载Openlist配置……")

        # 2. 进行身份验证
        if client.authenticate():
            print(f"成功获取到 Token: {client.token[:10]}...")  # 只显示部分 token
        else:
            print("无法完成认证。请检查 .env 文件中的用户名和密码是否正确。")
            sys.exit(1)

        # 3. 按需读取环境变量，执行批量上传
        source_dir = os.getenv("LOCAL_SOURCE_DIR")
        remote_root = os.getenv("OPENLIST_REMOTE_ROOT")

        if source_dir and remote_root:
            base_path = ensure_directory(source_dir)
            normalized_remote_root = remote_root.replace("\\", "/").rstrip("/")
            if not normalized_remote_root:
                normalized_remote_root = "/"

            file_count = 0
            for file_path in iter_files_sorted(base_path):
                relative_remote = relative_posix(file_path, base_path)
                if normalized_remote_root == "/":
                    remote_path = f"/{relative_remote}"
                else:
                    remote_path = f"{normalized_remote_root}/{relative_remote}"

                print(f"上传 {file_path} -> {remote_path}")
                client.upload_file(str(file_path), remote_path)
                file_count += 1

            if file_count:
                print(f"批量上传完成，共上传 {file_count} 个文件。")
            else:
                print("扫描完成，但未发现需要上传的文件。")
        else:
            print("未设置 LOCAL_SOURCE_DIR 或 OPENLIST_REMOTE_ROOT，跳过批量上传步骤。")

        # 4. 扫描两处目录，删除已上传云端的本地文件（预留实现）

    except ValueError as e:
        print(f"初始化失败: {e}")
    except (FileNotFoundError, NotADirectoryError, RuntimeError) as exc:
        print(f"执行过程中发生错误: {exc}")
        sys.exit(1)

if __name__ == "__main__":
    main()
