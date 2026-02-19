#!/bin/bash
target_dir="/file/downloads"

# 防呆机制：禁止误删系统根目录
if [ "$target_dir" == "/" ] || [ -z "$target_dir" ]; then
  echo "❌ Error: Invalid target_dir: '$target_dir'"
  exit 1
fi

# 删除空目录（递归），但不删除根目录本身
find "$target_dir" -type d -empty -not -path "$target_dir" -delete

# 记录日志（可选）
echo "$(date '+%F %T') | Removed empty directories under $target_dir" >> /var/log/rm_empty_dirs.log
