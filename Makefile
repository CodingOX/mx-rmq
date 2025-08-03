# MX-RMQ Makefile
# 提供常用的测试和开发命令

.PHONY: help install test test-quick test-full test-release coverage integration clean lint format security build

# 默认目标
help:
	@echo "MX-RMQ 项目管理命令"
	@echo ""
	@echo "可用命令:"
	@echo "  install       安装项目依赖"
	@echo "  test          运行默认测试 (等同于test-full)"
	@echo "  test-quick    快速测试 (P0核心功能)"
	@echo "  test-full     完整单元测试"
	@echo "  test-release  发版前检查"
	@echo "  coverage      生成覆盖率报告"
	@echo "  integration   集成测试 (需要Redis)"
	@echo "  lint          代码风格检查"
	@echo "  format        代码格式化"
	@echo "  security      安全检查"
	@echo "  build         构建项目包"
	@echo "  clean         清理临时文件"
	@echo ""
	@echo "快速开始:"
	@echo "  make install     # 首次安装依赖"
	@echo "  make test-quick  # 开发时快速验证"
	@echo "  make test-release # 发版前完整检查"

# 安装依赖
install:
	@echo "📦 安装项目依赖..."
	uv sync
	@echo "✅ 依赖安装完成"

# 测试相关命令
test: test-full

test-quick:
	@echo "🚀 运行快速测试..."
	./run_tests.sh --quick

test-full:
	@echo "🧪 运行完整测试..."
	./run_tests.sh --full

test-release:
	@echo "🎯 发版前检查..."
	./run_tests.sh --release

coverage:
	@echo "📊 生成覆盖率报告..."
	./run_tests.sh --coverage
	@echo "📄 HTML报告: htmlcov/index.html"

integration:
	@echo "🔗 运行集成测试..."
	./run_tests.sh --integration

# 代码质量检查
lint:
	@echo "🔍 代码风格检查..."
	uv run ruff check src/ tests/
	@echo "✅ 代码风格检查完成"

format:
	@echo "✨ 代码格式化..."
	uv run ruff format src/ tests/
	uv run ruff check --fix src/ tests/
	@echo "✅ 代码格式化完成"

security:
	@echo "🔒 安全检查..."
	uv run bandit -r src/
	@echo "✅ 安全检查完成"

# 类型检查
typecheck:
	@echo "🔍 类型检查..."
	uv run mypy src/ --ignore-missing-imports
	@echo "✅ 类型检查完成"

# 构建相关
build:
	@echo "🏗️ 构建项目包..."
	uv build
	@echo "✅ 构建完成，产物在 dist/ 目录"

# 清理临时文件
clean:
	@echo "🧹 清理临时文件..."
	rm -rf __pycache__/
	rm -rf .pytest_cache/
	rm -rf .coverage
	rm -rf htmlcov/
	rm -rf coverage.xml
	rm -rf dist/
	rm -rf build/
	rm -rf *.egg-info/
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@echo "✅ 清理完成"

# 开发环境设置
dev-setup: install
	@echo "🛠️ 设置开发环境..."
	uv run pre-commit install 2>/dev/null || echo "⚠️ pre-commit未安装，跳过git hooks设置"
	@echo "✅ 开发环境设置完成"

# 完整检查 (发版前必做)
pre-release: clean install lint typecheck test-release
	@echo "🎉 发版前检查全部完成！"

# 快速开发检查
dev-check: lint test-quick
	@echo "✅ 开发检查完成"

# CI/CD相关
ci-test:
	@echo "🤖 CI模式测试..."
	./run_tests.sh --ci

# 帮助信息
info:
	@echo "项目信息:"
	@echo "  名称: MX-RMQ"
	@echo "  版本: $(shell grep -E '^version' pyproject.toml | cut -d'"' -f2)"
	@echo "  Python: $(shell python --version)"
	@echo "  uv: $(shell uv --version)"
	@echo ""
	@echo "测试统计:"
	@echo "  P0核心功能: 89个测试"
	@echo "  P1重要功能: 31个测试"
	@echo "  P2辅助功能: 64个测试"
	@echo "  总计: 184个单元测试"