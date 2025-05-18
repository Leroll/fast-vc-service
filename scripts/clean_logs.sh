#!/bin/bash

# 脚本功能：删除logs/目录下文件名中包含.log的日志文件（包括带日期后缀的文件）

# 定义日志目录
LOG_DIR="logs/"

# 检查.logs/目录是否存在
if [ ! -d "$LOG_DIR" ]; then
    echo "错误：$LOG_DIR 目录不存在"
    exit 1
fi

# 使用 find 命令查找文件名中包含 .log 的文件并删除
found_files=$(find "$LOG_DIR" -type f -name "*.log*")

# 检查是否找到匹配文件
if [ -n "$found_files" ]; then
    while IFS= read -r file; do
        # 删除文件
        rm -f "$file"
        echo "已删除: $file"
    done <<< "$found_files"
    echo "所有包含 .log 的日志文件已删除"
else
    echo "没有找到包含 .log 的文件"
fi