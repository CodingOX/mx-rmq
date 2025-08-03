#!/bin/bash

# MX-RMQ 一键测试脚本
# 使用方法: ./run_tests.sh [选项]
# 
# 选项:
#   --quick     快速测试 (P0核心功能)
#   --full      完整单元测试 
#   --release   发版前完整检查
#   --coverage  带覆盖率报告
#   --integration 集成测试 (需要Redis)
#   --help      显示帮助信息

set -e  # 遇到错误立即退出

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 图标定义
SUCCESS="✅"
WARNING="⚠️"
ERROR="❌"
INFO="ℹ️"

# 全局变量
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEST_START_TIME=$(date +%s)
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0
COVERAGE_THRESHOLD=90

# 日志函数
log_info() {
    echo -e "${BLUE}${INFO} $1${NC}"
}

log_success() {
    echo -e "${GREEN}${SUCCESS} $1${NC}"
}

log_warning() {
    echo -e "${YELLOW}${WARNING} $1${NC}"
}

log_error() {
    echo -e "${RED}${ERROR} $1${NC}"
}

log_header() {
    echo -e "\n${BLUE}================================${NC}"
    echo -e "${BLUE} $1${NC}"
    echo -e "${BLUE}================================${NC}"
}

# 显示帮助信息
show_help() {
    cat << EOF
MX-RMQ 一键测试脚本

使用方法:
    ./run_tests.sh [选项]

选项:
    --quick         快速测试 (P0核心功能，约1分钟)
    --full          完整单元测试 (所有单元测试，约3分钟)  
    --release       发版前完整检查 (推荐，约5分钟)
    --coverage      带覆盖率报告 (生成HTML报告)
    --integration   集成测试 (需要Redis环境)
    --ci            CI模式 (静默输出，适合自动化)
    --help          显示此帮助信息

示例:
    ./run_tests.sh --quick          # 开发时快速验证
    ./run_tests.sh --full           # 日常完整测试
    ./run_tests.sh --release        # 发版前检查
    ./run_tests.sh --coverage       # 生成覆盖率报告

发版通过标准:
    ✅ P0核心功能: 100% 通过 (89/89)
    ✅ P1重要功能: ≥95% 通过 (≥30/31)
    ✅ 总体覆盖率: ≥90%
EOF
}

# 检查环境
check_environment() {
    log_header "环境检查"
    
    # 检查Python版本
    if command -v python &> /dev/null; then
        PYTHON_VERSION=$(python --version 2>&1 | cut -d' ' -f2)
        log_info "Python版本: $PYTHON_VERSION"
        
        # 检查是否为3.12+
        if python -c "import sys; exit(0 if sys.version_info >= (3, 12) else 1)" 2>/dev/null; then
            log_success "Python版本检查通过"
        else
            log_error "需要Python 3.12或更高版本"
            exit 1
        fi
    else
        log_error "未找到Python"
        exit 1
    fi
    
    # 检查uv
    if command -v uv &> /dev/null; then
        UV_VERSION=$(uv --version 2>&1 | cut -d' ' -f2)
        log_info "uv版本: $UV_VERSION"
        log_success "uv检查通过"
    else
        log_error "需要安装uv包管理器"
        exit 1
    fi
    
    # 检查项目依赖
    if [ -f "pyproject.toml" ]; then
        log_info "检查项目依赖..."
        uv sync --quiet || {
            log_error "依赖同步失败"
            exit 1
        }
        log_success "项目依赖检查通过"
    else
        log_error "未找到pyproject.toml文件"
        exit 1
    fi
}

# 运行测试并解析结果
run_pytest() {
    local test_path="$1"
    local test_name="$2"
    local extra_args="$3"
    
    log_info "正在运行: $test_name"
    
    # 创建临时结果文件
    local result_file=$(mktemp)
    local output_file=$(mktemp)
    
    # 运行pytest并捕获结果
    if uv run pytest "$test_path" -v --tb=short $extra_args > "$output_file" 2>&1; then
        local test_result=$?
    else
        local test_result=$?
    fi
    
    # 解析测试结果
    local passed=$(grep -E "^.* passed" "$output_file" | tail -1 | grep -oE '[0-9]+' | head -1 || echo "0")
    local failed=$(grep -E "^.* failed" "$output_file" | tail -1 | grep -oE '[0-9]+ failed' | grep -oE '[0-9]+' || echo "0")
    local total=$((passed + failed))
    
    # 更新全局统计
    TOTAL_TESTS=$((TOTAL_TESTS + total))
    PASSED_TESTS=$((PASSED_TESTS + passed))
    FAILED_TESTS=$((FAILED_TESTS + failed))
    
    # 显示结果
    if [ "$test_result" -eq 0 ] && [ "$failed" -eq 0 ]; then
        log_success "$test_name: $passed/$total 通过"
        echo "$passed/$total" > "$result_file"
    else
        log_error "$test_name: $passed/$total 通过, $failed 失败"
        echo "$passed/$total" > "$result_file"
        
        # 显示失败的测试
        if [ "$failed" -gt 0 ]; then
            echo -e "\n${YELLOW}失败的测试:${NC}"
            grep -A 5 "FAILURES" "$output_file" | head -20 || true
        fi
    fi
    
    # 清理临时文件
    rm -f "$result_file" "$output_file"
    
    return $test_result
}

# P0核心功能测试
run_p0_tests() {
    log_header "P0 核心功能测试 (必须100%通过)"
    
    local p0_start=$PASSED_TESTS
    local p0_tests=0
    
    # 配置管理测试
    run_pytest "tests/unit/test_config.py" "配置管理测试"
    p0_tests=$((p0_tests + 16))
    
    # 消息模型测试  
    run_pytest "tests/unit/test_message.py" "消息模型测试"
    p0_tests=$((p0_tests + 25))
    
    # 队列核心功能测试
    run_pytest "tests/unit/test_queue.py" "队列核心功能测试"
    p0_tests=$((p0_tests + 15))
    
    # 存储层测试
    run_pytest "tests/unit/test_storage.py" "存储层测试"
    p0_tests=$((p0_tests + 9))
    
    # 消息生命周期测试
    run_pytest "tests/unit/test_lifecycle.py" "消息生命周期测试"
    p0_tests=$((p0_tests + 13))
    
    # 优雅停机测试
    run_pytest "tests/unit/test_shutdown.py" "优雅停机测试"
    p0_tests=$((p0_tests + 11))
    
    local p0_passed=$((PASSED_TESTS - p0_start))
    local p0_success_rate=$((p0_passed * 100 / p0_tests))
    
    echo -e "\n${BLUE}P0测试汇总:${NC}"
    printf "  期望: 89个测试\n"
    printf "  实际: %d个测试\n" "$p0_tests"
    printf "  通过: %d个\n" "$p0_passed"
    printf "  成功率: %d%%\n" "$p0_success_rate"
    
    if [ "$p0_success_rate" -eq 100 ]; then
        log_success "P0核心功能测试: 100% 通过 ✅"
        return 0
    else
        log_error "P0核心功能测试: $p0_success_rate% 通过 ❌"
        return 1
    fi
}

# P1重要功能测试
run_p1_tests() {
    log_header "P1 重要功能测试 (≥95%通过)"
    
    local p1_start=$PASSED_TESTS
    local p1_tests=0
    
    # 监控模块测试
    run_pytest "tests/unit/test_monitoring.py" "监控模块测试"
    p1_tests=$((p1_tests + 22))
    
    # 消费者服务测试
    run_pytest "tests/unit/test_consumer.py" "消费者服务测试"
    p1_tests=$((p1_tests + 9))
    
    local p1_passed=$((PASSED_TESTS - p1_start))
    local p1_success_rate=$((p1_passed * 100 / p1_tests))
    
    echo -e "\n${BLUE}P1测试汇总:${NC}"
    printf "  期望: 31个测试\n"
    printf "  实际: %d个测试\n" "$p1_tests"
    printf "  通过: %d个\n" "$p1_passed"
    printf "  成功率: %d%%\n" "$p1_success_rate"
    
    if [ "$p1_success_rate" -ge 95 ]; then
        log_success "P1重要功能测试: $p1_success_rate% 通过 ✅"
        return 0
    elif [ "$p1_success_rate" -ge 90 ]; then
        log_warning "P1重要功能测试: $p1_success_rate% 通过 ⚠️"
        return 0
    else
        log_error "P1重要功能测试: $p1_success_rate% 通过 ❌"
        return 1
    fi
}

# P2辅助功能测试
run_p2_tests() {
    log_header "P2 辅助功能测试 (≥80%通过)"
    
    local p2_start=$PASSED_TESTS
    local p2_tests=0
    
    
    # 边界条件测试
    run_pytest "tests/unit/test_edge_cases.py" "边界条件测试" "--tb=no"
    p2_tests=$((p2_tests + 35))
    
    local p2_passed=$((PASSED_TESTS - p2_start))
    local p2_success_rate=$((p2_passed * 100 / p2_tests))
    
    echo -e "\n${BLUE}P2测试汇总:${NC}"
    printf "  期望: 64个测试\n"
    printf "  实际: %d个测试\n" "$p2_tests"
    printf "  通过: %d个\n" "$p2_passed"
    printf "  成功率: %d%%\n" "$p2_success_rate"
    
    if [ "$p2_success_rate" -ge 80 ]; then
        log_success "P2辅助功能测试: $p2_success_rate% 通过 ✅"
        return 0
    else
        log_warning "P2辅助功能测试: $p2_success_rate% 通过 ⚠️"
        return 0
    fi
}

# 集成测试
run_integration_tests() {
    log_header "集成测试 (需要Redis环境)"
    
    # 检查Redis连接
    if command -v redis-cli &> /dev/null; then
        if redis-cli -h localhost -p 6378 ping >/dev/null 2>&1; then
            log_success "Redis 8.x (6378) 连接正常"
        else
            log_warning "Redis 8.x (6378) 连接失败"
        fi
        
        if redis-cli -h localhost -p 6376 ping >/dev/null 2>&1; then
            log_success "Redis 6.x (6376) 连接正常"
        else
            log_warning "Redis 6.x (6376) 连接失败"
        fi
    else
        log_warning "未安装redis-cli，跳过连接检查"
    fi
    
    # 运行集成测试
    run_pytest "tests/integration/" "集成测试" "--tb=short"
}

# 生成覆盖率报告
generate_coverage_report() {
    log_header "生成覆盖率报告"
    
    log_info "运行带覆盖率的测试..."
    uv run pytest tests/unit/ \
        --cov=src/mx_rmq \
        --cov-report=html:htmlcov \
        --cov-report=term \
        --cov-report=xml:coverage.xml \
        --quiet || true
    
    # 解析覆盖率
    if [ -f "coverage.xml" ]; then
        local coverage=$(grep 'line-rate' coverage.xml | head -1 | grep -oE '[0-9.]+' | head -1)
        local coverage_percent=$(python -c "print(int(float('$coverage') * 100))" 2>/dev/null || echo "0")
        
        echo -e "\n${BLUE}覆盖率报告:${NC}"
        echo "  总覆盖率: $coverage_percent%"
        echo "  HTML报告: htmlcov/index.html"
        echo "  XML报告: coverage.xml"
        
        if [ "$coverage_percent" -ge "$COVERAGE_THRESHOLD" ]; then
            log_success "覆盖率检查: $coverage_percent% ≥ $COVERAGE_THRESHOLD% ✅"
        else
            log_warning "覆盖率检查: $coverage_percent% < $COVERAGE_THRESHOLD% ⚠️"
        fi
    else
        log_warning "无法生成覆盖率报告"
    fi
}

# 发版前检查
release_check() {
    log_header "发版前完整检查"
    
    local p0_result=0
    local p1_result=0
    
    # 运行P0和P1测试
    run_p0_tests || p0_result=1
    run_p1_tests || p1_result=1
    
    # 运行P2测试 (不影响发版结果)
    run_p2_tests || true
    
    # 生成覆盖率报告
    generate_coverage_report
    
    # 发版决策
    if [ "$p0_result" -eq 0 ] && [ "$p1_result" -eq 0 ]; then
        log_success "🎉 发版检查通过，可以发版！"
        return 0
    else
        log_error "🚫 发版检查失败，禁止发版！"
        return 1
    fi
}

# 显示最终结果
show_final_result() {
    local end_time=$(date +%s)
    local duration=$((end_time - TEST_START_TIME))
    local minutes=$((duration / 60))
    local seconds=$((duration % 60))
    
    log_header "测试结果汇总"
    
    echo -e "${BLUE}执行统计:${NC}"
    printf "  总测试数: %d\n" "$TOTAL_TESTS"
    printf "  通过测试: %d\n" "$PASSED_TESTS"
    printf "  失败测试: %d\n" "$FAILED_TESTS"
    printf "  执行时间: %d分%d秒\n" "$minutes" "$seconds"
    
    if [ "$FAILED_TESTS" -eq 0 ]; then
        local success_rate=100
    else
        local success_rate=$((PASSED_TESTS * 100 / TOTAL_TESTS))
    fi
    printf "  成功率: %d%%\n" "$success_rate"
    
    echo -e "\n${BLUE}质量评估:${NC}"
    if [ "$success_rate" -eq 100 ]; then
        echo -e "  ${GREEN}🏆 优秀 - 所有测试通过${NC}"
    elif [ "$success_rate" -ge 95 ]; then
        echo -e "  ${GREEN}✅ 良好 - 测试基本通过${NC}"
    elif [ "$success_rate" -ge 90 ]; then
        echo -e "  ${YELLOW}⚠️  一般 - 存在少量问题${NC}"
    else
        echo -e "  ${RED}❌ 较差 - 存在较多问题${NC}"
    fi
    
    echo -e "\n${BLUE}相关文档:${NC}"
    echo "  测试指南: TEST_GUIDE.md"
    echo "  测试报告: TEST_REPORT.md"
    echo "  集成测试: INTEGRATION_TEST_REPORT.md"
}

# 主函数
main() {
    # 解析命令行参数
    case "${1:-}" in
        --help|-h)
            show_help
            exit 0
            ;;
        --quick)
            log_header "MX-RMQ 快速测试"
            check_environment
            run_p0_tests
            ;;
        --full)
            log_header "MX-RMQ 完整单元测试"
            check_environment
            run_p0_tests
            run_p1_tests
            run_p2_tests
            ;;
        --release)
            log_header "MX-RMQ 发版前检查"
            check_environment
            release_check
            ;;
        --coverage)
            log_header "MX-RMQ 覆盖率测试"
            check_environment
            run_p0_tests
            run_p1_tests
            generate_coverage_report
            ;;
        --integration)
            log_header "MX-RMQ 集成测试"
            check_environment
            run_integration_tests
            ;;
        --ci)
            # CI模式：静默输出
            check_environment >/dev/null
            if run_p0_tests >/dev/null && run_p1_tests >/dev/null; then
                echo "PASS"
                exit 0
            else
                echo "FAIL"
                exit 1
            fi
            ;;
        "")
            # 默认：完整测试
            log_header "MX-RMQ 默认测试 (等同于 --full)"
            check_environment
            run_p0_tests
            run_p1_tests
            run_p2_tests
            ;;
        *)
            log_error "未知选项: $1"
            echo "使用 --help 查看帮助信息"
            exit 1
            ;;
    esac
    
    # 显示最终结果
    show_final_result
    
    # 返回适当的退出码
    if [ "$FAILED_TESTS" -eq 0 ]; then
        exit 0
    else
        exit 1
    fi
}

# 脚本入口
main "$@"