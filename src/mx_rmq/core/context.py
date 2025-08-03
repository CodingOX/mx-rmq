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


class QueueContext:
    """队列核心上下文 - 封装所有共享状态和依赖"""

    def __init__(
        self,
        config: MQConfig,
        redis: aioredis.Redis,
        lua_scripts: dict[str, AsyncScript],
    ) -> None:
        """
        初始化上下文

        Args:
            config: 消息队列配置
            redis: Redis 连接
            lua_scripts: Lua 脚本字典
        """
        self.config = config
        self.redis = redis
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
        from loguru import logger

        if not callable(handler):
            raise ValueError("处理器必须是可调用对象")

        self.handlers[topic] = handler
        logger.info(f"消息处理器注册成功, topic={topic}, handler={handler.__name__}")

    def get_global_key(self, key: GlobalKeys | str) -> str:
        """
        获取全局键名，自动添加队列前缀

        Args:
            key: 全局键名枚举或字符串

        Returns:
            带前缀的键名
        """
        key_value = key.value if isinstance(key, GlobalKeys) else key
        if self.config.queue_prefix:
            return f"{self.config.queue_prefix}:{key_value}"
        return key_value

    def get_global_topic_key(self, topic: str, suffix: TopicKeys) -> str:
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
