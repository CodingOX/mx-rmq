"""
队列上下文类 - 封装所有共享状态和依赖
"""

import asyncio
from collections.abc import Callable
from typing import Any

import redis.asyncio as aioredis
from redis.commands.core import AsyncScript

from ..config import MQConfig
from ..constants import GlobalKeys, TopicKeys
from ..logging import LoggerService


class QueueContext:
    """队列核心上下文 - 封装所有共享状态和依赖"""

    def __init__(
        self,
        config: MQConfig,
        redis: aioredis.Redis,
        logger_service: LoggerService,
        lua_scripts: dict[str, AsyncScript],
    ) -> None:
        """
        初始化上下文

        Args:
            config: 消息队列配置
            redis: Redis 连接
            logger_service: 日志服务
            lua_scripts: Lua 脚本字典
        """
        self.config = config
        self.redis = redis
        self.logger_service = logger_service
        self.lua_scripts = lua_scripts

        # 消息处理器
        self.handlers: dict[str, Callable] = {}

        # 运行状态
        self.running = False
        self.shutting_down = False
        self.initialized = False

        # 监控相关
        self.stuck_messages_tracker: dict[str, dict[str, int]] = {}

        # 活跃任务管理
        self.active_tasks: set[asyncio.Task] = set()
        self.shutdown_event = asyncio.Event()

    # 便捷属性，直接访问logger
    @property
    def logger(self):
        """获取logger，保持向后兼容"""
        return self.logger_service.logger

    def is_running(self) -> bool:
        """检查是否正在运行"""
        return self.running and not self.shutting_down

    def register_handler(self, topic: str, handler: Callable) -> None:
        """
        注册消息处理器

        Args:
            topic: 主题名称
            handler: 处理函数
        """
        if not callable(handler):
            raise ValueError("处理器必须是可调用对象")

        self.handlers[topic] = handler
        self.logger_service.logger.info(
            "消息处理器注册成功", topic=topic, handler=handler.__name__
        )

    def log_error(self, message: str, error: Exception, **kwargs) -> None:
        """记录错误日志"""
        self.logger_service.log_error(message, error, **kwargs)

    def log_message_event(
        self, event: str, message_id: str, topic: str, **kwargs
    ) -> None:
        """记录消息事件"""
        self.logger_service.log_message_event(event, message_id, topic, **kwargs)

    def get_global_key(self, key: GlobalKeys) -> str:
        """
        获取全局键名，自动添加队列前缀

        Args:
            key: 全局键名枚举

        Returns:
            带前缀的键名
        """
        if self.config.queue_prefix:
            return f"{self.config.queue_prefix}:{key.value}"
        return key.value

    def get_topic_key(self, topic: str, suffix: TopicKeys) -> str:
        """
        获取主题相关键名，自动添加队列前缀

        Args:
            topic: 主题名称
            suffix: 键后缀枚举

        Returns:
            带前缀的主题键名
        """
        if self.config.queue_prefix:
            return f"{self.config.queue_prefix}:{topic}:{suffix.value}"
        return f"{topic}:{suffix.value}"

    def log_metric(self, metric_name: str, value: Any, **kwargs) -> None:
        """记录指标"""
        self.logger_service.log_metric(metric_name, value, **kwargs)
