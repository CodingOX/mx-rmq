"""
Redis连接管理模块
负责创建和管理Redis连接池和连接
"""
import asyncio

import redis.asyncio as aioredis

from ..config import MQConfig
import logging


class RedisConnectionManager:
    """Redis连接管理器"""

    def __init__(self, config: MQConfig, logger: logging.Logger | None = None) -> None:
        self.config = config
        self._logger = logger or logging.getLogger("mx_rmq.storage.connection")
        self.redis_pool: aioredis.ConnectionPool | None = None
        self.redis: aioredis.Redis | None = None
        self._initialized = False  # 添加初始化标志
        self._lock = asyncio.Lock()  # 添加异步锁

    async def initialize_connection(self) -> aioredis.Redis:
        """
        初始化Redis连接（只初始化一次）

        Returns:
            Redis连接实例
        """
        # 如果已经初始化，直接返回
        if self._initialized and self.redis:
            return self.redis

        async with self._lock:  # 使用锁防止并发初始化
            # 双重检查
            if self._initialized and self.redis:
                return self.redis

            # 创建Redis连接池
            self.redis_pool = aioredis.ConnectionPool.from_url(
                self.config.redis_host,
                password=self.config.redis_password,
                max_connections=self.config.connection_pool_size,
                db=self.config.redis_db,
                decode_responses=True,
                socket_keepalive=True,
                socket_keepalive_options={},
                health_check_interval=30,
            )

            self.redis = aioredis.Redis(connection_pool=self.redis_pool)

            # 测试连接
            await self.redis.ping()
            self._initialized = True  # 标记为已初始化
            self._logger.info(f"Redis连接建立成功 - redis_url={self.config.redis_host}")

            return self.redis

    async def cleanup(self) -> None:
        """清理连接资源"""
        try:
            if self.redis_pool:
                await self.redis_pool.disconnect()
                self._logger.info("Redis连接池已关闭")
        except Exception as e:
            self._logger.error("清理Redis连接时出错", exc_info=e)

    @property
    def is_connected(self) -> bool:
        """检查是否已连接"""
        return self.redis is not None and self.redis_pool is not None
