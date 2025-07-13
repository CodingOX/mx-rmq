"""
日志子系统
提供统一的日志接口和多后端支持
"""

from .facade import LoggerAdapter, LoggerFactory, get_logger
from .integrations import (
    auto_configure_logging,
    get_available_backends,
    setup_loguru_integration,
    setup_structlog_integration,
    setup_standard_logging,
)
from .service import LoggerService, get_logger_instance, setup_logging

__all__ = [
    # 门面接口
    "LoggerAdapter",
    "LoggerFactory",
    "get_logger",
    # 服务接口
    "LoggerService",
    "setup_logging",
    "get_logger_instance",
    # 集成函数
    "auto_configure_logging",
    "get_available_backends",
    "setup_loguru_integration",
    "setup_structlog_integration",
    "setup_standard_logging",
]
