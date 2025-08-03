"""
基本集成测试 - 演示Redis环境集成
"""

import pytest
from unittest.mock import patch
import redis.asyncio as aioredis

from mx_rmq import RedisMessageQueue, MQConfig, MessagePriority
from tests.fixtures.test_data import TestDataFactory


class TestBasicIntegration:
    """基本集成测试"""
    
    @pytest.mark.integration
    @pytest.mark.redis_v8  
    @pytest.mark.asyncio
    async def test_basic_message_flow_redis_v8(self, test_config_v8: MQConfig):
        """测试基本消息流程 - Redis 8.x"""
        # 这里演示如何连接真实的Redis进行集成测试
        # 但由于当前环境限制，我们使用模拟
        
        with patch('redis.asyncio.Redis') as mock_redis_class:
            mock_redis = mock_redis_class.return_value
            mock_redis.ping.return_value = True
            mock_redis.info.return_value = {"redis_version": "8.0.0"}
            
            # 模拟Lua脚本执行
            mock_redis.eval.return_value = "test-message-id"
            
            # 初始化队列
            queue = RedisMessageQueue(test_config_v8)
            
            # 模拟初始化过程
            with patch.object(queue, '_produce_immediate_message_with_logging') as mock_produce:
                mock_produce.return_value = None
                
                # 生产消息
                message_id = await queue.produce(
                    topic="integration_test",
                    payload={"test": "integration"},
                    priority=MessagePriority.HIGH
                )
                
                assert isinstance(message_id, str)
                assert len(message_id) > 0
    
    @pytest.mark.integration
    @pytest.mark.redis_v6
    @pytest.mark.asyncio 
    async def test_basic_message_flow_redis_v6(self, test_config_v6: MQConfig):
        """测试基本消息流程 - Redis 6.x"""
        
        with patch('redis.asyncio.Redis') as mock_redis_class:
            mock_redis = mock_redis_class.return_value
            mock_redis.ping.return_value = True
            mock_redis.info.return_value = {"redis_version": "6.2.0"}
            
            # 模拟Lua脚本执行
            mock_redis.eval.return_value = "test-message-id"
            
            queue = RedisMessageQueue(test_config_v6)
            
            with patch.object(queue, '_produce_immediate_message_with_logging') as mock_produce:
                mock_produce.return_value = None
                
                message_id = await queue.produce(
                    topic="integration_test_v6",
                    payload={"test": "integration_v6"},
                    priority=MessagePriority.NORMAL
                )
                
                assert isinstance(message_id, str)
    
    @pytest.mark.integration 
    @pytest.mark.asyncio
    async def test_delayed_message_integration(self, test_config_v8: MQConfig):
        """测试延时消息集成"""
        
        with patch('redis.asyncio.Redis') as mock_redis_class:
            mock_redis = mock_redis_class.return_value
            mock_redis.ping.return_value = True
            mock_redis.info.return_value = {"redis_version": "8.0.0"}
            
            queue = RedisMessageQueue(test_config_v8)
            
            with patch.object(queue, '_produce_delayed_message_with_logging') as mock_produce:
                mock_produce.return_value = None
                
                # 生产延时消息
                message_id = await queue.produce(
                    topic="delayed_test",
                    payload={"delayed": True},
                    delay=300  # 5分钟延时
                )
                
                assert isinstance(message_id, str)
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_handler_registration_integration(self, test_config_v8: MQConfig):
        """测试处理器注册集成"""
        
        queue = RedisMessageQueue(test_config_v8)
        
        # 定义处理器
        async def test_handler(payload):
            return {"processed": True, "data": payload}
        
        # 注册处理器
        queue.register_handler("test_handler_topic", test_handler)
        
        # 验证处理器被正确注册
        assert hasattr(queue, "_pending_handlers")
        assert "test_handler_topic" in queue._pending_handlers
        assert queue._pending_handlers["test_handler_topic"] == test_handler
    
    @pytest.mark.integration
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_batch_message_processing(self, test_config_v8: MQConfig):
        """测试批量消息处理"""
        
        with patch('redis.asyncio.Redis') as mock_redis_class:
            mock_redis = mock_redis_class.return_value  
            mock_redis.ping.return_value = True
            mock_redis.info.return_value = {"redis_version": "8.0.0"}
            
            queue = RedisMessageQueue(test_config_v8)
            
            # 创建批量消息
            messages = TestDataFactory.create_batch_messages(
                count=10,
                topic="batch_test",
                priority=MessagePriority.NORMAL
            )
            
            with patch.object(queue, '_produce_immediate_message_with_logging') as mock_produce:
                mock_produce.return_value = None
                
                message_ids = []
                for message in messages:
                    message_id = await queue.produce(
                        topic=message.topic,
                        payload=message.payload,
                        priority=message.priority
                    )
                    message_ids.append(message_id)
                
                # 验证所有消息都有ID
                assert len(message_ids) == 10
                assert all(isinstance(mid, str) for mid in message_ids)
                assert len(set(message_ids)) == 10  # 确保ID唯一
    
    @pytest.mark.integration
    def test_error_handling_integration(self, test_config_v8: MQConfig):
        """测试错误处理集成"""
        
        queue = RedisMessageQueue(test_config_v8)
        
        # 测试无效处理器注册
        with pytest.raises(ValueError, match="处理器必须是可调用对象"):
            queue.register_handler("invalid_topic", "not_a_function") # type: ignore
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_priority_message_integration(self, test_config_v8: MQConfig):
        """测试优先级消息集成"""
        
        with patch('redis.asyncio.Redis') as mock_redis_class:
            mock_redis = mock_redis_class.return_value
            mock_redis.ping.return_value = True
            mock_redis.info.return_value = {"redis_version": "8.0.0"}
            
            queue = RedisMessageQueue(test_config_v8)
            
            # 创建不同优先级的消息
            priority_messages = TestDataFactory.create_priority_messages()
            
            with patch.object(queue, '_produce_immediate_message_with_logging') as mock_produce:
                mock_produce.return_value = None
                
                message_ids = []
                for message in priority_messages:
                    message_id = await queue.produce(
                        topic=message.topic,
                        payload=message.payload,
                        priority=message.priority
                    )
                    message_ids.append(message_id)
                
                assert len(message_ids) == 3  # HIGH, NORMAL, LOW
                assert all(isinstance(mid, str) for mid in message_ids)