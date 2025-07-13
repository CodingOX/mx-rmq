"""
日志门面模块 - 类似 SLF4J 的设计模式
支持多种日志后端：标准库 logging、loguru、structlog
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Optional, Protocol, runtime_checkable


@runtime_checkable
class LoggerInterface(Protocol):
    """日志器接口定义 - 类似 SLF4J Logger"""

    def debug(self, message: str, **kwargs: Any) -> None:
        """记录 DEBUG 级别日志"""
        ...

    def info(self, message: str, **kwargs: Any) -> None:
        """记录 INFO 级别日志"""
        ...

    def warning(self, message: str, **kwargs: Any) -> None:
        """记录 WARNING 级别日志"""
        ...

    def error(
        self, message: str, error: Optional[Exception] = None, **kwargs: Any
    ) -> None:
        """记录 ERROR 级别日志"""
        ...

    def critical(self, message: str, **kwargs: Any) -> None:
        """记录 CRITICAL 级别日志"""
        ...


class LoggerAdapter(ABC):
    """抽象日志适配器基类"""

    def __init__(self, name: str) -> None:
        self.name = name

    @abstractmethod
    def debug(self, message: str, **kwargs: Any) -> None:
        """记录 DEBUG 级别日志"""
        pass

    @abstractmethod
    def info(self, message: str, **kwargs: Any) -> None:
        """记录 INFO 级别日志"""
        pass

    @abstractmethod
    def warning(self, message: str, **kwargs: Any) -> None:
        """记录 WARNING 级别日志"""
        pass

    @abstractmethod
    def error(
        self, message: str, error: Optional[Exception] = None, **kwargs: Any
    ) -> None:
        """记录 ERROR 级别日志"""
        pass

    @abstractmethod
    def critical(self, message: str, **kwargs: Any) -> None:
        """记录 CRITICAL 级别日志"""
        pass


class StandardLoggingAdapter(LoggerAdapter):
    """标准库 logging 适配器"""

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self._logger = logging.getLogger(name)
        # 添加 NullHandler 避免 "No handlers could be found" 警告
        if not self._logger.handlers:
            self._logger.addHandler(logging.NullHandler())

    def _format_context(self, **kwargs: Any) -> str:
        """格式化上下文信息"""
        if not kwargs:
            return ""
        context_parts = []
        for key, value in kwargs.items():
            context_parts.append(f"{key}={value}")
        return " - " + ", ".join(context_parts)

    def debug(self, message: str, **kwargs: Any) -> None:
        context = self._format_context(**kwargs)
        self._logger.debug(f"{message}{context}")

    def info(self, message: str, **kwargs: Any) -> None:
        context = self._format_context(**kwargs)
        self._logger.info(f"{message}{context}")

    def warning(self, message: str, **kwargs: Any) -> None:
        context = self._format_context(**kwargs)
        self._logger.warning(f"{message}{context}")

    def error(
        self, message: str, error: Optional[Exception] = None, **kwargs: Any
    ) -> None:
        context = self._format_context(**kwargs)
        full_message = f"{message}{context}"
        if error:
            full_message += f" - error: {error} ({type(error).__name__})"
        self._logger.error(full_message, exc_info=error is not None)

    def critical(self, message: str, **kwargs: Any) -> None:
        context = self._format_context(**kwargs)
        self._logger.critical(f"{message}{context}")


class LoguruAdapter(LoggerAdapter):
    """Loguru 适配器"""

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self._available = False
        self._logger = None
        self._fallback = None

        try:
            import loguru

            self._logger = loguru.logger.bind(component=name)
            self._available = True
        except ImportError:
            # loguru 不可用时回退到标准 logging
            self._fallback = StandardLoggingAdapter(name)

    def debug(self, message: str, **kwargs: Any) -> None:
        if self._available:
            self._logger.debug(message, **kwargs)
        else:
            self._fallback.debug(message, **kwargs)

    def info(self, message: str, **kwargs: Any) -> None:
        if self._available:
            self._logger.info(message, **kwargs)
        else:
            self._fallback.info(message, **kwargs)

    def warning(self, message: str, **kwargs: Any) -> None:
        if self._available:
            self._logger.warning(message, **kwargs)
        else:
            self._fallback.warning(message, **kwargs)

    def error(
        self, message: str, error: Optional[Exception] = None, **kwargs: Any
    ) -> None:
        if self._available:
            if error:
                kwargs.update({"error": str(error), "error_type": type(error).__name__})
            self._logger.error(message, **kwargs)
        else:
            self._fallback.error(message, error, **kwargs)

    def critical(self, message: str, **kwargs: Any) -> None:
        if self._available:
            self._logger.critical(message, **kwargs)
        else:
            self._fallback.critical(message, **kwargs)


class StructlogAdapter(LoggerAdapter):
    """Structlog 适配器"""

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self._available = False
        self._logger = None
        self._fallback = None

        try:
            import structlog

            self._logger = structlog.get_logger(name)
            self._available = True
        except ImportError:
            # structlog 不可用时回退到标准 logging
            self._fallback = StandardLoggingAdapter(name)

    def debug(self, message: str, **kwargs: Any) -> None:
        if self._available:
            self._logger.debug(message, **kwargs)
        else:
            self._fallback.debug(message, **kwargs)

    def info(self, message: str, **kwargs: Any) -> None:
        if self._available:
            self._logger.info(message, **kwargs)
        else:
            self._fallback.info(message, **kwargs)

    def warning(self, message: str, **kwargs: Any) -> None:
        if self._available:
            self._logger.warning(message, **kwargs)
        else:
            self._fallback.warning(message, **kwargs)

    def error(
        self, message: str, error: Optional[Exception] = None, **kwargs: Any
    ) -> None:
        if self._available:
            if error:
                kwargs.update({"error": str(error), "error_type": type(error).__name__})
            self._logger.error(message, **kwargs)
        else:
            self._fallback.error(message, error, **kwargs)

    def critical(self, message: str, **kwargs: Any) -> None:
        if self._available:
            self._logger.critical(message, **kwargs)
        else:
            self._fallback.critical(message, **kwargs)


class LoggerFactory:
    """日志工厂类 - 类似 SLF4J 的 LoggerFactory"""

    # 适配器类型：auto, standard, loguru, structlog
    _adapter_type: str = "auto"

    @classmethod
    def set_adapter_type(cls, adapter_type: str) -> None:
        """
        设置全局适配器类型

        Args:
            adapter_type: 适配器类型 (auto, standard, loguru, structlog)
        """
        valid_types = {"auto", "standard", "loguru", "structlog"}
        if adapter_type not in valid_types:
            raise ValueError(
                f"无效的适配器类型: {adapter_type}. 有效类型: {valid_types}"
            )
        cls._adapter_type = adapter_type

    @classmethod
    def get_logger(cls, name: str) -> LoggerAdapter:
        """
        获取日志器实例 - 类似 SLF4J 的 getLogger

        Args:
            name: 日志器名称

        Returns:
            LoggerAdapter: 日志器适配器实例
        """
        if cls._adapter_type == "standard":
            return StandardLoggingAdapter(name)
        elif cls._adapter_type == "loguru":
            return LoguruAdapter(name)
        elif cls._adapter_type == "structlog":
            return StructlogAdapter(name)
        else:  # auto
            return cls._auto_detect_adapter(name)

    @classmethod
    def _auto_detect_adapter(cls, name: str) -> LoggerAdapter:
        """
        自动检测最佳适配器

        Args:
            name: 日志器名称

        Returns:
            LoggerAdapter: 最适合的日志器适配器
        """
        # 检查用户是否已经配置了 loguru
        try:
            import loguru

            # 检查 loguru 是否已经被配置
            if hasattr(loguru.logger, "_core") and loguru.logger._core.handlers:
                return LoguruAdapter(name)
        except ImportError:
            pass

        # 检查用户是否已经配置了 structlog
        try:
            import structlog

            # 简单检查 structlog 是否可用
            structlog.get_logger()
            return StructlogAdapter(name)
        except ImportError:
            pass

        # 默认使用标准 logging
        return StandardLoggingAdapter(name)


def get_logger(name: Optional[str] = None) -> LoggerAdapter:
    """
    获取日志器的便捷函数 - 类似 SLF4J 的静态导入

    Args:
        name: 日志器名称，如果为 None 则自动获取调用者模块名

    Returns:
        LoggerAdapter: 日志器适配器实例
    """
    if name is None:
        import inspect

        frame = inspect.currentframe()
        if frame and frame.f_back:
            caller_globals = frame.f_back.f_globals
            name = caller_globals.get("__name__", "unknown")
        else:
            name = "unknown"

    return LoggerFactory.get_logger(name)
