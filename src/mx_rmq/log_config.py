"""
Loguru 日志配置模块
提供统一的日志配置接口，替代原有的 logging 子系统
"""

import sys
from typing import Any
from loguru import logger


def setup_logger(
    level: str = "INFO",
    include_location: bool = True,
    colorized: bool = True,
    log_file: str | None = None,
    **kwargs: Any,
) -> None:
    """
    配置 loguru 日志器

    Args:
        level: 日志级别 (TRACE, DEBUG, INFO, SUCCESS, WARNING, ERROR, CRITICAL)
        include_location: 是否包含文件位置信息（文件名、行号、函数名）
        colorized: 是否启用彩色输出
        log_file: 日志文件路径，如果提供则同时输出到文件
        **kwargs: 其他配置参数

    Examples:
        >>> from mx_rmq.log_config import setup_logger
        >>> setup_logger("INFO")  # 配置基本日志输出
        >>> setup_logger("DEBUG", include_location=True)  # 开发环境配置
        >>> setup_logger("INFO", include_location=False, log_file="app.log")  # 生产环境配置
    """
    # 移除默认的 handler
    logger.remove()

    # 根据参数构建格式字符串
    if include_location:
        # 开发环境格式：包含详细位置信息
        format_string = (
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
            "<level>{message}</level>"
        )
    else:
        # 生产环境格式：简洁格式
        format_string = (
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan> - "
            "<level>{message}</level>"
        )

    # 添加控制台输出
    logger.add(
        sys.stdout,
        format=format_string,
        level=level.upper(),
        colorize=colorized,
        backtrace=True,
        diagnose=True,
        **kwargs,
    )

    # 如果指定了日志文件，添加文件输出
    if log_file:
        # 文件输出不使用颜色
        file_format = format_string.replace("<green>", "").replace("</green>", "")
        file_format = file_format.replace("<level>", "").replace("</level>", "")
        file_format = file_format.replace("<cyan>", "").replace("</cyan>", "")

        logger.add(
            log_file,
            format=file_format,
            level=level.upper(),
            rotation="10 MB",
            retention="7 days",
            compression="zip",
            backtrace=True,
            diagnose=True,
        )


def setup_simple_logger(level: str = "INFO") -> None:
    """
    配置简洁的日志输出（不显示时间戳，适合命令行工具）

    Args:
        level: 日志级别

    Examples:
        >>> from mx_rmq.log_config import setup_simple_logger
        >>> setup_simple_logger("INFO")
    """
    logger.remove()

    format_string = (
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
        "<level>{message}</level>"
    )

    logger.add(
        sys.stdout,
        format=format_string,
        level=level.upper(),
        colorize=True,
        backtrace=True,
        diagnose=True,
    )


def setup_production_logger(level: str = "INFO", log_file: str = "mx_rmq.log") -> None:
    """
    配置生产环境日志（JSON 格式，便于日志收集）

    Args:
        level: 日志级别
        log_file: 日志文件路径

    Examples:
        >>> from mx_rmq.log_config import setup_production_logger
        >>> setup_production_logger("INFO", "/var/log/mx_rmq.log")
    """
    logger.remove()

    # 控制台输出：简洁格式
    logger.add(
        sys.stdout,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan> - "
            "<level>{message}</level>"
        ),
        level=level.upper(),
        colorize=True,
    )

    # 文件输出：JSON 格式
    logger.add(
        log_file,
        format="{time} | {level} | {name}:{function}:{line} | {message}",
        level=level.upper(),
        rotation="50 MB",
        retention="30 days",
        compression="zip",
        serialize=True,  # JSON 格式
        backtrace=True,
        diagnose=True,
    )


# 便捷的配置函数，用于快速配置
def configure_mx_rmq_logging(
    level: str = "INFO", environment: str = "development"
) -> None:
    """
    mx-rmq 项目的标准日志配置

    Args:
        level: 日志级别
        environment: 环境类型 ("development", "production", "testing")
    """
    if environment == "development":
        setup_logger(level=level, include_location=True, colorized=True)
    elif environment == "production":
        setup_production_logger(level=level)
    elif environment == "testing":
        setup_simple_logger(level=level)
    else:
        setup_logger(level=level, include_location=False, colorized=True)


__all__ = [
    "setup_logger",
    "setup_simple_logger",
    "setup_production_logger",
    "configure_mx_rmq_logging",
]
