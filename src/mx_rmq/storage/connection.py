"""
Redis连接管理模块
负责创建和管理Redis连接池和连接
"""

import redis.asyncio as aioredis

from ..config import MQConfig
from ..logging import LoggerService


class RedisConnectionManager:
    """Redis连接管理器"""

    def __init__(self, config: MQConfig, logger_service: LoggerService) -> None:
        """
        初始化连接管理器

        Args:
            config: 消息队列配置
            logger_service: 日志服务实例
        """
        self.config = config
        self.logger_service = logger_service
        self.redis_pool: aioredis.ConnectionPool | None = None
        self.redis: aioredis.Redis | None = None

    async def initialize_connection(self) -> aioredis.Redis:
        """
        初始化Redis连接

        Returns:
            Redis连接实例
        """
        # 创建Redis连接池
        self.redis_pool = aioredis.ConnectionPool.from_url(
            self.config.redis_url,
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
        self.logger_service.logger.info(
            "Redis连接建立成功", redis_url=self.config.redis_url
        )

        return self.redis

    async def cleanup(self) -> None:
        """清理连接资源"""
        try:
            if self.redis_pool:
                await self.redis_pool.disconnect()
                self.logger_service.logger.info("Redis连接池已关闭")
        except Exception as e:
            self.logger_service.log_error("清理Redis连接时出错", e)
