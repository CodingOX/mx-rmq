"""
消息数据模型
"""

import time
import uuid
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class MessageStatus(str, Enum):
    """消息状态枚举"""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    RETRYING = "retrying"
    DEAD_LETTER = "dead_letter"
    STUCK_TIMEOUT = "stuck_timeout"


class MessagePriority(str, Enum):
    """消息优先级枚举"""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


class MessageMeta(BaseModel):
    """消息元数据"""

    model_config = {"extra": "forbid"}

    status: MessageStatus = Field(default=MessageStatus.PENDING, description="消息状态")
    retry_count: int = Field(default=0, ge=0, description="重试次数")
    max_retries: int = Field(default=3, ge=0, description="最大重试次数")
    retry_delays: list[int] = Field(
        default_factory=lambda: [60, 300, 1800], description="重试延迟间隔（秒）"
    )
    last_error: str | None = Field(default=None, description="最后一次错误信息")
    expire_at: int = Field(
        default_factory=lambda: int(time.time() * 1000) + 86400000,  # 默认24小时后过期
        ge=0,
        description="过期时间戳 ms",
    )
    created_at: int = Field(
        default_factory=lambda: int(time.time() * 1000), description="创建时间戳 ms"
    )
    updated_at: int = Field(
        default_factory=lambda: int(time.time() * 1000), description="更新时间戳 ms"
    )
    last_retry_at: int | None = Field(default=None, description="最后重试时间戳 ms")
    processing_started_at: int | None = Field(
        default=None, description="处理开始时间戳 ms"
    )
    completed_at: int | None = Field(default=None, description="完成时间戳 ms")
    dead_letter_at: int | None = Field(
        default=None, description="进入死信队列时间戳 ms"
    )
    stuck_detected_at: int | None = Field(
        default=None, description="检测到卡死时间戳 ms"
    )
    stuck_reason: str | None = Field(default=None, description="卡死原因")
    retried_from_dlq_at: int | None = Field(
        default=None, description="从死信队列重试时间戳 ms"
    )


class Message(BaseModel):
    """消息主体"""

    # 禁止额外字段，如果传入未定义的字段会抛出验证错误
    model_config = {"extra": "forbid"}

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="消息唯一ID")
    version: str = Field(default="1.0", description="消息格式版本")
    topic: str = Field(description="主题名称")
    payload: dict[str, Any] = Field(description="消息负载")
    priority: MessagePriority = Field(
        default=MessagePriority.NORMAL, description="消息优先级"
    )
    created_at: int = Field(
        default_factory=lambda: int(time.time() * 1000),
        description="创建时间戳",
        alias="createdAt",
    )
    meta: MessageMeta = Field(default_factory=MessageMeta, description="消息元数据")

    def mark_processing(self) -> None:
        """标记消息为处理中"""
        self.meta.status = MessageStatus.PROCESSING
        self.meta.processing_started_at = int(time.time() * 1000)
        self.meta.updated_at = int(time.time() * 1000)

    def mark_completed(self) -> None:
        """标记消息为已完成"""
        self.meta.status = MessageStatus.COMPLETED
        self.meta.completed_at = int(time.time() * 1000)
        self.meta.updated_at = int(time.time() * 1000)

    def mark_retry(self, error: str) -> None:
        """标记消息需要重试"""
        self.meta.status = MessageStatus.RETRYING
        self.meta.retry_count += 1
        # 这里 error 限定长度为 50 字符最长
        self.meta.last_error = error[:50]
        self.meta.last_retry_at = int(time.time() * 1000)
        self.meta.updated_at = int(time.time() * 1000)

    def mark_dead_letter(self, reason: str) -> None:
        """标记消息为死信"""
        self.meta.status = MessageStatus.DEAD_LETTER
        self.meta.last_error = reason[:50]
        self.meta.dead_letter_at = int(time.time() * 1000)
        self.meta.updated_at = int(time.time() * 1000)

    def mark_stuck(self, reason: str) -> None:
        """标记消息为卡死"""
        self.meta.status = MessageStatus.STUCK_TIMEOUT
        self.meta.stuck_reason = reason[:50]
        self.meta.stuck_detected_at = int(time.time() * 1000)
        self.meta.updated_at = int(time.time() * 1000)

    def can_retry(self) -> bool:
        """检查是否可以重试"""
        return self.meta.retry_count < self.meta.max_retries

    def is_expired(self) -> bool:
        """检查消息是否过期"""
        return int(time.time() * 1000) > self.meta.expire_at

    def get_retry_delay(self) -> int:
        """获取重试延迟时间"""
        retry_delays = self.meta.retry_delays
        if not retry_delays:
            return 60  # 默认1分钟

        # retry_count从1开始，数组索引从0开始，所以要减1
        # 使用最后一个延迟值如果重试次数超过配置长度
        index = min(self.meta.retry_count - 1, len(retry_delays) - 1)
        return retry_delays[index]
