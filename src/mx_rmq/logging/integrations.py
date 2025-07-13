"""
日志集成辅助模块
提供各种日志库的集成配置函数
"""

import logging
from typing import Optional, Dict, Any


def setup_loguru_integration(
    level: str = "INFO",
    format_string: Optional[str] = None,
    intercept_standard_logging: bool = True,
) -> bool:
    """
    设置 Loguru 集成

    Args:
        level: 日志级别
        format_string: 自定义格式字符串
        intercept_standard_logging: 是否拦截标准 logging 模块的日志

    Returns:
        bool: 是否成功设置
    """
    try:
        from loguru import logger

        # 移除默认处理器
        logger.remove()

        # 设置默认格式
        if format_string is None:
            format_string = (
                "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
                "{level: <8} | "
                "{name}:{function}:{line} - "
                "{message}"
            )

        # 添加控制台处理器
        logger.add(
            sink=lambda msg: print(msg, end=""), format=format_string, level=level
        )

        # 如果需要拦截标准 logging
        if intercept_standard_logging:
            setup_loguru_intercept()

        return True

    except ImportError:
        return False


def setup_loguru_intercept() -> bool:
    """
    设置 Loguru 拦截标准 logging 模块

    Returns:
        bool: 是否成功设置
    """
    try:
        from loguru import logger

        class InterceptHandler(logging.Handler):
            def emit(self, record):
                # 获取对应的 Loguru 级别
                try:
                    level = logger.level(record.levelname).name
                except ValueError:
                    level = record.levelno

                # 找到调用者以获取正确的堆栈深度
                frame, depth = logging.currentframe(), 2
                while frame.f_back and frame.f_code.co_filename == logging.__file__:
                    frame = frame.f_back
                    depth += 1

                logger.opt(depth=depth, exception=record.exc_info).log(
                    level, record.getMessage()
                )

        # 移除现有处理器
        for handler in logging.root.handlers[:]:
            logging.root.removeHandler(handler)

        # 设置拦截器
        logging.basicConfig(handlers=[InterceptHandler()], level=logging.INFO)

        # 确保特定日志器传播到根日志器
        loggers_to_intercept = [
            "mx_rmq",
            "uvicorn",
            "uvicorn.access",
            "uvicorn.error",
            "fastapi",
            "asyncio",
            "starlette",
        ]

        for logger_name in loggers_to_intercept:
            logging_logger = logging.getLogger(logger_name)
            logging_logger.handlers = []
            logging_logger.propagate = True

        return True

    except ImportError:
        return False


def setup_structlog_integration(
    processors: Optional[list] = None,
    logger_factory: Optional[Any] = None,
    wrapper_class: Optional[Any] = None,
    **configure_kwargs: Any,
) -> bool:
    """
    设置 Structlog 集成

    Args:
        processors: 处理器列表
        logger_factory: 日志器工厂
        wrapper_class: 包装器类
        **configure_kwargs: 其他配置参数

    Returns:
        bool: 是否成功设置
    """
    try:
        import structlog

        # 设置默认配置
        if processors is None:
            processors = [
                structlog.stdlib.filter_by_level,
                structlog.stdlib.add_logger_name,
                structlog.stdlib.add_log_level,
                structlog.stdlib.PositionalArgumentsFormatter(),
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.processors.UnicodeDecoder(),
                structlog.processors.JSONRenderer(),
            ]

        if logger_factory is None:
            logger_factory = structlog.stdlib.LoggerFactory()

        if wrapper_class is None:
            wrapper_class = structlog.stdlib.BoundLogger

        # 配置 structlog
        structlog.configure(
            processors=processors,
            logger_factory=logger_factory,
            wrapper_class=wrapper_class,
            context_class=dict,
            cache_logger_on_first_use=True,
            **configure_kwargs,
        )

        return True

    except ImportError:
        return False


def setup_standard_logging(
    level: str = "INFO",
    format_string: Optional[str] = None,
    handlers: Optional[Dict[str, Dict[str, Any]]] = None,
) -> bool:
    """
    设置标准 logging 集成

    Args:
        level: 日志级别
        format_string: 格式字符串
        handlers: 处理器配置字典

    Returns:
        bool: 总是返回 True，因为标准 logging 总是可用的
    """
    # 设置默认格式
    if format_string is None:
        format_string = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    # 基本配置
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO), format=format_string
    )

    # 如果提供了处理器配置
    if handlers:
        root_logger = logging.getLogger()

        for handler_name, handler_config in handlers.items():
            handler_type = handler_config.get("type", "StreamHandler")
            handler_level = handler_config.get("level", level)
            handler_format = handler_config.get("format", format_string)

            # 创建处理器
            if handler_type == "FileHandler":
                filename = handler_config.get("filename", "app.log")
                handler = logging.FileHandler(filename)
            elif handler_type == "RotatingFileHandler":
                from logging.handlers import RotatingFileHandler

                filename = handler_config.get("filename", "app.log")
                max_bytes = handler_config.get("maxBytes", 1024 * 1024 * 10)  # 10MB
                backup_count = handler_config.get("backupCount", 5)
                handler = RotatingFileHandler(
                    filename, maxBytes=max_bytes, backupCount=backup_count
                )
            else:  # StreamHandler
                handler = logging.StreamHandler()

            # 设置级别和格式
            handler.setLevel(getattr(logging, handler_level.upper(), logging.INFO))
            formatter = logging.Formatter(handler_format)
            handler.setFormatter(formatter)

            # 添加到根日志器
            root_logger.addHandler(handler)

    return True


def auto_configure_logging(
    prefer_backend: Optional[str] = None, level: str = "INFO", **kwargs: Any
) -> str:
    """
    自动配置最佳可用的日志后端

    Args:
        prefer_backend: 首选后端 (loguru, structlog, standard)
        level: 日志级别
        **kwargs: 传递给具体配置函数的参数

    Returns:
        str: 实际使用的日志后端名称
    """
    from .logging_facade import LoggerFactory

    # 如果指定了首选后端，先尝试配置
    if prefer_backend == "loguru":
        if setup_loguru_integration(level=level, **kwargs):
            LoggerFactory.set_adapter_type("loguru")
            return "loguru"
    elif prefer_backend == "structlog":
        if setup_structlog_integration(**kwargs):
            LoggerFactory.set_adapter_type("structlog")
            return "structlog"
    elif prefer_backend == "standard":
        setup_standard_logging(level=level, **kwargs)
        LoggerFactory.set_adapter_type("standard")
        return "standard"

    # 自动检测最佳后端
    # 优先级：loguru > structlog > standard

    # 尝试 loguru
    if setup_loguru_integration(level=level, **kwargs):
        LoggerFactory.set_adapter_type("loguru")
        return "loguru"

    # 尝试 structlog
    if setup_structlog_integration(**kwargs):
        LoggerFactory.set_adapter_type("structlog")
        return "structlog"

    # 回退到标准 logging
    setup_standard_logging(level=level, **kwargs)
    LoggerFactory.set_adapter_type("standard")
    return "standard"


def get_available_backends() -> Dict[str, bool]:
    """
    获取可用的日志后端

    Returns:
        Dict[str, bool]: 各个后端的可用性状态
    """
    backends = {
        "standard": True,  # 标准库总是可用
        "loguru": False,
        "structlog": False,
    }

    # 检查 loguru
    try:
        import loguru

        backends["loguru"] = True
    except ImportError:
        pass

    # 检查 structlog
    try:
        import structlog

        backends["structlog"] = True
    except ImportError:
        pass

    return backends
