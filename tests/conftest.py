"""
pytest配置文件和共享fixtures
"""

import asyncio
import pytest
# import pytest_asyncio
import redis.asyncio as aioredis
from typing import AsyncGenerator

from mx_rmq.config import MQConfig


# Redis测试配置
TEST_REDIS_CONFIGS = {
    "redis_v8": {
        "host": "localhost",
        "port": 6378,
        "db": 1,  # 使用独立测试数据库
        "decode_responses": True
    },
    "redis_v6": {
        "host": "localhost",
        "port": 6376,
        "db": 1,
        "decode_responses": True
    }
}


@pytest.fixture(scope="session")
def event_loop():
    """创建事件循环用于整个测试会话"""
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def redis_v8_client() -> AsyncGenerator[aioredis.Redis, None]:
    """Redis 8.x 测试客户端"""
    client = aioredis.Redis(**TEST_REDIS_CONFIGS["redis_v8"])
    try:
        # 测试连接
        await client.ping()
        yield client
    finally:
        # 清理测试数据
        await client.flushdb()
        await client.aclose()


@pytest.fixture(scope="session")
async def redis_v6_client() -> AsyncGenerator[aioredis.Redis, None]:
    """Redis 6.x 测试客户端"""
    client = aioredis.Redis(**TEST_REDIS_CONFIGS["redis_v6"])
    try:
        # 测试连接
        await client.ping()
        yield client
    finally:
        # 清理测试数据
        await client.flushdb()
        await client.aclose()


@pytest.fixture
def test_config_v8() -> MQConfig:
    """Redis 8.x 测试配置"""
    return MQConfig(
        redis_host=TEST_REDIS_CONFIGS["redis_v8"]["host"],
        redis_port=TEST_REDIS_CONFIGS["redis_v8"]["port"],
        redis_db=TEST_REDIS_CONFIGS["redis_v8"]["db"],
        queue_prefix="test_mq",
        max_retries=3,
        batch_size=10
    )


@pytest.fixture
def test_config_v6() -> MQConfig:
    """Redis 6.x 测试配置"""
    return MQConfig(
        redis_host=TEST_REDIS_CONFIGS["redis_v6"]["host"],
        redis_port=TEST_REDIS_CONFIGS["redis_v6"]["port"],
        redis_db=TEST_REDIS_CONFIGS["redis_v6"]["db"],
        queue_prefix="test_mq",
        max_retries=3,
        batch_size=10
    )


@pytest.fixture
async def clean_redis_v8(redis_v8_client: aioredis.Redis) -> AsyncGenerator[aioredis.Redis, None]:
    """每个测试前后清理Redis 8.x数据"""
    await redis_v8_client.flushdb()
    yield redis_v8_client
    await redis_v8_client.flushdb()


@pytest.fixture
async def clean_redis_v6(redis_v6_client: aioredis.Redis) -> AsyncGenerator[aioredis.Redis, None]:
    """每个测试前后清理Redis 6.x数据"""
    await redis_v6_client.flushdb()
    yield redis_v6_client
    await redis_v6_client.flushdb()


# pytest配置
def pytest_configure(config):
    """pytest配置"""
    config.addinivalue_line(
        "markers", "slow: 标记运行时间较长的测试"
    )
    config.addinivalue_line(
        "markers", "integration: 标记集成测试"
    )
    config.addinivalue_line(
        "markers", "redis_v8: 标记需要Redis 8.x的测试"
    )
    config.addinivalue_line(
        "markers", "redis_v6: 标记需要Redis 6.x的测试"
    )
    config.addinivalue_line(
        "markers", "real_redis: 标记需要真实Redis环境的测试"
    )


def pytest_collection_modifyitems(config, items):
    """修改测试收集项"""
    for item in items:
        # 为慢速测试添加超时
        if item.get_closest_marker("slow"):
            item.add_marker(pytest.mark.timeout(30))
        
        # 为集成测试添加超时
        if item.get_closest_marker("integration"):
            item.add_marker(pytest.mark.timeout(60))