"""
消息模型单元测试
"""

import time
import uuid
import pytest
from unittest.mock import patch

from mx_rmq.message import Message, MessageMeta, MessageStatus, MessagePriority


class TestMessageStatus:
    """消息状态枚举测试"""
    
    def test_message_status_values(self):
        """测试消息状态枚举值"""
        assert MessageStatus.PENDING == "pending"
        assert MessageStatus.PROCESSING == "processing"
        assert MessageStatus.COMPLETED == "completed"
        assert MessageStatus.RETRYING == "retrying"
        assert MessageStatus.DEAD_LETTER == "dead_letter"
        assert MessageStatus.STUCK_TIMEOUT == "stuck_timeout"


class TestMessagePriority:
    """消息优先级枚举测试"""
    
    def test_message_priority_values(self):
        """测试消息优先级枚举值"""
        assert MessagePriority.LOW == "low"
        assert MessagePriority.NORMAL == "normal"
        assert MessagePriority.HIGH == "high"


class TestMessageMeta:
    """消息元数据测试"""
    
    def test_default_meta_creation(self):
        """测试默认元数据创建"""
        with patch('time.time', return_value=1640995200):  # 固定时间戳
            meta = MessageMeta()
            
            assert meta.status == MessageStatus.PENDING
            assert meta.retry_count == 0
            assert meta.max_retries == 3
            assert meta.retry_delays == [60, 300, 1800]
            assert meta.last_error is None
            assert meta.created_at == 1640995200000
            assert meta.updated_at == 1640995200000
            assert meta.expire_at == 1640995200000 + 86400000  # 24小时后
    
    def test_custom_meta_creation(self):
        """测试自定义元数据创建"""
        current_time = int(time.time() * 1000)
        expire_time = current_time + 3600000  # 1小时后
        
        # 使用别名字段名
        meta = MessageMeta(
            status=MessageStatus.PROCESSING,
            retryCount=2,  # 使用别名
            maxRetries=5,  # 使用别名
            retryDelays=[30, 60, 120],  # 使用别名
            lastError="处理失败",  # 使用别名
            expireAt=expire_time  # 使用别名
        )
        
        assert meta.status == MessageStatus.PROCESSING
        assert meta.retry_count == 2
        assert meta.max_retries == 5
        assert meta.retry_delays == [30, 60, 120]
        assert meta.last_error == "处理失败"
        assert meta.expire_at == expire_time
    
    def test_meta_alias_fields(self):
        """测试元数据字段别名"""
        meta_dict = {
            "retryCount": 3,
            "maxRetries": 5,
            "retryDelays": [10, 20, 30],
            "lastError": "错误信息",
            "expireAt": 1640995200000,
            "createdAt": 1640995200000,
            "updatedAt": 1640995200000
        }
        
        meta = MessageMeta(**meta_dict)
        assert meta.retry_count == 3
        assert meta.max_retries == 5
        assert meta.retry_delays == [10, 20, 30]
        assert meta.last_error == "错误信息"
        assert meta.expire_at == 1640995200000


class TestMessage:
    """消息主体测试"""
    
    def test_default_message_creation(self):
        """测试默认消息创建"""
        with patch('time.time', return_value=1640995200):
            message = Message(
                topic="test_topic",
                payload={"key": "value"}
            )
            
            assert message.topic == "test_topic"
            assert message.payload == {"key": "value"}
            assert message.priority == MessagePriority.NORMAL
            assert message.version == "1.0"
            assert message.created_at == 1640995200000
            assert isinstance(message.id, str)
            assert len(message.id) == 36  # UUID长度
            assert isinstance(message.meta, MessageMeta)
    
    def test_custom_message_creation(self):
        """测试自定义消息创建"""
        custom_id = str(uuid.uuid4())
        payload = {"user_id": 123, "action": "login"}
        
        message = Message(
            id=custom_id,
            topic="user_events",
            payload=payload,
            priority=MessagePriority.HIGH,
            version="2.0"
        )
        
        assert message.id == custom_id
        assert message.topic == "user_events"
        assert message.payload == payload
        assert message.priority == MessagePriority.HIGH
        assert message.version == "2.0"
    
    def test_message_with_custom_meta(self):
        """测试带自定义元数据的消息"""
        meta = MessageMeta(
            maxRetries=5,  # 使用别名
            retryDelays=[15, 30, 60]  # 使用别名
        )
        
        message = Message(
            topic="test_topic",
            payload={"data": "test"},
            meta=meta
        )
        
        assert message.meta.max_retries == 5
        assert message.meta.retry_delays == [15, 30, 60]
    
    def test_mark_processing(self):
        """测试标记消息为处理中"""
        message = Message(topic="test", payload={})
        
        with patch('time.time', return_value=1640995200):
            message.mark_processing()
            
            assert message.meta.status == MessageStatus.PROCESSING
            assert message.meta.processing_started_at == 1640995200000
            assert message.meta.updated_at == 1640995200000
    
    def test_mark_completed(self):
        """测试标记消息为已完成"""
        message = Message(topic="test", payload={})
        
        with patch('time.time', return_value=1640995200):
            message.mark_completed()
            
            assert message.meta.status == MessageStatus.COMPLETED
            assert message.meta.completed_at == 1640995200000
            assert message.meta.updated_at == 1640995200000
    
    def test_mark_retry(self):
        """测试标记消息重试"""
        message = Message(topic="test", payload={})
        error_msg = "网络连接失败"
        
        with patch('time.time', return_value=1640995200):
            message.mark_retry(error_msg)
            
            assert message.meta.status == MessageStatus.RETRYING
            assert message.meta.retry_count == 1
            assert message.meta.last_error == error_msg
            assert message.meta.last_retry_at == 1640995200000
            assert message.meta.updated_at == 1640995200000
    
    def test_mark_retry_error_truncation(self):
        """测试重试时错误信息截断"""
        message = Message(topic="test", payload={})
        long_error = "这是一个非常长的错误信息" * 10  # 超过50字符
        
        message.mark_retry(long_error)
        
        assert message.meta.last_error is not None
        assert len(message.meta.last_error) == 50
        assert message.meta.last_error == long_error[:50]
    
    def test_mark_dead_letter(self):
        """测试标记消息为死信"""
        message = Message(topic="test", payload={})
        reason = "超过最大重试次数"
        
        with patch('time.time', return_value=1640995200):
            message.mark_dead_letter(reason)
            
            assert message.meta.status == MessageStatus.DEAD_LETTER
            assert message.meta.last_error == reason
            assert message.meta.dead_letter_at == 1640995200000
            assert message.meta.updated_at == 1640995200000
    
    def test_mark_stuck(self):
        """测试标记消息为卡死"""
        message = Message(topic="test", payload={})
        reason = "处理超时"
        
        with patch('time.time', return_value=1640995200):
            message.mark_stuck(reason)
            
            assert message.meta.status == MessageStatus.STUCK_TIMEOUT
            assert message.meta.stuck_reason == reason
            assert message.meta.stuck_detected_at == 1640995200000
            assert message.meta.updated_at == 1640995200000
    
    def test_mark_stuck_reason_truncation(self):
        """测试卡死原因截断"""
        message = Message(topic="test", payload={})
        long_reason = "这是一个非常长的卡死原因描述" * 10
        
        message.mark_stuck(long_reason)
        
        assert message.meta.stuck_reason is not None
        assert len(message.meta.stuck_reason) == 50
        assert message.meta.stuck_reason == long_reason[:50]
    
    def test_can_retry_true(self):
        """测试可以重试的情况"""
        message = Message(topic="test", payload={})
        message.meta.retry_count = 2
        message.meta.max_retries = 3
        
        assert message.can_retry() is True
    
    def test_can_retry_false(self):
        """测试不能重试的情况"""
        message = Message(topic="test", payload={})
        message.meta.retry_count = 3
        message.meta.max_retries = 3
        
        assert message.can_retry() is False
    
    def test_is_expired_false(self):
        """测试消息未过期"""
        future_time = int(time.time() * 1000) + 3600000  # 1小时后
        message = Message(topic="test", payload={})
        message.meta.expire_at = future_time
        
        assert message.is_expired() is False
    
    def test_is_expired_true(self):
        """测试消息已过期"""
        past_time = int(time.time() * 1000) - 3600000  # 1小时前
        message = Message(topic="test", payload={})
        message.meta.expire_at = past_time
        
        assert message.is_expired() is True
    
    def test_get_retry_delay_first_retry(self):
        """测试第一次重试延迟"""
        message = Message(topic="test", payload={})
        message.meta.retry_count = 1
        message.meta.retry_delays = [30, 60, 120]
        
        assert message.get_retry_delay() == 30
    
    def test_get_retry_delay_second_retry(self):
        """测试第二次重试延迟"""
        message = Message(topic="test", payload={})
        message.meta.retry_count = 2
        message.meta.retry_delays = [30, 60, 120]
        
        assert message.get_retry_delay() == 60
    
    def test_get_retry_delay_exceed_config(self):
        """测试重试次数超过配置长度"""
        message = Message(topic="test", payload={})
        message.meta.retry_count = 5
        message.meta.retry_delays = [30, 60, 120]
        
        # 应该使用最后一个延迟值
        assert message.get_retry_delay() == 120
    
    def test_get_retry_delay_empty_config(self):
        """测试空重试延迟配置"""
        message = Message(topic="test", payload={})
        message.meta.retry_count = 1
        message.meta.retry_delays = []
        
        # 应该使用默认值60秒
        assert message.get_retry_delay() == 60
    
    def test_multiple_retries(self):
        """测试多次重试的状态变化"""
        message = Message(topic="test", payload={})
        message.meta.max_retries = 3
        
        # 第一次重试
        message.mark_retry("第一次失败")
        assert message.meta.retry_count == 1
        assert message.can_retry() is True
        
        # 第二次重试
        message.mark_retry("第二次失败")
        assert message.meta.retry_count == 2
        assert message.can_retry() is True
        
        # 第三次重试
        message.mark_retry("第三次失败")
        assert message.meta.retry_count == 3
        assert message.can_retry() is False
    
    def test_message_lifecycle(self):
        """测试消息完整生命周期"""
        message = Message(topic="user_action", payload={"user_id": 123})
        
        # 初始状态
        assert message.meta.status == MessageStatus.PENDING
        
        # 开始处理
        message.mark_processing()
        assert message.meta.status == MessageStatus.PROCESSING
        assert message.meta.processing_started_at is not None
        
        # 处理失败，需要重试
        message.mark_retry("临时网络错误")
        assert message.meta.status == MessageStatus.RETRYING
        assert message.meta.retry_count == 1
        assert message.can_retry() is True
        
        # 重试成功，标记完成
        message.mark_completed()
        assert message.meta.status == MessageStatus.COMPLETED
        assert message.meta.completed_at is not None