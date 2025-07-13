"""消息模型的单元测试"""

import pytest
import time
from mx_rmq.message import Message, MessageMeta, MessageStatus, MessagePriority


class TestMessagePriority:
    """测试消息优先级枚举"""

    def test_priority_values(self):
        """测试优先级值"""
        assert MessagePriority.LOW.value == "low"
        assert MessagePriority.NORMAL.value == "normal"
        assert MessagePriority.HIGH.value == "high"

    def test_priority_string_enum(self):
        """测试优先级字符串枚举特性"""
        assert MessagePriority.HIGH.value == "high"
        assert MessagePriority.HIGH == "high"
        assert MessagePriority.NORMAL != "high"


class TestMessageStatus:
    """测试消息状态枚举"""

    def test_status_values(self):
        """测试状态值"""
        assert MessageStatus.PENDING.value == "pending"
        assert MessageStatus.PROCESSING.value == "processing"
        assert MessageStatus.COMPLETED.value == "completed"
        assert MessageStatus.RETRYING.value == "retrying"
        assert MessageStatus.DEAD_LETTER.value == "dead_letter"
        assert MessageStatus.STUCK_TIMEOUT.value == "stuck_timeout"

    def test_status_string_enum(self):
        """测试状态字符串枚举特性"""
        assert MessageStatus.PROCESSING.value == "processing"
        assert MessageStatus.COMPLETED == "completed"


class TestMessageMeta:
    """测试消息元数据类"""

    def test_default_meta(self):
        """测试默认元数据"""
        current_time = int(time.time() * 1000)
        meta = MessageMeta(expire_at=current_time + 3600000)

        assert meta.status == MessageStatus.PENDING
        assert meta.retry_count == 0
        assert meta.max_retries == 3
        assert meta.retry_delays == [60, 300, 1800]
        assert meta.last_error is None
        assert meta.expire_at == current_time + 3600000
        assert abs(meta.created_at - current_time) <= 1
        assert abs(meta.updated_at - current_time) <= 1
        assert meta.last_retry_at is None
        assert meta.processing_started_at is None
        assert meta.completed_at is None
        assert meta.dead_letter_at is None
        assert meta.stuck_detected_at is None
        assert meta.stuck_reason is None

    def test_custom_meta(self):
        """测试自定义元数据"""
        expire_time = int(time.time() * 1000) + 7200000
        custom_delays = [30, 120, 600]

        meta = MessageMeta(
            status=MessageStatus.RETRYING,
            retry_count=2,
            max_retries=5,
            retry_delays=custom_delays,
            last_error="Test error",
            expire_at=expire_time,
            last_retry_at=expire_time - 300,
        )

        assert meta.status == MessageStatus.RETRYING
        assert meta.retry_count == 2
        assert meta.max_retries == 5
        assert meta.retry_delays == custom_delays
        assert meta.last_error == "Test error"
        assert meta.expire_at == expire_time
        assert meta.last_retry_at == expire_time - 300

    def test_meta_validation(self):
        """测试元数据验证"""
        expire_time = int(time.time() * 1000) + 3600000

        # retry_count不能为负数
        with pytest.raises(ValueError):
            MessageMeta(retry_count=-1, expire_at=expire_time)

        # max_retries不能为负数
        with pytest.raises(ValueError):
            MessageMeta(max_retries=-1, expire_at=expire_time)

        # expire_at现在有默认值，测试负数
        with pytest.raises(ValueError):
            MessageMeta(expire_at=-1)

    def test_meta_serialization(self):
        """测试元数据序列化"""
        expire_time = int(time.time() * 1000) + 3600000
        meta = MessageMeta(
            status=MessageStatus.PROCESSING,
            retry_count=1,
            max_retries=5,
            expire_at=expire_time,
            last_error="Test error",
        )

        # 测试转换为字典
        meta_dict = meta.model_dump()
        assert meta_dict["status"] == "processing"
        assert meta_dict["retry_count"] == 1
        assert meta_dict["max_retries"] == 5
        assert meta_dict["expire_at"] == expire_time
        assert meta_dict["last_error"] == "Test error"

        # 测试JSON序列化
        meta_json = meta.model_dump_json()
        assert isinstance(meta_json, str)
        assert "processing" in meta_json

    def test_meta_from_dict(self):
        """测试从字典创建元数据"""
        expire_time = int(time.time() * 1000) + 3600000
        meta_data = {
            "status": "retrying",
            "retry_count": 2,
            "max_retries": 7,
            "expire_at": expire_time,
            "last_error": "Connection failed",
        }

        meta = MessageMeta.model_validate(meta_data)
        assert meta.status == MessageStatus.RETRYING
        assert meta.retry_count == 2
        assert meta.max_retries == 7
        assert meta.expire_at == expire_time
        assert meta.last_error == "Connection failed"


class TestMessage:
    """测试消息类"""

    def test_default_message(self):
        """测试默认消息"""
        payload = {"user_id": 123, "action": "login"}
        msg = Message(topic="user.events", payload=payload)

        assert msg.id is not None
        assert isinstance(msg.id, str)
        assert len(msg.id) > 0
        assert msg.version == "1.0"
        assert msg.topic == "user.events"
        assert msg.payload == payload
        assert msg.priority == MessagePriority.NORMAL
        assert isinstance(msg.meta, MessageMeta)
        assert msg.meta.status == MessageStatus.PENDING

    def test_custom_message(self):
        """测试自定义消息"""
        payload = {"order_id": "ord-123"}
        expire_time = int(time.time() * 1000) + 3600000
        meta = MessageMeta(
            status=MessageStatus.PROCESSING, max_retries=5, expire_at=expire_time
        )

        msg = Message(
            id="msg-custom-123",
            topic="orders.created",
            payload=payload,
            priority=MessagePriority.HIGH,
            meta=meta,
        )

        assert msg.id == "msg-custom-123"
        assert msg.topic == "orders.created"
        assert msg.payload == payload
        assert msg.priority == MessagePriority.HIGH
        assert msg.meta == meta
        assert msg.meta.status == MessageStatus.PROCESSING

    def test_message_serialization(self):
        """测试消息序列化"""
        payload = {"data": "test"}
        msg = Message(
            topic="test.topic", payload=payload, priority=MessagePriority.HIGH
        )

        # 测试转换为字典
        msg_dict = msg.model_dump()
        assert msg_dict["topic"] == "test.topic"
        assert msg_dict["payload"] == payload
        assert msg_dict["priority"] == "high"
        assert "meta" in msg_dict
        assert "id" in msg_dict

        # 测试JSON序列化
        msg_json = msg.model_dump_json()
        assert isinstance(msg_json, str)
        assert "test.topic" in msg_json
        assert "high" in msg_json

    def test_message_from_dict(self):
        """测试从字典创建消息"""
        expire_time = int(time.time() * 1000) + 3600000
        msg_data = {
            "id": "test-msg-123",
            "topic": "test.events",
            "payload": {"key": "value"},
            "priority": "high",
            "meta": {"status": "completed", "max_retries": 5, "expire_at": expire_time},
        }

        msg = Message.model_validate(msg_data)
        assert msg.id == "test-msg-123"
        assert msg.topic == "test.events"
        assert msg.payload == {"key": "value"}
        assert msg.priority == MessagePriority.HIGH
        assert msg.meta.status == MessageStatus.COMPLETED
        assert msg.meta.max_retries == 5

    def test_message_id_generation(self):
        """测试消息ID生成"""
        # 测试自动生成的ID是唯一的
        messages = [Message(topic="test", payload={}) for _ in range(10)]

        ids = [msg.id for msg in messages]
        assert len(set(ids)) == 10  # 所有ID都应该是唯一的

        # 测试ID格式（应该是UUID格式）
        for msg in messages:
            assert isinstance(msg.id, str)
            assert len(msg.id.replace("-", "")) == 32  # UUID长度

    def test_mark_processing(self):
        """测试标记消息为处理中"""
        msg = Message(topic="test", payload={})

        msg.mark_processing()

        assert msg.meta.status == MessageStatus.PROCESSING
        assert msg.meta.processing_started_at is not None
        assert msg.meta.updated_at > 0
        assert msg.meta.processing_started_at == msg.meta.updated_at

    def test_mark_completed(self):
        """测试标记消息为已完成"""
        msg = Message(topic="test", payload={})
        msg.mark_processing()

        msg.mark_completed()

        assert msg.meta.status == MessageStatus.COMPLETED
        assert msg.meta.completed_at is not None
        assert msg.meta.updated_at > 0
        assert msg.meta.completed_at == msg.meta.updated_at

    def test_mark_retry(self):
        """测试标记消息需要重试"""
        msg = Message(topic="test", payload={})
        error_msg = "Connection timeout"

        original_retry_count = msg.meta.retry_count

        msg.mark_retry(error_msg)

        assert msg.meta.status == MessageStatus.RETRYING
        assert msg.meta.retry_count == original_retry_count + 1
        assert msg.meta.last_error == error_msg
        assert msg.meta.last_retry_at is not None
        assert msg.meta.updated_at > 0
        assert msg.meta.last_retry_at == msg.meta.updated_at

    def test_mark_dead_letter(self):
        """测试标记消息为死信"""
        msg = Message(topic="test", payload={})
        reason = "Max retries exceeded"

        msg.mark_dead_letter(reason)

        assert msg.meta.status == MessageStatus.DEAD_LETTER
        assert msg.meta.last_error == reason
        assert msg.meta.dead_letter_at is not None
        assert msg.meta.updated_at > 0
        assert msg.meta.dead_letter_at == msg.meta.updated_at

    def test_mark_stuck(self):
        """测试标记消息为卡死"""
        msg = Message(topic="test", payload={})
        reason = "Processing timeout"

        msg.mark_stuck(reason)

        assert msg.meta.status == MessageStatus.STUCK_TIMEOUT
        assert msg.meta.stuck_reason == reason
        assert msg.meta.stuck_detected_at is not None
        assert msg.meta.updated_at > 0
        assert msg.meta.stuck_detected_at == msg.meta.updated_at

    def test_can_retry(self):
        """测试检查是否可以重试"""
        # 创建最大重试次数为3的消息
        expire_time = int(time.time() * 1000) + 3600000
        meta = MessageMeta(max_retries=3, expire_at=expire_time)
        msg = Message(topic="test", payload={}, meta=meta)

        # 初始状态可以重试
        assert msg.can_retry() is True

        # 重试3次后不能再重试
        for i in range(3):
            msg.mark_retry(f"Error {i + 1}")
            if i < 2:
                assert msg.can_retry() is True
            else:
                assert msg.can_retry() is False

    def test_is_expired(self):
        """测试检查消息是否过期"""
        # 未过期的消息
        future_time = int(time.time() * 1000) + 3600000
        meta = MessageMeta(expire_at=future_time)
        msg = Message(topic="test", payload={}, meta=meta)
        assert msg.is_expired() is False

        # 已过期的消息
        past_time = int(time.time() * 1000) - 3600000
        meta = MessageMeta(expire_at=past_time)
        msg = Message(topic="test", payload={}, meta=meta)
        assert msg.is_expired() is True

    def test_get_retry_delay(self):
        """测试获取重试延迟时间"""
        expire_time = int(time.time() * 1000) + 3600000

        # 使用默认重试延迟
        meta = MessageMeta(expire_at=expire_time)
        msg = Message(topic="test", payload={}, meta=meta)

        # 第一次重试
        msg.mark_retry("Error 1")
        assert msg.get_retry_delay() == 60  # 第一个延迟值

        # 第二次重试
        msg.mark_retry("Error 2")
        assert msg.get_retry_delay() == 300  # 第二个延迟值

        # 第三次重试
        msg.mark_retry("Error 3")
        assert msg.get_retry_delay() == 1800  # 第三个延迟值

        # 超过配置的重试次数，使用最后一个值
        msg.mark_retry("Error 4")
        assert msg.get_retry_delay() == 1800  # 仍然是最后一个值

    def test_get_retry_delay_custom(self):
        """测试自定义重试延迟"""
        expire_time = int(time.time() * 1000) + 3600000
        custom_delays = [10, 30, 90]
        meta = MessageMeta(retry_delays=custom_delays, expire_at=expire_time)
        msg = Message(topic="test", payload={}, meta=meta)

        msg.mark_retry("Error 1")
        assert msg.get_retry_delay() == 10

        msg.mark_retry("Error 2")
        assert msg.get_retry_delay() == 30

        msg.mark_retry("Error 3")
        assert msg.get_retry_delay() == 90

    def test_get_retry_delay_empty_list(self):
        """测试空重试延迟列表"""
        expire_time = int(time.time() * 1000) + 3600000
        meta = MessageMeta(retry_delays=[], expire_at=expire_time)
        msg = Message(topic="test", payload={}, meta=meta)

        msg.mark_retry("Error")
        assert msg.get_retry_delay() == 60  # 默认值

    def test_model_dump_and_validate(self):
        """测试Pydantic模型序列化和反序列化方法"""
        payload = {"test": "data"}
        msg = Message(topic="test.topic", payload=payload)

        # 转换为字典
        msg_dict = msg.model_dump()
        assert isinstance(msg_dict, dict)
        assert msg_dict["topic"] == "test.topic"
        assert msg_dict["payload"] == payload

        # 从字典创建
        restored_msg = Message.model_validate(msg_dict)
        assert restored_msg.id == msg.id
        assert restored_msg.topic == msg.topic
        assert restored_msg.payload == msg.payload
        assert restored_msg.priority == msg.priority

    def test_complex_payload(self):
        """测试复杂载荷"""
        complex_payload = {
            "user": {"id": 123, "name": "张三", "roles": ["admin", "user"]},
            "action": "login",
            "timestamp": "2024-01-01T12:00:00Z",
            "metadata": {
                "ip": "192.168.1.1",
                "user_agent": "Mozilla/5.0...",
                "session_id": "sess-abc123",
            },
            "numbers": [1, 2, 3.14, -5],
            "flags": {"new_user": False, "premium": True},
        }

        msg = Message(topic="user.login", payload=complex_payload)

        assert msg.payload == complex_payload
        assert msg.payload["user"]["name"] == "张三"
        assert msg.payload["numbers"] == [1, 2, 3.14, -5]
        assert msg.payload["flags"]["premium"] is True

        # 测试序列化和反序列化保持数据完整性
        msg_dict = msg.model_dump()
        restored_msg = Message.model_validate(msg_dict)
        assert restored_msg.payload == complex_payload
