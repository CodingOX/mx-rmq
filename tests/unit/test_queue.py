"""
队列核心功能单元测试
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from unittest.mock import call

from mx_rmq import RedisMessageQueue, MQConfig, Message, MessagePriority
from tests.fixtures.test_data import TestDataFactory


class TestRedisMessageQueue:
    """Redis消息队列核心测试"""

    def test_queue_initialization(self):
        """测试队列初始化"""
        # 使用默认配置
        queue = RedisMessageQueue()
        assert queue.config is not None
        assert queue.initialized is False
        assert queue._task_queue is not None
        assert queue._task_queue.maxsize == queue.config.task_queue_size

    def test_queue_with_custom_config(self, test_config_v8: MQConfig):
        """测试自定义配置初始化"""
        queue = RedisMessageQueue(test_config_v8)
        assert queue.config == test_config_v8
        assert queue.initialized is False

    @pytest.mark.asyncio
    async def test_queue_produce_message_not_initialized(self):
        """测试未初始化状态下生产消息会自动初始化"""
        queue = RedisMessageQueue()
        
        # 模拟初始化过程
        with patch.object(queue, 'initialize', new_callable=AsyncMock) as mock_init:
            with patch.object(queue, '_produce_immediate_message_with_logging', new_callable=AsyncMock) as mock_produce:
                # 设置初始化后的状态
                def set_initialized():
                    queue.initialized = True
                    queue._context = MagicMock()
                
                mock_init.side_effect = set_initialized
                mock_produce.return_value = None
                
                # 初始状态未初始化
                queue.initialized = False
                
                message_id = await queue.produce(
                    topic="test_topic",
                    payload={"test": "data"}
                )
                
                # 验证自动初始化被调用
                mock_init.assert_called_once()
                assert isinstance(message_id, str)

    def test_register_handler_before_initialization(self):
        """测试初始化前注册处理器"""
        queue = RedisMessageQueue()
        
        def test_handler(payload):
            return True
        
        # 在初始化前注册
        queue.register_handler("test_topic", test_handler)
        
        # 验证处理器被存储到待注册列表
        assert hasattr(queue, "_pending_handlers")
        assert queue._pending_handlers["test_topic"] == test_handler

    def test_register_handler_validation(self):
        """测试处理器注册验证"""
        queue = RedisMessageQueue()
        
        # 无效处理器
        with pytest.raises(ValueError, match="处理器必须是可调用对象"):
            queue.register_handler("test_topic", "not_callable") # type: ignore

    @pytest.mark.asyncio
    async def test_message_creation(self):
        """测试消息创建逻辑"""
        queue = RedisMessageQueue()
        
        with patch.object(queue, 'initialize', new_callable=AsyncMock):
            with patch.object(queue, '_produce_immediate_message_with_logging', new_callable=AsyncMock) as mock_produce:
                queue.initialized = True
                queue._context = MagicMock()
                
                # 测试自定义消息ID
                custom_id = "custom-message-id"
                message_id = await queue.produce(
                    topic="test_topic",
                    payload={"test": "data"},
                    message_id=custom_id,
                    priority=MessagePriority.HIGH,
                    ttl=3600
                )
                
                assert message_id == custom_id
                mock_produce.assert_called_once()

    @pytest.mark.asyncio
    async def test_delayed_message_production(self):
        """测试延时消息生产"""
        queue = RedisMessageQueue()
        
        with patch.object(queue, 'initialize', new_callable=AsyncMock):
            with patch.object(queue, '_produce_delayed_message_with_logging', new_callable=AsyncMock) as mock_produce:
                queue.initialized = True
                queue._context = MagicMock()
                
                message_id = await queue.produce(
                    topic="test_topic",
                    payload={"test": "data"},
                    delay=300  # 5分钟延时
                )
                
                mock_produce.assert_called_once()
                # 验证调用参数
                args = mock_produce.call_args[0]
                message, message_json, topic, delay, priority = args
                
                assert isinstance(message, Message)
                assert topic == "test_topic"
                assert delay == 300
                assert priority == MessagePriority.NORMAL

    @pytest.mark.asyncio
    async def test_immediate_message_production(self):
        """测试立即消息生产"""
        queue = RedisMessageQueue()
        
        with patch.object(queue, 'initialize', new_callable=AsyncMock):
            with patch.object(queue, '_produce_immediate_message_with_logging', new_callable=AsyncMock) as mock_produce:
                queue.initialized = True
                queue._context = MagicMock()
                
                message_id = await queue.produce(
                    topic="test_topic",
                    payload={"test": "data"},
                    delay=0  # 立即执行
                )
                
                mock_produce.assert_called_once()
                # 验证调用参数
                args = mock_produce.call_args[0]
                message, message_json, topic, expire_time, priority = args
                
                assert isinstance(message, Message)
                assert topic == "test_topic"
                assert priority == MessagePriority.NORMAL

    def test_queue_metrics_structure(self):
        """测试队列指标结构"""
        from mx_rmq.queue import QueueMetrics
        
        metrics = QueueMetrics(
            local_queue_size=10,
            local_queue_maxsize=100,
            active_tasks_count=5,
            registered_topics=["topic1", "topic2"],
            shutting_down=False
        )
        
        assert metrics.local_queue_size == 10
        assert metrics.local_queue_maxsize == 100
        assert metrics.active_tasks_count == 5
        assert metrics.registered_topics == ["topic1", "topic2"]
        assert metrics.shutting_down is False

    @pytest.mark.asyncio
    async def test_message_ttl_configuration(self):
        """测试消息TTL配置"""
        config = MQConfig(message_ttl=7200)  # 2小时
        queue = RedisMessageQueue(config)
        
        with patch.object(queue, 'initialize', new_callable=AsyncMock):
            with patch.object(queue, '_produce_immediate_message_with_logging', new_callable=AsyncMock) as mock_produce:
                with patch('time.time', return_value=1640995200):  # 固定时间
                    queue.initialized = True
                    queue._context = MagicMock()
                    
                    await queue.produce(
                        topic="test_topic",
                        payload={"test": "data"}
                    )
                    
                    # 验证消息TTL设置正确
                    args = mock_produce.call_args[0]
                    message = args[0]
                    expected_expire_time = int(1640995200 * 1000) + 7200 * 1000
                    assert message.meta.expire_at == expected_expire_time

    @pytest.mark.asyncio
    async def test_custom_ttl_override(self):
        """测试自定义TTL覆盖配置"""
        config = MQConfig(message_ttl=7200)  # 配置2小时
        queue = RedisMessageQueue(config)
        
        with patch.object(queue, 'initialize', new_callable=AsyncMock):
            with patch.object(queue, '_produce_immediate_message_with_logging', new_callable=AsyncMock) as mock_produce:
                with patch('time.time', return_value=1640995200):
                    queue.initialized = True
                    queue._context = MagicMock()
                    
                    await queue.produce(
                        topic="test_topic",
                        payload={"test": "data"},
                        ttl=3600  # 覆盖为1小时
                    )
                    
                    # 验证使用了自定义TTL
                    args = mock_produce.call_args[0]
                    message = args[0]
                    expected_expire_time = int(1640995200 * 1000) + 3600 * 1000
                    assert message.meta.expire_at == expected_expire_time

    @pytest.mark.asyncio
    async def test_retry_configuration_propagation(self):
        """测试重试配置传播"""
        config = MQConfig(
            max_retries=5,
            retry_delays=[30, 60, 120, 300, 600]
        )
        queue = RedisMessageQueue(config)
        
        with patch.object(queue, 'initialize', new_callable=AsyncMock):
            with patch.object(queue, '_produce_immediate_message_with_logging', new_callable=AsyncMock) as mock_produce:
                queue.initialized = True
                queue._context = MagicMock()
                
                await queue.produce(
                    topic="test_topic",
                    payload={"test": "data"}
                )
                
                # 验证重试配置传播到消息
                args = mock_produce.call_args[0]
                message = args[0]
                assert message.meta.max_retries == 5
                assert message.meta.retry_delays == [30, 60, 120, 300, 600]

    @pytest.mark.asyncio
    async def test_error_handling_in_produce(self):
        """测试生产过程中的错误处理"""
        queue = RedisMessageQueue()
        
        with patch.object(queue, 'initialize', new_callable=AsyncMock):
            with patch.object(queue, '_produce_immediate_message_with_logging', new_callable=AsyncMock) as mock_produce:
                queue.initialized = True
                queue._context = MagicMock()
                
                # 模拟生产失败
                mock_produce.side_effect = Exception("Redis连接失败")
                
                with pytest.raises(Exception, match="Redis连接失败"):
                    await queue.produce(
                        topic="test_topic",
                        payload={"test": "data"}
                    )

    def test_message_priority_handling(self):
        """测试消息优先级处理"""
        queue = RedisMessageQueue()
        
        # 测试不同优先级的消息创建
        priorities = [MessagePriority.LOW, MessagePriority.NORMAL, MessagePriority.HIGH]
        
        for priority in priorities:
            with patch.object(queue, 'initialize', new_callable=AsyncMock):
                with patch.object(queue, '_produce_immediate_message_with_logging', new_callable=AsyncMock) as mock_produce:
                    async def test_priority():
                        queue.initialized = True
                        queue._context = MagicMock()
                        
                        await queue.produce(
                            topic="test_topic",
                            payload={"test": "data"},
                            priority=priority
                        )
                        
                        args = mock_produce.call_args[0]
                        message = args[0]
                        assert message.priority == priority
                    
                    # 运行异步测试
                    asyncio.run(test_priority())

    @pytest.mark.asyncio
    async def test_multiple_handler_registration(self):
        """测试多个处理器注册"""
        queue = RedisMessageQueue()
        
        def handler1(payload):
            return "handler1"
        
        def handler2(payload):
            return "handler2"
        
        # 注册多个处理器
        queue.register_handler("topic1", handler1)
        queue.register_handler("topic2", handler2)
        
        # 验证待注册处理器
        assert queue._pending_handlers["topic1"] == handler1
        assert queue._pending_handlers["topic2"] == handler2