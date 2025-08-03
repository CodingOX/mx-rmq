"""
Redis相关的测试fixtures
"""

import asyncio
from typing import AsyncGenerator, Callable, Any
import pytest
import pytest_asyncio
import redis.asyncio as aioredis
from unittest.mock import AsyncMock

from mx_rmq import RedisMessageQueue, MQConfig


@pytest_asyncio.fixture
async def redis_queue_v8(
    test_config_v8: MQConfig,
    clean_redis_v8: aioredis.Redis
) -> AsyncGenerator[RedisMessageQueue, None]:
    """Redis 8.x 消息队列实例"""
    queue = RedisMessageQueue(test_config_v8)
    try:
        await queue.start()
        yield queue
    finally:
        await queue.stop()


@pytest_asyncio.fixture
async def redis_queue_v6(
    test_config_v6: MQConfig,
    clean_redis_v6: aioredis.Redis
) -> AsyncGenerator[RedisMessageQueue, None]:
    """Redis 6.x 消息队列实例"""
    queue = RedisMessageQueue(test_config_v6)
    try:
        await queue.start()
        yield queue
    finally:
        await queue.stop()


@pytest.fixture
def mock_message_handler() -> Callable[[Any], Any]:
    """模拟消息处理器"""
    async def handler(message: Any) -> bool:
        """成功处理消息的模拟处理器"""
        return True
    return handler


@pytest.fixture
def mock_failing_handler() -> Callable[[Any], Any]:
    """模拟失败的消息处理器"""
    async def handler(message: Any) -> bool:
        """总是失败的模拟处理器"""
        raise ValueError("模拟处理失败")
    return handler


@pytest.fixture
def mock_slow_handler() -> Callable[[Any], Any]:
    """模拟慢速消息处理器"""
    async def handler(message: Any) -> bool:
        """慢速处理的模拟处理器"""
        await asyncio.sleep(0.1)  # 模拟耗时处理
        return True
    return handler


@pytest.fixture
def mock_conditional_handler() -> Callable[[Any], Any]:
    """模拟条件处理器"""
    async def handler(message: Any) -> bool:
        """根据消息内容决定成功或失败"""
        if hasattr(message, 'data') and message.data.get('should_fail'):
            raise ValueError("条件失败")
        return True
    return handler


@pytest_asyncio.fixture
async def isolated_redis_v8(test_config_v8: MQConfig) -> AsyncGenerator[aioredis.Redis, None]:
    """独立的Redis 8.x客户端，用于验证队列状态"""
    redis_config = {
        "host": test_config_v8.redis_host,
        "port": test_config_v8.redis_port,
        "db": test_config_v8.redis_db,
        "password": test_config_v8.redis_password,
        "decode_responses": True
    }
    client = aioredis.Redis(**redis_config)
    try:
        await client.ping()
        yield client
    finally:
        await client.aclose()


@pytest_asyncio.fixture
async def isolated_redis_v6(test_config_v6: MQConfig) -> AsyncGenerator[aioredis.Redis, None]:
    """独立的Redis 6.x客户端，用于验证队列状态"""
    redis_config = {
        "host": test_config_v6.redis_host,
        "port": test_config_v6.redis_port,
        "db": test_config_v6.redis_db,
        "password": test_config_v6.redis_password,
        "decode_responses": True
    }
    client = aioredis.Redis(**redis_config)
    try:
        await client.ping()
        yield client
    finally:
        await client.aclose()


class RedisTestHelper:
    """Redis测试辅助工具"""
    
    def __init__(self, redis_client: aioredis.Redis, config: MQConfig):
        self.redis = redis_client
        self.config = config
    
    async def get_queue_size(self, topic: str) -> int:
        """获取队列大小"""
        key = f"{self.config.queue_prefix}:queue:{topic}"
        return await self.redis.llen(key)  # type: ignore
    
    async def get_delay_queue_size(self, topic: str) -> int:
        """获取延时队列大小"""
        key = f"{self.config.queue_prefix}:delay:{topic}"
        return await self.redis.zcard(key)  # type: ignore
    
    async def get_dlq_size(self, topic: str) -> int:
        """获取死信队列大小"""
        key = f"{self.config.queue_prefix}:dlq:{topic}"
        return await self.redis.llen(key)  # type: ignore
    
    async def get_processing_queue_size(self, topic: str) -> int:
        """获取处理中队列大小"""
        key = f"{self.config.queue_prefix}:processing:{topic}"
        return await self.redis.hlen(key)  # type: ignore
    
    async def clear_all_queues(self) -> None:
        """清空所有队列"""
        pattern = f"{self.config.queue_prefix}:*"
        keys = await self.redis.keys(pattern)
        if keys:
            await self.redis.delete(*keys)


@pytest.fixture
def redis_helper_v8(clean_redis_v8: aioredis.Redis, test_config_v8: MQConfig) -> RedisTestHelper:
    """Redis 8.x 测试辅助工具"""
    return RedisTestHelper(clean_redis_v8, test_config_v8)


@pytest.fixture
def redis_helper_v6(clean_redis_v6: aioredis.Redis, test_config_v6: MQConfig) -> RedisTestHelper:
    """Redis 6.x 测试辅助工具"""
    return RedisTestHelper(clean_redis_v6, test_config_v6)