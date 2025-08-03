@echo off
REM MX-RMQ Windows 测试脚本
REM 使用方法: run_tests.bat [选项]

setlocal EnableDelayedExpansion

REM 颜色定义(在Windows上需要ANSI支持)
set "GREEN=[32m"
set "RED=[31m"
set "YELLOW=[33m"
set "BLUE=[34m"
set "NC=[0m"

REM 显示帮助
if "%1"=="--help" (
    echo MX-RMQ Windows 测试脚本
    echo.
    echo 使用方法:
    echo     run_tests.bat [选项]
    echo.
    echo 选项:
    echo     --quick     快速测试 (P0核心功能)
    echo     --full      完整单元测试
    echo     --release   发版前完整检查
    echo     --help      显示帮助信息
    echo.
    echo 示例:
    echo     run_tests.bat --quick
    echo     run_tests.bat --full
    echo     run_tests.bat --release
    goto :eof
)

echo ================================
echo    MX-RMQ 测试脚本 (Windows)
echo ================================

REM 检查Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo %RED%❌ 错误: 未找到Python%NC%
    exit /b 1
)

REM 检查uv
uv --version >nul 2>&1
if %errorlevel% neq 0 (
    echo %RED%❌ 错误: 需要安装uv包管理器%NC%
    exit /b 1
)

REM 检查项目文件
if not exist "pyproject.toml" (
    echo %RED%❌ 错误: 未找到pyproject.toml文件%NC%
    exit /b 1
)

echo %GREEN%✅ 环境检查通过%NC%

REM 同步依赖
echo 正在同步依赖...
uv sync --quiet
if %errorlevel% neq 0 (
    echo %RED%❌ 依赖同步失败%NC%
    exit /b 1
)

REM 根据参数执行不同测试
if "%1"=="--quick" (
    echo.
    echo ================================
    echo      P0 核心功能快速测试
    echo ================================
    uv run pytest tests/unit/test_config.py tests/unit/test_message.py tests/unit/test_queue.py -v --tb=short
) else if "%1"=="--full" (
    echo.
    echo ================================
    echo        完整单元测试
    echo ================================
    uv run pytest tests/unit/ -v --tb=short
) else if "%1"=="--release" (
    echo.
    echo ================================
    echo        发版前完整检查
    echo ================================
    echo 执行P0核心功能测试...
    uv run pytest tests/unit/test_config.py tests/unit/test_message.py tests/unit/test_queue.py tests/unit/test_storage.py tests/unit/test_lifecycle.py tests/unit/test_shutdown.py -v
    if %errorlevel% neq 0 (
        echo %RED%❌ P0测试失败，禁止发版！%NC%
        exit /b 1
    )
    
    echo.
    echo 执行P1重要功能测试...
    uv run pytest tests/unit/test_monitoring.py tests/unit/test_consumer.py -v
    if %errorlevel% neq 0 (
        echo %YELLOW%⚠️ P1测试存在问题，请检查%NC%
    )
    
    echo %GREEN%🎉 发版前检查完成%NC%
) else (
    echo.
    echo ================================
    echo      默认完整单元测试
    echo ================================
    uv run pytest tests/unit/ -v --tb=short
)

if %errorlevel% equ 0 (
    echo.
    echo %GREEN%✅ 测试完成，结果正常%NC%
) else (
    echo.
    echo %RED%❌ 测试完成，发现问题%NC%
    exit /b 1
)

echo.
echo 相关文档:
echo   测试指南: TEST_GUIDE.md
echo   测试报告: TEST_REPORT.md
echo   集成测试: INTEGRATION_TEST_REPORT.md