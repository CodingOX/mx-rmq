"""
MX-RMQ: 基于Redis的高性能异步消息队列
重构版本 - 完全组合模式
"""

from .config import MQConfig
from .constants import GlobalKeys, TopicKeys, KeyNamespace
from .core import QueueContext
from .log_config import (
    setup_logger,
    setup_simple_logger,
    setup_production_logger,
    configure_mx_rmq_logging,
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
    # 日志配置
    "setup_logger",
    "setup_simple_logger",
    "setup_production_logger",
    "configure_mx_rmq_logging",
    # Redis键名常量
    "GlobalKeys",
    "TopicKeys",
    "KeyNamespace",
    # 监控相关
    "MetricsCollector",
    "QueueMetrics",
    "ProcessingMetrics",
    # 内部组件（高级用法，仅用于扩展开发）
    "QueueContext",
]
