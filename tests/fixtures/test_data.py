"""
测试数据和工具函数
"""

import uuid
from datetime import datetime, timedelta
from typing import Any, Dict

from mx_rmq import Message, MessagePriority
from mx_rmq.message import MessageMeta


class TestDataFactory:
    """测试数据工厂类"""
    
    @staticmethod
    def create_test_message(
        topic: str = "test_topic",
        data: Dict[str, Any] | None = None,
        priority: MessagePriority = MessagePriority.NORMAL,
        delay: int = 0,
    ) -> Message:
        """创建测试消息"""
        if data is None:
            data = {"test_key": "test_value", "timestamp": datetime.now().isoformat()}
        
        return Message(
            topic=topic,
            payload=data,
            priority=priority,
            meta=MessageMeta(delay=delay)
        )
    
    @staticmethod
    def create_batch_messages(
        count: int,
        topic: str = "test_topic",
        priority: MessagePriority = MessagePriority.NORMAL
    ) -> list[Message]:
        """创建批量测试消息"""
        messages = []
        for i in range(count):
            data = {
                "batch_id": i,
                "message": f"测试消息 {i}",
                "timestamp": datetime.now().isoformat()
            }
            messages.append(TestDataFactory.create_test_message(
                topic=topic,
                data=data,
                priority=priority
            ))
        return messages
    
    @staticmethod
    def create_delay_messages(
        delays: list[int],
        topic: str = "delay_test_topic"
    ) -> list[Message]:
        """创建延时消息"""
        messages = []
        for i, delay in enumerate(delays):
            data = {
                "delay_id": i,
                "delay_seconds": delay,
                "message": f"延时消息，延时{delay}秒"
            }
            messages.append(TestDataFactory.create_test_message(
                topic=topic,
                data=data,
                delay=delay
            ))
        return messages
    
    @staticmethod
    def create_priority_messages() -> list[Message]:
        """创建不同优先级的消息"""
        messages = []
        priorities = [MessagePriority.HIGH, MessagePriority.NORMAL, MessagePriority.LOW]
        
        for i, priority in enumerate(priorities):
            data = {
                "priority_id": i,
                "priority": priority.value,
                "message": f"优先级{priority.value}消息"
            }
            messages.append(TestDataFactory.create_test_message(
                topic="priority_test_topic",
                data=data,
                priority=priority
            ))
        return messages


class TestUtils:
    """测试工具函数"""
    
    @staticmethod
    def generate_topic_name(prefix: str = "test") -> str:
        """生成唯一的topic名称"""
        return f"{prefix}_{uuid.uuid4().hex[:8]}"
    
    @staticmethod
    def generate_message_id() -> str:
        """生成唯一的消息ID"""
        return str(uuid.uuid4())
    
    @staticmethod
    def create_error_message_data() -> Dict[str, Any]:
        """创建可能导致错误的消息数据"""
        return {
            "error_type": "test_error",
            "should_fail": True,
            "error_message": "模拟处理错误"
        }
    
    @staticmethod
    def calculate_expected_delay_time(delay_seconds: int) -> datetime:
        """计算预期的延时执行时间"""
        return datetime.now() + timedelta(seconds=delay_seconds)


# 常用测试数据常量
TEST_TOPICS = [
    "test_topic_1",
    "test_topic_2", 
    "priority_topic",
    "delay_topic",
    "batch_topic",
    "error_topic"
]

SAMPLE_MESSAGE_DATA = {
    "user_id": 12345,
    "action": "test_action",
    "metadata": {
        "source": "unit_test",
        "version": "1.0"
    },
    "payload": {
        "data": "测试数据",
        "timestamp": "2024-01-01T00:00:00Z"
    }
}

RETRY_TEST_INTERVALS = [1, 2, 4, 8]  # 重试间隔（秒）
DELAY_TEST_SECONDS = [1, 5, 10, 30]  # 延时测试时间（秒）