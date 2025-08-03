"""
Redis连接管理模块
负责创建和管理Redis连接池和连接
"""

import asyncio

import redis.asyncio as aioredis
from loguru import logger

from ..config import MQConfig


class RedisConnectionManager:
    """Redis连接管理器"""

    def __init__(self, config: MQConfig) -> None:
        self.config = config
        self.redis_pool: aioredis.ConnectionPool | None = None
        self.redis: aioredis.Redis | None = None
        self._initialized = False  # 添加初始化标志
        self._lock = asyncio.Lock()  # 添加异步锁
        self.redis_version: tuple[int, int, int] | None = (
            None  # Redis版本信息 7.4.0 那么就是  7 4 0
        )
        self.supports_hexpire = False  # 是否支持HEXPIRE

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
            self.redis_pool = aioredis.ConnectionPool(
                host=self.config.redis_host,
                port=self.config.redis_port,
                password=self.config.redis_password,
                max_connections=self.config.redis_max_connections,
                db=self.config.redis_db,
                decode_responses=True,
                socket_keepalive=True,
                socket_keepalive_options={},
                health_check_interval=30,
            )

            self.redis = aioredis.Redis(connection_pool=self.redis_pool)

            # 测试连接
            await self.redis.ping()

            # 检测Redis版本和特性支持
            await self._detect_redis_features()

            self._initialized = True  # 标记为已初始化
            logger.info(
                f"Redis连接建立成功 - redis_url={self.config.redis_host}, "
                f"version={'.'.join(map(str, self.redis_version)) if self.redis_version else 'unknown'}, "
                f"supports_hexpire={self.supports_hexpire}"
            )

            return self.redis

    async def _detect_redis_features(self) -> None:
        """检测Redis版本和特性支持"""
        try:
            if not self.redis:
                return

            # 获取Redis版本信息
            info = await self.redis.info("server")
            version_str = info.get("redis_version", "0.0.0")

            # 解析版本号 (如 "7.4.0" -> (7, 4, 0))
            version_parts = version_str.split(".")
            if len(version_parts) >= 3:
                self.redis_version = (
                    int(version_parts[0]),
                    int(version_parts[1]),
                    int(version_parts[2]),
                )
            else:
                self.redis_version = (int(version_parts[0]), int(version_parts[1]), 0)

            # 检测HEXPIRE支持 (Redis 7.4+)
            if self.redis_version >= (7, 4, 0):
                self.supports_hexpire = True
            else:
                self.supports_hexpire = False
                logger.warning(
                    f"Redis版本 {version_str} 不支持HEXPIRE命令，"
                    f"错误队列将使用整体过期策略"
                )

        except Exception as e:
            logger.warning(f"检测Redis特性时出错: {e}")
            self.redis_version = None
            self.supports_hexpire = False

    async def cleanup(self) -> None:
        """清理连接资源"""
        try:
            if self.redis_pool:
                await self.redis_pool.disconnect()
                logger.info("Redis连接池已关闭")
        except Exception as e:
            logger.exception("清理Redis连接时出错")

    @property
    def is_connected(self) -> bool:
        """检查是否已连接"""
        return self.redis is not None and self.redis_pool is not None
