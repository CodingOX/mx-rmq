"""
日志服务模块 - 重构为使用门面模式
支持多种日志后端，保持向后兼容性
"""

from typing import Any

from .facade import LoggerAdapter, get_logger


def setup_logging(level: str = "INFO") -> LoggerAdapter:
    """
    设置日志 - 兼容性函数

    注意：由于使用门面模式，具体的日志配置应该由用户在应用层完成
    这个函数主要用于向后兼容

    Args:
        level: 日志级别

    Returns:
        配置好的logger实例
    """
    # 获取 mx_rmq 的日志器
    logger = get_logger("mx_rmq")

    # 如果用户使用标准 logging，可以配置基本设置
    import logging

    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=getattr(logging, level.upper(), logging.INFO),
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )

    return logger


def get_logger_instance(name: str = "mx_rmq") -> LoggerAdapter:
    """
    获取logger实例 - 兼容性函数

    Args:
        name: logger名称

    Returns:
        logger实例
    """
    return get_logger(name)


class LoggerService:
    """日志服务类 - 使用门面模式，支持多种日志后端"""

    def __init__(self, component_name: str = "mx_rmq") -> None:
        """
        初始化日志服务

        Args:
            component_name: 组件名称，用于日志标识
        """
        self.component_name = component_name
        self._logger = get_logger(f"mx_rmq.{component_name}")

    @property
    def logger(self) -> LoggerAdapter:
        """获取日志器实例"""
        return self._logger

    def log_message_event(
        self, event: str, message_id: str, topic: str, **kwargs: Any
    ) -> None:
        """
        记录消息相关事件

        Args:
            event: 事件类型
            message_id: 消息ID
            topic: 主题
            **kwargs: 额外的上下文信息
        """
        self._logger.info(event, message_id=message_id, topic=topic, **kwargs)

    def log_error(self, event: str, error: Exception, **kwargs: Any) -> None:
        """
        记录错误事件

        Args:
            event: 事件描述
            error: 异常对象
            **kwargs: 额外的上下文信息
        """
        self._logger.error(event, error=error, **kwargs)

    def log_metric(self, metric_name: str, value: Any, **kwargs: Any) -> None:
        """
        记录指标事件

        Args:
            metric_name: 指标名称
            value: 指标值
            **kwargs: 额外的上下文信息
        """
        self._logger.info("metric", metric_name=metric_name, value=value, **kwargs)
