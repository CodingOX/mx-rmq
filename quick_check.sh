#!/bin/bash

# MX-RMQ 快速验证脚本
# 最简单的发版前检查，只验证核心功能

set -e

echo "🚀 MX-RMQ 快速验证开始..."

# 检查环境
echo "📋 检查环境..."
python --version
uv --version

# 同步依赖
echo "📦 同步依赖..."
uv sync --quiet

# 运行核心测试
echo "🧪 运行核心测试..."
uv run pytest tests/unit/test_config.py tests/unit/test_message.py tests/unit/test_queue.py -v --tb=short

echo ""
echo "✅ 快速验证完成！"
echo "💡 提示: 运行 './run_tests.sh --release' 进行完整的发版前检查"