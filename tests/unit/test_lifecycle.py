"""
消息生命周期管理测试
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import json

from mx_rmq.core.lifecycle import MessageLifecycleService
from mx_rmq.core.context import QueueContext
from mx_rmq.message import Message, MessagePriority, MessageStatus
from mx_rmq.config import MQConfig


class TestMessageLifecycleService:
    """消息生命周期管理服务测试"""
    
    def test_lifecycle_service_initialization(self):
        """测试生命周期服务初始化"""
        mock_context = MagicMock(spec=QueueContext)
        service = MessageLifecycleService(mock_context)
        
        assert service.context == mock_context
    
    @pytest.mark.asyncio
    async def test_complete_message_success(self):
        """测试成功完成消息处理"""
        mock_context = MagicMock(spec=QueueContext)
        mock_script = AsyncMock()
        mock_context.lua_scripts = {"complete_message": mock_script}
        mock_context.get_global_key = MagicMock(return_value="test:global:key")
        mock_context.get_global_topic_key = MagicMock(return_value="test:topic:key")
        
        service = MessageLifecycleService(mock_context)
        
        message_id = "test-message-123"
        topic = "test_topic"
        
        await service.complete_message(message_id, topic)
        
        # 验证Lua脚本被正确调用
        mock_script.assert_called_once()
        call_args = mock_script.call_args
        
        assert len(call_args[1]['keys']) == 3  # 3个键
        assert call_args[1]['args'] == [message_id]
        
        # 验证上下文方法被调用
        mock_context.get_global_key.assert_called()
        mock_context.get_global_topic_key.assert_called_with(topic, mock_context.get_global_topic_key.call_args[0][1])
    
    @pytest.mark.asyncio
    async def test_complete_message_failure(self):
        """测试完成消息处理时的异常"""
        mock_context = MagicMock(spec=QueueContext)
        mock_script = AsyncMock()
        mock_script.side_effect = Exception("Lua脚本执行失败")
        mock_context.lua_scripts = {"complete_message": mock_script}
        mock_context.get_global_key = MagicMock(return_value="test:global:key")
        mock_context.get_global_topic_key = MagicMock(return_value="test:topic:key")
        
        service = MessageLifecycleService(mock_context)
        
        with pytest.raises(Exception, match="Lua脚本执行失败"):
            await service.complete_message("test-message-123", "test_topic")
    
    @pytest.mark.asyncio
    async def test_handle_message_failure_retryable(self):
        """测试处理可重试的消息失败"""
        mock_context = MagicMock(spec=QueueContext)
        service = MessageLifecycleService(mock_context)
        
        # 创建可重试的消息
        message = Message(
            topic="test_topic",
            payload={"test": "data"}
        )
        message.meta.retry_count = 1
        message.meta.max_retries = 3
        
        error = ValueError("处理失败")
        
        with patch.object(service, '_handle_retryable_failure', new_callable=AsyncMock) as mock_retry:
            await service.handle_message_failure(message, error)
            
            # 验证消息状态被标记为重试
            assert message.meta.status == MessageStatus.RETRYING
            assert message.meta.retry_count == 2
            assert message.meta.last_error == "处理失败"
            
            # 验证重试处理被调用
            mock_retry.assert_called_once_with(message, error)
    
    @pytest.mark.asyncio
    async def test_handle_message_failure_final(self):
        """测试处理最终失败的消息"""
        mock_context = MagicMock(spec=QueueContext)
        service = MessageLifecycleService(mock_context)
        
        # 创建已达到最大重试次数的消息
        message = Message(
            topic="test_topic",
            payload={"test": "data"}
        )
        message.meta.retry_count = 3
        message.meta.max_retries = 3
        
        error = ValueError("最终失败")
        
        with patch.object(service, '_handle_final_failure', new_callable=AsyncMock) as mock_final:
            await service.handle_message_failure(message, error)
            
            # 验证消息状态被标记为重试（即使是最终失败也会先标记）
            assert message.meta.status == MessageStatus.RETRYING
            assert message.meta.retry_count == 4
            assert message.meta.last_error == "最终失败"
            
            # 验证最终失败处理被调用
            mock_final.assert_called_once_with(message, error)
    
    @pytest.mark.asyncio
    async def test_handle_message_failure_exception_in_handling(self):
        """测试消息失败处理过程中的异常"""
        mock_context = MagicMock(spec=QueueContext)
        service = MessageLifecycleService(mock_context)
        
        message = Message(
            topic="test_topic",
            payload={"test": "data"}
        )
        
        error = ValueError("原始错误")
        
        # 模拟重试处理失败
        with patch.object(service, '_handle_retryable_failure', new_callable=AsyncMock) as mock_retry:
            mock_retry.side_effect = Exception("重试处理失败")
            
            # 不应该抛出异常，应该被捕获并记录
            await service.handle_message_failure(message, error)
            
            mock_retry.assert_called_once()
    
    def test_message_lifecycle_transitions(self):
        """测试消息生命周期状态转换"""
        message = Message(
            topic="lifecycle_test",
            payload={"test": "lifecycle"}
        )
        
        # 初始状态
        assert message.meta.status == MessageStatus.PENDING
        assert message.meta.retry_count == 0
        
        # 开始处理
        message.mark_processing()
        assert message.meta.status == MessageStatus.PROCESSING
        assert message.meta.processing_started_at is not None
        
        # 处理失败，需要重试
        error_msg = "网络超时"
        message.mark_retry(error_msg)
        assert message.meta.status == MessageStatus.RETRYING
        assert message.meta.retry_count == 1
        assert message.meta.last_error == error_msg
        assert message.meta.last_retry_at is not None
        
        # 重试后成功
        message.mark_completed()
        assert message.meta.status == MessageStatus.COMPLETED
        assert message.meta.completed_at is not None
    
    def test_message_dead_letter_transition(self):
        """测试消息死信队列转换"""
        message = Message(
            topic="dlq_test",
            payload={"test": "dlq"}
        )
        
        # 模拟多次重试失败
        message.meta.retry_count = 3
        message.meta.max_retries = 3
        
        # 验证不能再重试
        assert not message.can_retry()
        
        # 移入死信队列
        reason = "超过最大重试次数"
        message.mark_dead_letter(reason)
        
        assert message.meta.status == MessageStatus.DEAD_LETTER
        assert message.meta.last_error == reason
        assert message.meta.dead_letter_at is not None
    
    def test_message_stuck_detection(self):
        """测试消息卡死检测"""
        message = Message(
            topic="stuck_test",
            payload={"test": "stuck"}
        )
        
        reason = "处理超时"
        message.mark_stuck(reason)
        
        assert message.meta.status == MessageStatus.STUCK_TIMEOUT
        assert message.meta.stuck_reason == reason
        assert message.meta.stuck_detected_at is not None
    
    def test_message_expiration_check(self):
        """测试消息过期检查"""
        import time
        
        message = Message(
            topic="expire_test",
            payload={"test": "expire"}
        )
        
        # 设置为已过期
        message.meta.expire_at = int((time.time() - 3600) * 1000)  # 1小时前过期
        
        assert message.is_expired() is True
        
        # 设置为未来过期
        message.meta.expire_at = int((time.time() + 3600) * 1000)  # 1小时后过期
        
        assert message.is_expired() is False
    
    def test_retry_delay_calculation(self):
        """测试重试延迟计算"""
        message = Message(
            topic="retry_test",
            payload={"test": "retry"}
        )
        
        # 设置重试延迟配置
        message.meta.retry_delays = [30, 60, 120, 300]
        
        # 第一次重试
        message.meta.retry_count = 1
        assert message.get_retry_delay() == 30
        
        # 第二次重试
        message.meta.retry_count = 2
        assert message.get_retry_delay() == 60
        
        # 第四次重试
        message.meta.retry_count = 4
        assert message.get_retry_delay() == 300
        
        # 超过配置长度，使用最后一个值
        message.meta.retry_count = 10
        assert message.get_retry_delay() == 300
    
    def test_retry_delay_empty_config(self):
        """测试空重试延迟配置"""
        message = Message(
            topic="retry_empty_test",
            payload={"test": "retry"}
        )
        
        # 清空重试延迟配置
        message.meta.retry_delays = []
        message.meta.retry_count = 1
        
        # 应该返回默认值
        assert message.get_retry_delay() == 60
    
    @pytest.mark.asyncio
    async def test_lifecycle_service_error_handling(self):
        """测试生命周期服务的错误处理"""
        mock_context = MagicMock(spec=QueueContext)
        service = MessageLifecycleService(mock_context)
        
        message = Message(
            topic="error_test",
            payload={"test": "error"}
        )
        
        # 模拟处理过程中的各种异常
        exceptions = [
            ValueError("验证错误"),
            RuntimeError("运行时错误"),
            Exception("未知错误")
        ]
        
        for exception in exceptions:
            # 重置消息状态
            message.meta.status = MessageStatus.PENDING
            message.meta.retry_count = 0
            
            with patch.object(service, '_handle_retryable_failure', new_callable=AsyncMock):
                await service.handle_message_failure(message, exception)
                
                # 验证错误信息被正确记录
                assert str(exception) in message.meta.last_error # type: ignore