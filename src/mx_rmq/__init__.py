"""
MX-RMQ: 基于Redis的高性能异步消息队列
重构版本 - 完全组合模式
"""

from .config import MQConfig
from .constants import GlobalKeys, TopicKeys, KeyNamespace
from .core import (
    ConsumerService,
    DispatchService,
    MessageLifecycleService,
    ScheduleService,
    QueueContext,
)
from .logging import (
    LoggerService,
    setup_logging,
    get_logger_instance,
    LoggerFactory,
    get_logger,
    auto_configure_logging,
    get_available_backends,
    setup_loguru_integration,
    setup_structlog_integration,
    setup_standard_logging,
)
from .message import Message, MessageMeta, MessagePriority, MessageStatus
from .monitoring import MetricsCollector, QueueMetrics, ProcessingMetrics
from .queue import RedisMessageQueue

__version__ = "3.0.0"

__all__ = [
    # 核心组件
    "RedisMessageQueue",
    "MQConfig",
    "Message",
    "MessagePriority",
    "MessageStatus",
    "MessageMeta",
    # Redis键名常量
    "GlobalKeys",
    "TopicKeys",
    "KeyNamespace",
    # 日志相关
    "LoggerService",
    "LoggerFactory",
    "get_logger",
    "setup_logging",
    "get_logger_instance",
    # 日志集成函数
    "auto_configure_logging",
    "get_available_backends",
    "setup_loguru_integration",
    "setup_structlog_integration",
    "setup_standard_logging",
    # 监控相关
    "MetricsCollector",
    "QueueMetrics",
    "ProcessingMetrics",
    # 内部组件（高级用法）
    "QueueContext",
    "ConsumerService",
    "MessageLifecycleService",
    "ScheduleService",
    "DispatchService",
]
