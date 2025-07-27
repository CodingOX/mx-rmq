"""
MX-RMQ: 基于Redis的高性能异步消息队列
重构版本 - 完全组合模式
"""

from .config import MQConfig
from .constants import GlobalKeys, TopicKeys, KeyNamespace
from .core import QueueContext
from .logging import LoggerService, setup_colored_logging, setup_simple_colored_logging
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
    # 向后兼容的日志服务
    "LoggerService",
    # 彩色日志配置
    "setup_colored_logging",
    "setup_simple_colored_logging",
    # 监控相关
    "MetricsCollector",
    "QueueMetrics",
    "ProcessingMetrics",
    # 内部组件（高级用法，仅用于扩展开发）
    "QueueContext",
]
