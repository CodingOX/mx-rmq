"""信号处理工具类

提供可选的信号处理功能，用于优雅关机。
用户可以选择使用此工具类或自行实现信号处理逻辑。
"""

import asyncio
import signal
from typing import Any, Callable, Optional
from loguru import logger


class SignalHandler:
    """信号处理器工具类
    
    提供标准的信号处理功能，用于优雅关机。
    这是一个独立的工具类，不与RedisMessageQueue耦合。
    """
    
    def __init__(self, shutdown_callback: Callable[[], Any]):
        """初始化信号处理器
        
        Args:
            shutdown_callback: 收到停机信号时调用的回调函数
        """
        self.shutdown_callback = shutdown_callback
        self._original_handlers: dict[int, Any] = {}
        self._installed = False
    
    def install(self, signals: Optional[list[int]] = None) -> None:
        """安装信号处理器
        
        Args:
            signals: 要处理的信号列表，默认为[SIGINT, SIGTERM]
        """
        if self._installed:
            logger.warning("信号处理器已经安装")
            return
            
        if signals is None:
            signals = [signal.SIGINT, signal.SIGTERM]
        
        def signal_handler(signum: int, frame: Any) -> None:
            logger.info(f"收到停机信号: {signum}")
            
            # 如果回调是协程函数，创建任务
            if asyncio.iscoroutinefunction(self.shutdown_callback):
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(self.shutdown_callback())
                except RuntimeError:
                    # 没有运行的事件循环，直接调用
                    asyncio.run(self.shutdown_callback())
            else:
                # 同步回调
                self.shutdown_callback()
        
        # 保存原始处理器并安装新的
        for sig in signals:
            try:
                self._original_handlers[sig] = signal.signal(sig, signal_handler)
                logger.debug(f"已安装信号处理器: {sig}")
            except (OSError, ValueError) as e:
                logger.warning(f"无法安装信号处理器 {sig}: {e}")
        
        self._installed = True
        logger.info(f"信号处理器安装完成，处理信号: {signals}")
    
    def uninstall(self) -> None:
        """卸载信号处理器，恢复原始处理器"""
        if not self._installed:
            return
        
        for sig, original_handler in self._original_handlers.items():
            try:
                signal.signal(sig, original_handler)
                logger.debug(f"已恢复信号处理器: {sig}")
            except (OSError, ValueError) as e:
                logger.warning(f"无法恢复信号处理器 {sig}: {e}")
        
        self._original_handlers.clear()
        self._installed = False
        logger.info("信号处理器已卸载")
    
    def __enter__(self):
        """上下文管理器入口"""
        self.install()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器退出"""
        self.uninstall()
    
    @property
    def is_installed(self) -> bool:
        """检查信号处理器是否已安装"""
        return self._installed


def create_queue_signal_handler(queue) -> SignalHandler:
    """为RedisMessageQueue创建信号处理器的便捷函数
    
    Args:
        queue: RedisMessageQueue实例
        
    Returns:
        SignalHandler: 配置好的信号处理器
        
    Example:
        ```python
        from mx_rmq import RedisMessageQueue
        from mx_rmq.signal_handler import create_queue_signal_handler
        
        queue = RedisMessageQueue()
        signal_handler = create_queue_signal_handler(queue)
        
        # 使用上下文管理器
        with signal_handler:
            await queue.start_background()
            # 程序运行...
        
        # 或手动管理
        signal_handler.install()
        try:
            await queue.start_background()
            # 程序运行...
        finally:
            signal_handler.uninstall()
        ```
    """
    return SignalHandler(queue.stop)