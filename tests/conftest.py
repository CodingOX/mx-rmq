"""pytest配置文件"""

import asyncio
import time
from unittest.mock import AsyncMock

import pytest

from mx_rmq.config import MQConfig
from mx_rmq.message import Message, MessageMeta, MessagePriority, MessageStatus


@pytest.fixture(scope="session")
def event_loop():
    """创建事件循环用于异步测试"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def test_config():
    """测试用配置"""
    return MQConfig(
        redis_url="redis://localhost:6379",
        redis_db=15,  # 使用测试数据库
        max_workers=2,
        task_queue_size=5,
        message_ttl=3600,
        processing_timeout=60,
        max_retries=2,
        retry_delays=[10, 30],
        monitor_interval=5,
        log_level="DEBUG",
    )


@pytest.fixture
def sample_message():
    """示例消息"""
    return Message(
        topic="test.topic",
        payload={"user_id": 123, "action": "test"},
        priority=MessagePriority.NORMAL,
    )


@pytest.fixture
def sample_message_meta():
    """示例消息元数据"""
    return MessageMeta(
        expire_at=int(time.time() * 1000) + 3600000,
        max_retries=3,
        retry_delays=[60, 300, 1800],
    )


@pytest.fixture
def mock_redis():
    """模拟Redis连接"""
    redis_mock = AsyncMock()

    # 设置常用的返回值
    redis_mock.ping.return_value = True
    redis_mock.eval.return_value = None
    redis_mock.hget.return_value = None
    redis_mock.hgetall.return_value = {}
    redis_mock.llen.return_value = 0
    redis_mock.lrange.return_value = []
    redis_mock.zcard.return_value = 0
    redis_mock.zrange.return_value = []
    redis_mock.info.return_value = {"redis_version": "6.0.0"}
    redis_mock.close.return_value = None

    return redis_mock


@pytest.fixture
def mock_lua_scripts():
    """模拟Lua脚本返回值"""
    return {
        "produce_normal": "msg-123",
        "produce_delay": "delay-msg-456",
        "complete_message": 1,
        "retry_message": 1,
        "move_to_dlq": 1,
        "process_delay_messages": 0,
        "handle_timeout_messages": 0,
    }


@pytest.fixture
def sample_messages():
    """多个示例消息"""
    messages = []
    for i in range(5):
        message = Message(
            topic=f"test.topic.{i}",
            payload={"index": i, "data": f"test-{i}"},
            priority=MessagePriority.NORMAL if i % 2 == 0 else MessagePriority.HIGH,
        )
        messages.append(message)
    return messages


@pytest.fixture
def message_with_retry():
    """带重试信息的消息"""
    message = Message(topic="retry.test", payload={"retry": True})
    # 模拟已重试的状态
    message.mark_retry("Test error")
    return message


@pytest.fixture
def expired_message():
    """过期消息"""
    expired_meta = MessageMeta(
        expire_at=int(time.time() * 1000) - 3600000,  # 1小时前过期
        max_retries=3,
    )
    return Message(topic="expired.test", payload={"expired": True}, meta=expired_meta)


def pytest_configure(config):
    """pytest配置"""
    # 添加自定义标记
    config.addinivalue_line("markers", "asyncio: 标记异步测试函数")
    config.addinivalue_line("markers", "integration: 标记集成测试")
    config.addinivalue_line("markers", "unit: 标记单元测试")
    config.addinivalue_line("markers", "slow: 标记慢速测试")


def pytest_collection_modifyitems(config, items):
    """修改测试项配置"""
    # 为异步测试添加asyncio标记
    for item in items:
        if asyncio.iscoroutinefunction(item.function):
            item.add_marker(pytest.mark.asyncio)


@pytest.fixture(autouse=True)
def cleanup_after_test():
    """测试后自动清理"""
    yield
    # 清理逻辑可以在这里添加
    pass
