#!/bin/bash
target_dir="/file/shualiu"

# 确保目录存在
if [ -d "$target_dir" ]; then
  # 删除目录下所有文件和子目录，但不删除根目录
  find "$target_dir" -mindepth 1 -delete
else
  echo "Directory $target_dir not found!"
fi
