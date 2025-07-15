"""
日志子系统
使用 Python 标准 logging，遵循最佳实践
"""

import logging
import sys
from typing import Optional


class ColoredFormatter(logging.Formatter):
    """彩色日志格式器"""
    
    # ANSI 颜色代码
    COLORS = {
        'DEBUG': '\033[36m',    # 青色
        'INFO': '\033[32m',     # 绿色
        'WARNING': '\033[33m',  # 黄色
        'ERROR': '\033[31m',    # 红色
        'CRITICAL': '\033[35m', # 紫色
        'RESET': '\033[0m'      # 重置
    }
    
    def format(self, record):
        # 获取原始格式化的消息
        log_message = super().format(record)
        
        # 获取日志级别对应的颜色
        color = self.COLORS.get(record.levelname, self.COLORS['RESET'])
        reset = self.COLORS['RESET']
        
        # 只对级别名称添加颜色
        colored_level = f"{color}{record.levelname}{reset}"
        
        # 替换级别名称为彩色版本
        log_message = log_message.replace(record.levelname, colored_level)
        
        return log_message


# 标准的日志获取函数
def get_logger(name: Optional[str] = None) -> logging.Logger:
    """
    获取标准日志器实例
    
    Args:
        name: 日志器名称，如果为 None 则使用 mx_rmq
        
    Returns:
        logging.Logger: 标准日志器实例
    """
    if name is None:
        name = "mx_rmq"
    
    logger = logging.getLogger(name)
    
    # 添加 NullHandler 避免警告，符合 Python 库最佳实践
    if not logger.handlers:
        logger.addHandler(logging.NullHandler())
    
    return logger


def setup_basic_logging(level: str = "INFO", include_location: bool = True) -> None:
    """
    快速配置基本的日志输出
    
    Args:
        level: 日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        include_location: 是否包含文件位置信息（文件名、行号、函数名）
    
    Examples:
        >>> from mx_rmq.logging import setup_basic_logging
        >>> setup_basic_logging("INFO")  # 配置基本日志输出（包含位置信息）
        >>> setup_basic_logging("INFO", include_location=False)  # 生产环境格式
    """
    # 获取根 mx_rmq 日志器
    logger = logging.getLogger("mx_rmq")
    
    # 如果已经配置过，先清除
    if logger.handlers:
        logger.handlers.clear()
    
    # 创建控制台处理器
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(getattr(logging, level.upper()))
    
    # 设置格式 - 根据参数选择是否包含位置信息
    if include_location:
        # 开发环境格式：包含文件名、行号、函数名
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d:%(funcName)s - %(message)s'
        )
    else:
        # 生产环境格式：简洁格式
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
    handler.setFormatter(formatter)
    
    # 添加处理器
    logger.addHandler(handler)
    logger.setLevel(getattr(logging, level.upper()))
    
    # 防止重复输出
    logger.propagate = False


def setup_colored_logging(level: str = "INFO", include_location: bool = True) -> None:
    """
    快速配置彩色日志输出
    
    Args:
        level: 日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        include_location: 是否包含文件位置信息（文件名、行号、函数名）
    
    Examples:
        >>> from mx_rmq.logging import setup_colored_logging
        >>> setup_colored_logging("INFO")  # 配置彩色日志输出（包含位置信息）
        >>> setup_colored_logging("INFO", include_location=False)  # 生产环境彩色格式
    """
    # 获取根 mx_rmq 日志器
    logger = logging.getLogger("mx_rmq")
    
    # 如果已经配置过，先清除
    if logger.handlers:
        logger.handlers.clear()
    
    # 创建控制台处理器
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(getattr(logging, level.upper()))
    
    # 设置彩色格式器 - 根据参数选择是否包含位置信息
    if include_location:
        # 开发环境格式：包含文件名、行号、函数名
        formatter = ColoredFormatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d:%(funcName)s - %(message)s'
        )
    else:
        # 生产环境格式：简洁格式
        formatter = ColoredFormatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
    handler.setFormatter(formatter)
    
    # 添加处理器
    logger.addHandler(handler)
    logger.setLevel(getattr(logging, level.upper()))
    
    # 防止重复输出
    logger.propagate = False


def setup_simple_colored_logging(level: str = "INFO", include_location: bool = True) -> None:
    """
    配置简洁的彩色日志输出（不显示时间戳）
    
    Args:
        level: 日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        include_location: 是否包含文件位置信息（文件名、行号、函数名）
    
    Examples:
        >>> from mx_rmq.logging import setup_simple_colored_logging
        >>> setup_simple_colored_logging("INFO")  # 配置简洁彩色日志（包含位置信息）
        >>> setup_simple_colored_logging("INFO", include_location=False)  # 极简格式
    """
    # 获取根 mx_rmq 日志器
    logger = logging.getLogger("mx_rmq")
    
    # 如果已经配置过，先清除
    if logger.handlers:
        logger.handlers.clear()
    
    # 创建控制台处理器
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(getattr(logging, level.upper()))
    
    # 设置简洁的彩色格式器 - 根据参数选择是否包含位置信息
    if include_location:
        # 开发环境格式：包含文件名、行号、函数名
        formatter = ColoredFormatter(
            '%(name)s - %(levelname)s - %(filename)s:%(lineno)d:%(funcName)s - %(message)s'
        )
    else:
        # 生产环境格式：极简格式
        formatter = ColoredFormatter(
            '%(name)s - %(levelname)s - %(message)s'
        )
    handler.setFormatter(formatter)
    
    # 添加处理器
    logger.addHandler(handler)
    logger.setLevel(getattr(logging, level.upper()))
    
    # 防止重复输出
    logger.propagate = False


# 向后兼容的简化服务类
class LoggerService:
    """
    向后兼容的日志服务类
    内部使用标准 logging
    """
    
    def __init__(self, component_name: str = "mx_rmq") -> None:
        self.component_name = component_name
        self._logger = logging.getLogger(f"mx_rmq.{component_name}")
        
        # 确保有 NullHandler
        if not self._logger.handlers:
            self._logger.addHandler(logging.NullHandler())
    
    @property
    def logger(self) -> logging.Logger:
        """获取标准日志器实例"""
        return self._logger
    
    def log_message_event(self, event: str, message_id: str, topic: str, **kwargs) -> None:
        """记录消息相关事件"""
        extra_info = f", {', '.join(f'{k}={v}' for k, v in kwargs.items())}" if kwargs else ""
        self._logger.info(f"{event} - message_id={message_id}, topic={topic}{extra_info}")
    
    def log_error(self, event: str, error: Exception, **kwargs) -> None:
        """记录错误事件"""
        extra_info = f", {', '.join(f'{k}={v}' for k, v in kwargs.items())}" if kwargs else ""
        self._logger.error(f"{event}{extra_info}", exc_info=error)
    
    def log_metric(self, metric_name: str, value, **kwargs) -> None:
        """记录指标事件"""
        extra_info = f", {', '.join(f'{k}={v}' for k, v in kwargs.items())}" if kwargs else ""
        self._logger.info(f"metric: {metric_name}={value}{extra_info}")


# 便利函数，用于向后兼容
def get_queue_logger() -> logging.Logger:
    """获取队列日志器"""
    return get_logger("mx_rmq.queue")


def get_component_logger(component: str) -> logging.Logger:
    """获取组件日志器"""
    return get_logger(f"mx_rmq.{component}")


__all__ = [
    # 标准日志接口
    "get_logger",
    "get_queue_logger", 
    "get_component_logger",
    # 日志配置函数
    "setup_basic_logging",
    "setup_colored_logging",
    "setup_simple_colored_logging",
    # 彩色格式器
    "ColoredFormatter",
    # 向后兼容的服务接口
    "LoggerService",
]
