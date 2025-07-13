"""
消息队列配置模块
"""

from typing import Any

from pydantic import BaseModel, Field, field_validator


class MQConfig(BaseModel):
    """消息队列配置类"""

    model_config = {"frozen": True}  # 配置对象不可变

    # Redis连接配置
    redis_url: str = Field(default="redis://localhost:6379", description="Redis连接URL")
    redis_db: int = Field(default=0, ge=0, le=15, description="Redis数据库编号")
    redis_password: str | None = Field(default=None, description="Redis密码")

    # 队列前缀配置
    queue_prefix: str = Field(default="", description="队列前缀，用于逻辑隔离")

    connection_pool_size: int = Field(
        default=20, ge=5, le=100, description="Redis连接池大小"
    )

    # 消费者配置
    max_workers: int = Field(default=5, ge=1, le=50, description="最大工作协程数")
    task_queue_size: int = Field(
        default=8, ge=5, le=300, description="本地任务队列大小"
    )

    # 消息生命周期配置
    message_ttl: int = Field(
        default=86400,  # 24小时
        ge=1,
        description="消息TTL（秒）",
    )
    processing_timeout: int = Field(
        default=180,  # 3分钟
        ge=30,
        description="消息处理超时时间（秒）",
    )

    # 重试配置
    max_retries: int = Field(default=3, ge=0, le=10, description="最大重试次数")
    retry_delays: list[int] = Field(
        default_factory=lambda: [60, 300, 1800],  # 1分钟、5分钟、30分钟
        description="重试延迟间隔（秒）",
    )

    # 死信队列配置
    enable_dead_letter: bool = Field(default=True, description="是否启用死信队列")

    # 监控配置
    monitor_interval: int = Field(default=30, ge=5, description="监控检查间隔（秒）")
    expired_check_interval: int = Field(
        default=10, ge=5, description="过期消息检查间隔（秒）"
    )
    processing_monitor_interval: int = Field(
        default=60, ge=30, description="处理中队列监控间隔（秒）"
    )
    batch_size: int = Field(default=100, ge=10, le=1000, description="批处理大小")

    # 日志配置
    log_level: str = Field(default="INFO", description="日志级别")

    # 新增处理器超时配置
    handler_timeout: float = Field(
        default=60.0, ge=1.0, description="默认业务逻辑处理超时时间（秒）"
    )
    handler_timeouts: dict[str, float] = Field(
        default_factory=dict,
        description="主题级别的超时配置，如 {'heavy_task': 60, 'light_task': 10}",
    )
    enable_handler_timeout: bool = Field(
        default=True, description="是否启用业务逻辑超时控制"
    )

    @field_validator("task_queue_size")
    @classmethod
    def validate_task_queue_size(cls, v: int, info: Any) -> int:
        """验证任务队列大小必须大于最大工作数"""
        # 卫语句：如果没有 max_workers 信息则直接返回
        if not (hasattr(info, "data") and "max_workers" in info.data):
            return v

        max_workers = info.data["max_workers"]
        # 卫语句：验证失败时抛出异常
        if v <= max_workers:
            raise ValueError(
                f"task_queue_size ({v}) 必须大于 max_workers ({max_workers})"
            )
        return v

    @field_validator("retry_delays")
    @classmethod
    def validate_retry_delays(cls, v: list[int]) -> list[int]:
        """验证重试延迟配置"""
        # 卫语句：列表为空时抛出异常
        if not v:
            raise ValueError("重试延迟列表不能为空")

        # 卫语句：存在非正数时抛出异常
        if any(delay <= 0 for delay in v):
            raise ValueError("重试延迟必须大于0")

        return v

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """验证日志级别"""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"日志级别必须是: {', '.join(valid_levels)}")
        return v.upper()

    @field_validator("queue_prefix")
    @classmethod
    def validate_queue_prefix(cls, v: str) -> str:
        """验证队列前缀"""
        # 卫语句：空前缀直接返回
        if not v:
            return v

        import re

        # 卫语句：格式不符合要求时抛出异常
        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError("队列前缀只能包含字母、数字、下划线和连字符")

        # 卫语句：前缀格式错误时抛出异常
        if v.startswith("-") or v.endswith("-"):
            raise ValueError("队列前缀不能以连字符开头或结尾")

        return v
