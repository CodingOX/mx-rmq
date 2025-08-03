"""
消费者服务测试
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from mx_rmq.core.consumer import ConsumerService
from mx_rmq.core.context import QueueContext
from mx_rmq.core.dispatch import TaskItem
from mx_rmq.message import Message, MessagePriority


class TestConsumerService:
    """消费者服务测试"""
    
    def test_consumer_service_initialization(self):
        """测试消费者服务初始化"""
        mock_context = MagicMock(spec=QueueContext)
        task_queue = asyncio.Queue()
        
        service = ConsumerService(mock_context, task_queue)
        
        assert service.context == mock_context
        assert service.task_queue == task_queue
    
    @pytest.mark.asyncio
    async def test_consume_messages_with_valid_handler(self):
        """测试消费消息 - 有效处理器"""
        mock_context = MagicMock(spec=QueueContext)
        task_queue = asyncio.Queue()
        
        # 模拟运行状态
        mock_context.is_running.side_effect = [True, False]  # 运行一次后停止
        
        # 模拟处理器
        mock_handler = AsyncMock(return_value={"result": "success"})
        mock_context.handlers = {"test_topic": mock_handler}
        
        service = ConsumerService(mock_context, task_queue)
        
        # 创建测试消息和任务
        message = Message(
            topic="test_topic",
            payload={"test": "data"}
        )
        task_item = TaskItem(topic="test_topic", message=message)
        
        # 将任务放入队列
        await task_queue.put(task_item)
        
        # 模拟消息处理流程中的服务调用
        with patch('mx_rmq.core.consumer.MessageLifecycleService') as mock_lifecycle_class:
            mock_lifecycle = AsyncMock()
            mock_lifecycle_class.return_value = mock_lifecycle
            
            with patch('asyncio.wait_for') as mock_wait_for:
                # 第一次调用返回任务，第二次超时（模拟优雅停机）
                mock_wait_for.side_effect = [task_item, asyncio.TimeoutError()]
                
                await service.consume_messages()
                
                # 验证处理器被调用
                mock_handler.assert_called_once_with(message.payload)
                # 验证生命周期服务被创建和调用
                mock_lifecycle_class.assert_called_with(service.context)
                mock_lifecycle.complete_message.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_consume_messages_no_handler(self):
        """测试消费消息 - 无处理器"""
        mock_context = MagicMock(spec=QueueContext)
        task_queue = asyncio.Queue()
        
        # 模拟运行状态
        mock_context.is_running.side_effect = [True, False]
        mock_context.handlers = {}  # 空处理器映射
        
        service = ConsumerService(mock_context, task_queue)
        
        # 创建测试任务
        message = Message(topic="unknown_topic", payload={"test": "data"})
        task_item = TaskItem(topic="unknown_topic", message=message)
        
        with patch('asyncio.wait_for') as mock_wait_for:
            mock_wait_for.side_effect = [task_item, asyncio.TimeoutError()]
            
            # 应该能正常运行，只是跳过未知topic的消息
            await service.consume_messages()
            
            # 验证没有异常抛出
    
    @pytest.mark.asyncio
    async def test_consume_messages_handler_exception(self):
        """测试消费消息 - 处理器异常"""
        mock_context = MagicMock(spec=QueueContext)
        task_queue = asyncio.Queue()
        
        mock_context.is_running.side_effect = [True, False]
        
        # 模拟抛出异常的处理器
        mock_handler = AsyncMock(side_effect=ValueError("处理失败"))
        mock_context.handlers = {"test_topic": mock_handler}
        
        service = ConsumerService(mock_context, task_queue)
        
        message = Message(topic="test_topic", payload={"test": "data"})
        task_item = TaskItem(topic="test_topic", message=message)
        
        with patch('asyncio.wait_for') as mock_wait_for:
            mock_wait_for.side_effect = [task_item, asyncio.TimeoutError()]
            
            # 消费过程中的异常应该被捕获处理
            await service.consume_messages()
            
            # 验证处理器被调用了
            mock_handler.assert_called_once_with(message.payload)
    
    @pytest.mark.asyncio
    async def test_consume_messages_timeout_handling(self):
        """测试消费消息 - 超时处理（优雅停机）"""
        mock_context = MagicMock(spec=QueueContext)
        task_queue = asyncio.Queue()
        
        # 模拟运行状态：一直运行但队列为空，触发超时
        mock_context.is_running.side_effect = [True, True, False]
        
        service = ConsumerService(mock_context, task_queue)
        
        with patch('asyncio.wait_for') as mock_wait_for:
            # 模拟连续超时
            mock_wait_for.side_effect = [
                asyncio.TimeoutError(),
                asyncio.TimeoutError()
            ]
            
            await service.consume_messages()
            
            # 验证wait_for被调用了多次（尝试获取任务）
            assert mock_wait_for.call_count >= 2
    
    @pytest.mark.asyncio
    async def test_consume_messages_graceful_shutdown(self):
        """测试消费消息 - 优雅停机"""
        mock_context = MagicMock(spec=QueueContext)
        task_queue = asyncio.Queue()
        
        # 模拟从运行到停止的状态变化
        run_states = [True, True, True, False]
        mock_context.is_running.side_effect = run_states
        
        service = ConsumerService(mock_context, task_queue)
        
        with patch('asyncio.wait_for') as mock_wait_for:
            # 模拟获取任务时的超时（空队列）
            mock_wait_for.side_effect = asyncio.TimeoutError()
            
            await service.consume_messages()
            
            # 验证is_running被调用了预期次数
            assert mock_context.is_running.call_count == len(run_states)
    
    @pytest.mark.asyncio
    async def test_consume_messages_multiple_tasks(self):
        """测试消费多个消息任务"""
        mock_context = MagicMock(spec=QueueContext)
        task_queue = asyncio.Queue()
        
        # 处理3个任务后停止
        mock_context.is_running.side_effect = [True, True, True, False]
        
        mock_handler = AsyncMock(return_value="processed")
        mock_context.handlers = {"test_topic": mock_handler}
        
        service = ConsumerService(mock_context, task_queue)
        
        # 创建多个任务
        tasks = []
        for i in range(3):
            message = Message(
                topic="test_topic", 
                payload={"id": i, "data": f"message_{i}"}
            )
            task_item = TaskItem(topic="test_topic", message=message)
            tasks.append(task_item)
        
        with patch('asyncio.wait_for') as mock_wait_for:
            # 前3次返回任务，第4次超时停止
            mock_wait_for.side_effect = tasks + [asyncio.TimeoutError()]
            
            with patch('mx_rmq.core.consumer.MessageLifecycleService') as mock_lifecycle_class:
                mock_lifecycle = AsyncMock()
                mock_lifecycle_class.return_value = mock_lifecycle
                
                await service.consume_messages()
                
                # 验证所有任务都被处理
                assert mock_handler.call_count == 3
                # 验证生命周期服务被调用3次
                assert mock_lifecycle.complete_message.call_count == 3
    
    @pytest.mark.asyncio
    async def test_consume_messages_different_topics(self):
        """测试消费不同主题的消息"""
        mock_context = MagicMock(spec=QueueContext)
        task_queue = asyncio.Queue()
        
        mock_context.is_running.side_effect = [True, True, False]
        
        # 为不同主题注册处理器
        mock_handler1 = AsyncMock(return_value="handler1")
        mock_handler2 = AsyncMock(return_value="handler2")
        mock_context.handlers = {
            "topic1": mock_handler1,
            "topic2": mock_handler2
        }
        
        service = ConsumerService(mock_context, task_queue)
        
        # 创建不同主题的任务
        message1 = Message(topic="topic1", payload={"type": "type1"})
        message2 = Message(topic="topic2", payload={"type": "type2"})
        
        task1 = TaskItem(topic="topic1", message=message1)
        task2 = TaskItem(topic="topic2", message=message2)
        
        with patch('asyncio.wait_for') as mock_wait_for:
            mock_wait_for.side_effect = [task1, task2, asyncio.TimeoutError()]
            
            with patch('mx_rmq.core.consumer.MessageLifecycleService') as mock_lifecycle_class:
                mock_lifecycle = AsyncMock()
                mock_lifecycle_class.return_value = mock_lifecycle
                
                await service.consume_messages()
                
                # 验证不同处理器被正确调用
                mock_handler1.assert_called_once_with(message1.payload)
                mock_handler2.assert_called_once_with(message2.payload)
                # 验证生命周期服务被调用2次
                assert mock_lifecycle.complete_message.call_count == 2
    
    def test_task_item_structure(self):
        """测试TaskItem数据结构"""
        message = Message(
            topic="test_topic",
            payload={"test": "data"},
            priority=MessagePriority.HIGH
        )
        
        task_item = TaskItem(topic="test_topic", message=message)
        
        assert task_item.topic == "test_topic"
        assert task_item.message == message
        assert task_item.message.priority == MessagePriority.HIGH