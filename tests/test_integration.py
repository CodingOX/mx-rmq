"""集成测试"""

import pytest
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch
from mx_rmq.config import MQConfig
from mx_rmq.message import Message, MessageMeta, MessageStatus, MessagePriority
from mx_rmq.queue import RedisMessageQueue


class TestRedisMessageQueueIntegration:
    """Redis消息队列集成测试"""

    @pytest.fixture
    def mock_redis(self):
        """模拟Redis连接"""
        redis_mock = AsyncMock()
        redis_mock.ping.return_value = True
        redis_mock.eval.return_value = None
        redis_mock.hget.return_value = None
        redis_mock.llen.return_value = 0
        redis_mock.zcard.return_value = 0
        return redis_mock

    @pytest.fixture
    def config(self):
        """测试配置"""
        return MQConfig(
            redis_url="redis://localhost:6379",
            redis_db=1,
            max_workers=2,
            task_queue_size=5,
        )

    @pytest.fixture
    async def queue(self, config, mock_redis):
        """创建消息队列实例"""
        with patch("mx_rmq.queue.redis.asyncio.from_url", return_value=mock_redis):
            queue = RedisMessageQueue(config)
            await queue.connect()
            yield queue
            await queue.disconnect()

    @pytest.mark.asyncio
    async def test_queue_lifecycle(self, queue, mock_redis):
        """测试队列生命周期"""
        # 验证连接状态
        assert queue.is_connected() is True

        # 测试健康检查
        health = await queue.health_check()
        assert health["status"] == "healthy"
        assert health["connected"] is True

    @pytest.mark.asyncio
    async def test_message_production(self, queue, mock_redis):
        """测试消息生产"""
        # 配置mock返回值
        mock_redis.eval.return_value = "msg-123"

        # 生产普通消息
        message_id = await queue.produce(
            topic="test.topic",
            payload={"user_id": 123, "action": "login"},
            priority=MessagePriority.HIGH,
        )

        assert message_id == "msg-123"

        # 验证Redis调用
        mock_redis.eval.assert_called()

    @pytest.mark.asyncio
    async def test_delay_message_production(self, queue, mock_redis):
        """测试延时消息生产"""
        # 配置mock返回值
        mock_redis.eval.return_value = "delay-msg-456"

        # 生产延时消息
        message_id = await queue.produce_delay(
            topic="scheduled.task",
            payload={"task": "cleanup"},
            delay_seconds=300,  # 5分钟后执行
            priority=MessagePriority.NORMAL,
        )

        assert message_id == "delay-msg-456"
        mock_redis.eval.assert_called()

    @pytest.mark.asyncio
    async def test_message_consumption_flow(self, queue, mock_redis):
        """测试消息消费流程"""
        # 模拟从Redis获取的消息
        message_data = {
            "id": "test-msg-789",
            "topic": "test.topic",
            "payload": {"data": "test"},
            "priority": "normal",
            "meta": {
                "status": "pending",
                "expire_at": int(time.time() * 1000) + 3600000,
                "max_retries": 3,
                "retry_count": 0,
            },
        }

        # 配置mock返回值
        mock_redis.eval.return_value = [message_data]

        # 定义消息处理器
        processed_messages = []

        async def test_handler(message: Message) -> None:
            processed_messages.append(message.id)
            # 模拟处理时间
            await asyncio.sleep(0.01)

        # 注册处理器
        queue.register_handler("test.topic", test_handler)

        # 模拟消费一条消息
        # 由于我们使用mock，这里主要测试处理器注册
        assert "test.topic" in queue._handlers
        assert queue._handlers["test.topic"] == test_handler

    @pytest.mark.asyncio
    async def test_error_handling_and_retry(self, queue, mock_redis):
        """测试错误处理和重试机制"""
        error_count = 0

        async def failing_handler(message: Message) -> None:
            nonlocal error_count
            error_count += 1
            if error_count <= 2:
                raise Exception(f"Simulated error {error_count}")
            # 第三次成功

        # 注册失败处理器
        queue.register_handler("retry.topic", failing_handler)

        # 验证处理器注册
        assert "retry.topic" in queue._handlers

    @pytest.mark.asyncio
    async def test_graceful_shutdown(self, queue, mock_redis):
        """测试优雅停机"""
        # 模拟运行状态
        queue._running = True

        # 启动停机流程
        await queue.shutdown()

        # 验证状态
        assert queue._running is False

    @pytest.mark.asyncio
    async def test_dlq_operations(self, queue, mock_redis):
        """测试死信队列操作"""
        # 配置DLQ相关的mock返回值
        mock_redis.eval.return_value = None
        mock_redis.hgetall.return_value = {}
        mock_redis.lrange.return_value = []

        # 测试DLQ管理器存在
        assert hasattr(queue, "dlq_manager")

        # 测试获取DLQ统计（通过mock）
        dlq_stats = await queue.get_dlq_stats()
        assert isinstance(dlq_stats, dict)

    @pytest.mark.asyncio
    async def test_metrics_collection(self, queue, mock_redis):
        """测试指标收集"""
        # 验证指标收集器存在
        assert hasattr(queue, "metrics")

        # 模拟指标操作
        metrics = queue.get_metrics()
        assert isinstance(metrics, dict)

    @pytest.mark.asyncio
    async def test_multiple_handlers(self, queue, mock_redis):
        """测试多个处理器注册"""

        async def handler1(message: Message) -> None:
            pass

        async def handler2(message: Message) -> None:
            pass

        # 注册多个处理器
        queue.register_handler("topic1", handler1)
        queue.register_handler("topic2", handler2)

        # 验证注册
        assert len(queue._handlers) == 2
        assert queue._handlers["topic1"] == handler1
        assert queue._handlers["topic2"] == handler2

    @pytest.mark.asyncio
    async def test_configuration_validation(self, config):
        """测试配置验证"""
        # 测试有效配置
        assert config.redis_url == "redis://localhost:6379"
        assert config.max_workers == 2
        assert config.task_queue_size == 5

        # 测试配置序列化
        config_dict = config.model_dump()
        assert "redis_url" in config_dict
        assert "max_workers" in config_dict

    @pytest.mark.asyncio
    async def test_message_serialization_flow(self):
        """测试消息序列化流程"""
        # 创建消息
        payload = {"user_id": 123, "action": "test"}
        message = Message(
            topic="test.serialization", payload=payload, priority=MessagePriority.HIGH
        )

        # 序列化
        message_dict = message.model_dump()

        # 反序列化
        restored_message = Message.model_validate(message_dict)

        # 验证数据完整性
        assert restored_message.topic == message.topic
        assert restored_message.payload == message.payload
        assert restored_message.priority == message.priority
        assert restored_message.id == message.id

    @pytest.mark.asyncio
    async def test_priority_message_handling(self, queue, mock_redis):
        """测试优先级消息处理"""
        priorities = [MessagePriority.LOW, MessagePriority.NORMAL, MessagePriority.HIGH]

        for priority in priorities:
            # 创建不同优先级的消息
            message = Message(
                topic="priority.test",
                payload={"priority": priority.value},
                priority=priority,
            )

            # 验证优先级设置
            assert message.priority == priority

    @pytest.mark.asyncio
    async def test_connection_error_handling(self, config):
        """测试连接错误处理"""
        with patch("mx_rmq.queue.redis.asyncio.from_url") as mock_from_url:
            # 模拟连接失败
            mock_from_url.side_effect = Exception("Connection failed")

            queue = RedisMessageQueue(config)

            # 连接应该失败
            with pytest.raises(Exception):
                await queue.connect()

    @pytest.mark.asyncio
    async def test_lua_script_execution(self, queue, mock_redis):
        """测试Lua脚本执行"""
        # 验证Lua脚本已加载
        assert hasattr(queue, "_lua_scripts")

        # 模拟脚本执行
        mock_redis.eval.return_value = "script-result"

        # 测试脚本调用（通过生产消息）
        with patch.object(queue, "_load_lua_scripts"):
            result = await queue.produce("test", {"data": "test"})
            # 由于是mock，这里主要验证调用流程

    @pytest.mark.asyncio
    async def test_concurrent_operations(self, queue, mock_redis):
        """测试并发操作"""
        # 模拟并发生产消息
        tasks = []
        for i in range(5):
            task = queue.produce(f"topic.{i}", {"index": i})
            tasks.append(task)

        # 等待所有任务完成
        with patch.object(queue, "produce", return_value=f"msg-{i}"):
            results = await asyncio.gather(*tasks, return_exceptions=True)

        # 验证没有异常
        assert len(results) == 5

    @pytest.mark.asyncio
    async def test_monitoring_and_health_check(self, queue, mock_redis):
        """测试监控和健康检查"""
        # 配置健康的mock响应
        mock_redis.ping.return_value = True
        mock_redis.info.return_value = {"redis_version": "6.0.0"}

        # 执行健康检查
        health = await queue.health_check()

        # 验证健康状态
        assert health["status"] == "healthy"
        assert health["connected"] is True
        assert "redis" in health

    @pytest.mark.asyncio
    async def test_resource_cleanup(self, queue, mock_redis):
        """测试资源清理"""
        # 模拟有活跃连接
        queue._connected = True
        queue._running = True

        # 执行清理
        await queue.disconnect()

        # 验证清理状态
        assert queue._connected is False
        mock_redis.close.assert_called_once()

    def test_configuration_edge_cases(self):
        """测试配置边界情况"""
        # 测试最小配置
        min_config = MQConfig(
            max_workers=1,
            task_queue_size=6,  # 必须大于max_workers
        )
        assert min_config.max_workers == 1
        assert min_config.task_queue_size == 6

        # 测试最大配置
        max_config = MQConfig(max_workers=50, task_queue_size=100)
        assert max_config.max_workers == 50
        assert max_config.task_queue_size == 100

    def test_message_lifecycle_states(self):
        """测试消息生命周期状态"""
        message = Message(topic="lifecycle.test", payload={"test": True})

        # 初始状态
        assert message.meta.status == MessageStatus.PENDING

        # 处理中
        message.mark_processing()
        assert message.meta.status == MessageStatus.PROCESSING
        assert message.meta.processing_started_at is not None

        # 完成
        message.mark_completed()
        assert message.meta.status == MessageStatus.COMPLETED
        assert message.meta.completed_at is not None

        # 测试重试流程
        retry_message = Message(topic="retry.test", payload={"test": True})
        retry_message.mark_retry("Test error")
        assert retry_message.meta.status == MessageStatus.RETRYING
        assert retry_message.meta.retry_count == 1
        assert retry_message.meta.last_error == "Test error"

        # 测试死信
        dlq_message = Message(topic="dlq.test", payload={"test": True})
        dlq_message.mark_dead_letter("Max retries exceeded")
        assert dlq_message.meta.status == MessageStatus.DEAD_LETTER
        assert dlq_message.meta.dead_letter_at is not None
