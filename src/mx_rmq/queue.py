"""
Redis消息队列核心实现 - 重构为组合模式
"""

import asyncio
import signal
import time
import uuid
from collections.abc import Callable
from typing import Any
from dataclasses import dataclass, field

import redis.asyncio as aioredis
from redis.commands.core import AsyncScript
from loguru import logger

from .config import MQConfig
from .constants import GlobalKeys, TopicKeys
from .core import (
    ConsumerService,
    DispatchService,
    MessageLifecycleService,
    QueueContext,
    ScheduleService,
)
from .storage import RedisConnectionManager
from .message import Message, MessagePriority


@dataclass
class QueueMetrics:
    """队列指标信息"""

    local_queue_size: int
    local_queue_maxsize: int
    active_tasks_count: int = 0
    registered_topics: list[str] = field(default_factory=list)
    shutting_down: bool = False


class RedisMessageQueue:
    """Redis消息队列核心类 - 完全组合模式"""

    def __init__(self, config: MQConfig | None = None) -> None:
        """
        初始化消息队列

        Args:
            config: 消息队列配置，如为None则使用默认配置
        """
        self.config = config or MQConfig()

        # Redis连接管理器（私有）
        self._connection_manager = RedisConnectionManager(self.config)

        # 核心上下文（延迟初始化，私有）
        self._context: QueueContext | None = None

        # 本地任务队列（私有）
        self._task_queue: asyncio.Queue = asyncio.Queue(
            maxsize=self.config.task_queue_size
        )

        # 服务组件（延迟初始化，私有）
        self._consumer_service: ConsumerService | None = None
        self._message_handler_service: MessageLifecycleService | None = None
        self._monitor_service: ScheduleService | None = None
        self._dispatch_service: DispatchService | None = None

        # 状态管理
        self.initialized = False
        self._background_task: asyncio.Task | None = None
        self._start_time: float | None = None

    async def initialize(self) -> None:
        """初始化连接和服务组件"""
        # 卫语句：已初始化则直接返回
        if self.initialized:
            return

        try:
            # 步骤1：建立Redis连接
            redis = await self._connection_manager.initialize_connection()

            # 步骤2：加载Lua脚本
            from .storage import LuaScriptManager

            script_manager = LuaScriptManager(redis)
            lua_scripts = await script_manager.load_scripts()

            # 步骤3：创建核心上下文和服务组件
            await self._initialize_services(lua_scripts)

            self.initialized = True
            logger.info("消息队列初始化完成")

        except Exception as e:
            logger.exception("消息队列初始化失败")
            raise

    async def _initialize_services(self, lua_scripts: dict[str, AsyncScript]) -> None:
        """初始化服务组件"""
        # 确保Redis连接已建立
        assert self._connection_manager.redis is not None, "Redis连接未初始化"

        # 创建核心上下文
        self._context = QueueContext(
            config=self.config,
            redis=self._connection_manager.redis,
            lua_scripts=lua_scripts,
        )

        # 初始化服务组件
        self._consumer_service = ConsumerService(self._context, self._task_queue)
        self._message_handler_service = MessageLifecycleService(self._context)
        self._monitor_service = ScheduleService(self._context)
        self._dispatch_service = DispatchService(
            self._context, self._task_queue, self._connection_manager
        )

    def _setup_signal_handlers(self) -> None:
        """设置信号处理器"""

        def signal_handler(signum: int, frame: Any) -> None:
            logger.info(f"收到停机信号, signal={signum}")
            asyncio.create_task(self._graceful_shutdown())

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    async def cleanup(self) -> None:
        """清理资源"""
        try:
            await self._connection_manager.cleanup()
        except Exception as e:
            logger.exception("清理资源时出错")

    # ==================== 生产者接口 ====================

    async def produce(
        self,
        topic: str,
        payload: dict[str, Any],
        delay: int = 0,
        priority: MessagePriority = MessagePriority.NORMAL,
        ttl: int | None = None,
        message_id: str | None = None,
    ) -> str:
        """
        生产消息

        Args:
            topic: 主题名称
            payload: 消息负载，其他语言保持相同的json即可
            delay: 延迟执行时间（秒），0表示立即执行
            priority: 消息优先级
            ttl: 消息生存时间（秒），None使用配置默认值
            message_id: 消息ID，None则自动生成

        Returns:
            消息ID
        """
        if not self.initialized:
            await self.initialize()

        assert self._context is not None

        # 创建消息对象
        message = Message(
            id=message_id or str(uuid.uuid4()),
            topic=topic,
            payload=payload,
            priority=priority,
        )

        # 设置过期时间
        ttl = ttl or self.config.message_ttl
        message.meta.delay=delay
        expire_time = int(time.time() * 1000) + ttl * 1000
        message.meta.expire_at = expire_time
        message.meta.max_retries = self.config.max_retries
        message.meta.retry_delays = self.config.retry_delays.copy()
   

        message_json = message.model_dump_json(by_alias=True, exclude_none=True)

        try:
            # 根据延迟时间选择生产策略
            if delay > 0:
                await self._produce_delayed_message_with_logging(
                    message, message_json, topic, delay, priority
                )
            else:
                await self._produce_immediate_message_with_logging(
                    message, message_json, topic, expire_time, priority
                )

            return message.id

        except Exception as e:
            logger.exception(f"消息生产失败, message_id={message.id}, topic={topic}")
            raise

    async def _produce_delayed_message_with_logging(
        self,
        message: Message,
        message_json: str,
        topic: str,
        delay: int,
        priority: MessagePriority,
    ) -> None:
        """生产延时消息并记录日志"""
        await self._produce_delay_message(message.id, message_json, topic, delay)
        logger.info(
            f"消息生产成功[延时] - message_id={message.id}, topic={topic}, delay={delay}, priority={priority.value}"
        )

    async def _produce_immediate_message_with_logging(
        self,
        message: Message,
        message_json: str,
        topic: str,
        expire_time: int,
        priority: MessagePriority,
    ) -> None:
        """生产立即消息并记录日志"""
        await self._produce_normal_message(
            message.id, message_json, topic, expire_time, priority
        )
        logger.info(
            f"消息生产成功[立即] - message_id={message.id}, topic={topic}, priority={priority.value}"
        )

    async def _produce_normal_message(
        self,
        message_id: str,
        payload_json: str,
        topic: str,
        expire_time: int,
        priority: MessagePriority,
    ) -> None:
        """生产普通消息"""
        assert self._context is not None
        is_urgent = "1" if priority == MessagePriority.HIGH else "0"

        # 在存储时就使用完整的带前缀的队列名
        full_topic_name = self._context.get_global_key(topic)

        await self._context.lua_scripts["produce_normal"](
            keys=[
                self._context.get_global_key(GlobalKeys.PAYLOAD_MAP),
                self._context.get_global_topic_key(
                    topic, TopicKeys.PENDING
                ),  # 用于入队
                self._context.get_global_key(GlobalKeys.EXPIRE_MONITOR),
            ],
            args=[message_id, payload_json, full_topic_name, expire_time, is_urgent],
        )  # type: ignore

    async def _produce_delay_message(
        self, message_id: str, payload_json: str, topic: str, delay_seconds: int
    ) -> None:
        """生产延时消息"""
        assert self._context is not None

        # 在存储时就使用完整的带前缀的队列名
        full_topic_name = self._context.get_global_key(topic)

        # 使用增强版脚本，包含智能 pubsub 通知
        await self._context.lua_scripts["produce_delay"](
            keys=[
                self._context.get_global_key(GlobalKeys.PAYLOAD_MAP),
                self._context.get_global_key(GlobalKeys.DELAY_TASKS),
                self._context.get_global_key(
                    GlobalKeys.DELAY_PUBSUB_CHANNEL
                ),  # pubsub 通道
            ],
            args=[message_id, payload_json, full_topic_name, delay_seconds],
        )  # type: ignore

    # ==================== 消费者接口 ====================

    async def _prepare_for_consuming(self) -> None:
        """准备消费环境：初始化检查和处理器注册"""
        if not self.initialized:
            await self.initialize()

        assert self._context is not None

        # 注册延迟的处理器
        if hasattr(self, "_pending_handlers"):
            for topic, handler in self._pending_handlers.items():
                self._context.register_handler(topic, handler)
            delattr(self, "_pending_handlers")

        if not self._context.handlers:
            logger.warning("未注册任何消息处理器，队列将启动但不会处理业务消息")

    def _get_task_definitions(self) -> list[dict[str, Any]]:
        """获取任务定义列表

        Returns:
            list[dict]: 任务定义列表，每个定义包含name、coro、task_name等信息
        """
        assert self._context is not None

        task_definitions = []

        # 1. 消息分发协程（每个topic一个）
        for topic in self._context.handlers.keys():
            task_definitions.append(
                {
                    "name": f"dispatch_{topic}",
                    "coro": self._dispatch_service.dispatch_messages(topic),  # type: ignore
                    "description": f"消息分发协程-{topic}",
                }
            )

        # 2. 延时消息处理协程
        task_definitions.append(
            {
                "name": "delay_processor",
                "coro": self._monitor_service.process_delay_messages(),  # type: ignore
                "description": "延时消息处理协程",
            }
        )

        # 3. 过期消息监控协程
        task_definitions.append(
            {
                "name": "expired_monitor",
                "coro": self._monitor_service.monitor_expired_messages(),  # type: ignore
                "description": "过期消息监控协程",
            }
        )

        # 4. Processing队列监控协程
        task_definitions.append(
            {
                "name": "processing_monitor",
                "coro": self._monitor_service.monitor_processing_queues(),  # type: ignore
                "description": "Processing队列监控协程",
            }
        )

        # 5. 消费者协程池
        for i in range(self.config.max_workers):
            task_definitions.append(
                {
                    "name": f"consumer_{i}",
                    "coro": self._consumer_service.consume_messages(),  # type: ignore
                    "description": f"消费者协程-{i}",
                }
            )

        # 6. 系统监控协程
        task_definitions.append(
            {
                "name": "system_monitor",
                "coro": self._monitor_service.system_monitor(),  # type: ignore
                "description": "系统监控协程",
            }
        )

        return task_definitions

    def _create_task_from_definition(self, task_def: dict[str, Any]) -> asyncio.Task:
        """根据任务定义创建asyncio.Task

        Args:
            task_def: 任务定义字典

        Returns:
            asyncio.Task: 创建的任务对象
        """
        task = asyncio.create_task(task_def["coro"], name=task_def["name"])

        # 将任务添加到活跃任务集合
        if self._context:
            self._context.active_tasks.add(task)

        return task

    async def _create_and_run_tasks(self, is_background: bool = False) -> None:
        """创建并运行所有任务

        Args:
            is_background: 是否为后台模式，影响错误处理和清理逻辑
        """
        assert self._context is not None

        # 记录启动日志
        mode_text = "后台" if is_background else "前台"
        logger.info(
            f"{mode_text}启动消息消费, topics={list(self._context.handlers.keys())}, "
            f"max_workers={self.config.max_workers}"
        )

        # 获取任务定义并创建任务
        task_definitions = self._get_task_definitions()
        tasks: list[asyncio.Task] = []

        for task_def in task_definitions:
            task = self._create_task_from_definition(task_def)
            tasks.append(task)

        try:
            # 等待所有任务完成
            await asyncio.gather(*tasks, return_exceptions=True)

        except Exception as e:
            error_msg = (
                "后台消息消费过程中出错" if is_background else "消息消费过程中出错"
            )
            logger.exception(error_msg)
            raise
        finally:
            # 清理任务
            await self._cleanup_tasks()

            # 非后台模式需要额外清理资源
            if not is_background:
                await self.cleanup()

    def register_handler(self, topic: str, handler: Callable) -> None:
        """
        注册消息处理器

        Args:
            topic: 主题名称
            handler: 消息处理函数，接收payload参数
        """
        if not callable(handler):
            raise ValueError("处理器必须是可调用对象")

        """注册处理器装饰器"""

        # 如果已经初始化，直接注册到context
        if self._context:
            self._context.register_handler(topic, handler)
        else:
            # 延迟注册，等待初始化
            if not hasattr(self, "_pending_handlers"):
                self._pending_handlers: dict[str, Callable] = {}
            self._pending_handlers[topic] = handler

        logger.info(f"消息处理器注册成功, topic={topic}, handler={handler.__name__}")

    async def start(self) -> None:
        """启动消费"""
        # 准备消费环境
        await self._prepare_for_consuming()

        # 创建并运行任务
        await self._create_and_run_tasks(is_background=False)

    async def start_background(self, manage_signals: bool = True) -> asyncio.Task:
        """非阻塞启动消费，返回后台任务

        Args:
            manage_signals: 是否由队列管理信号（SIGINT, SIGTERM）。在嵌入式应用（如FastAPI）中应设为False。

        Returns:
            asyncio.Task: 后台运行的任务对象

        Raises:
            RuntimeError: 如果已经在运行中
        """
        if self.is_running():
            raise RuntimeError("消息队列已经在运行中")

        # 准备消费环境
        await self._prepare_for_consuming()

        # 创建后台任务
        self._background_task = asyncio.create_task(
            self._run_background_services(manage_signals=manage_signals),
            name="mx_rmq_background",
        )
        self._start_time = time.time()

        return self._background_task

    async def _run_background_services(self, manage_signals: bool = True) -> None:
        """运行后台服务（内部方法）"""
        if not self._context:
            raise RuntimeError("队列未初始化")

        self._context.running = True
        if manage_signals:
            self._setup_signal_handlers()

        # 创建并运行任务
        await self._create_and_run_tasks(is_background=True)

    async def stop(self) -> None:
        """停止消息队列

        优雅地停止所有后台服务并清理资源
        """
        if not self.is_running():
            logger.warning("消息队列未在运行中")
            return

        logger.info("开始停止消息队列...")

        try:
            # 执行优雅停机
            await self._graceful_shutdown()

            # 等待后台任务完成
            if self._background_task and not self._background_task.done():
                self._background_task.cancel()
                try:
                    await self._background_task
                except asyncio.CancelledError:
                    pass

        except Exception as e:
            logger.exception("停止消息队列时出错")
        finally:
            self._background_task = None
            self._start_time = None
            await self.cleanup()

        logger.info("消息队列已停止")
    
    def is_running(self) -> bool:
        """检查消息队列是否正在运行

        Returns:
            bool: True表示正在运行，False表示未运行
        """
        return (
            self._background_task is not None
            and not self._background_task.done()
            and self._context is not None
            and self._context.running
        )

    @property
    def status(self) -> dict[str, Any]:
        """获取消息队列状态信息

        Returns:
            dict: 包含运行状态、启动时间、活跃任务数等信息
        """
        status = {
            "running": self.is_running(),
            "initialized": self.initialized,
            "start_time": self._start_time,
            "uptime_seconds": time.time() - self._start_time
            if self._start_time
            else None,
        }

        if self._context:
            status.update(
                {
                    "registered_topics": list(self._context.handlers.keys()),
                    "active_tasks_count": len(self._context.active_tasks),
                    "shutting_down": self._context.shutting_down,
                    "local_queue_size": self._task_queue.qsize(),
                }
            )

        return status

    async def health_check(self) -> dict[str, Any]:
        """健康检查

        Returns:
            dict: 健康状态信息
        """
        health = {"healthy": True, "timestamp": time.time(), "checks": {}}

        try:
            # 检查Redis连接
            if self._context and self._context.redis:
                await self._context.redis.ping()
                health["checks"]["redis"] = "ok"
            else:
                health["checks"]["redis"] = "not_initialized"
                health["healthy"] = False

            # 检查运行状态
            if self.is_running():
                health["checks"]["running"] = "ok"
            else:
                health["checks"]["running"] = "stopped"

            # 检查后台任务状态
            if self._background_task:
                if self._background_task.done():
                    if self._background_task.exception():
                        health["checks"]["background_task"] = (
                            f"failed: {self._background_task.exception()}"
                        )
                        health["healthy"] = False
                    else:
                        health["checks"]["background_task"] = "completed"
                else:
                    health["checks"]["background_task"] = "running"
            else:
                health["checks"]["background_task"] = "not_started"

        except Exception as e:
            health["healthy"] = False
            health["error"] = str(e)

        return health

    # ==================== 受控访问接口 ====================

    @property
    def context(self) -> QueueContext | None:
        """获取队列上下文（只读访问）

        Returns:
            QueueContext | None: 队列上下文，未初始化时返回None
        """
        return self._context

    @property
    def connection_manager(self) -> RedisConnectionManager:
        """获取Redis连接管理器（只读访问）

        Returns:
            RedisConnectionManager: Redis连接管理器
        """
        return self._connection_manager

    @property
    def metrics(self) -> QueueMetrics:
        """获取队列指标信息

        Returns:
            QueueMetrics: 包含本地队列大小等指标信息
        """
        metrics = QueueMetrics(
            local_queue_size=self._task_queue.qsize(),
            local_queue_maxsize=self._task_queue.maxsize,
        )

        if self._context:
            metrics.active_tasks_count = len(self._context.active_tasks)
            metrics.registered_topics = list(self._context.handlers.keys())
            metrics.shutting_down = self._context.shutting_down

        return metrics

    def get_service_status(self) -> dict[str, bool]:
        """获取服务组件状态

        Returns:
            dict: 各服务组件的初始化状态
        """
        return {
            "consumer_service": self._consumer_service is not None,
            "message_handler_service": self._message_handler_service is not None,
            "monitor_service": self._monitor_service is not None,
            "dispatch_service": self._dispatch_service is not None,
        }

    # ==================== 异步上下文管理器支持 ====================

    async def __aenter__(self) -> "RedisMessageQueue":
        """异步上下文管理器入口

        Returns:
            RedisMessageQueue: 自身实例
        """
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """异步上下文管理器退出

        Args:
            exc_type: 异常类型
            exc_val: 异常值
            exc_tb: 异常追踪
        """
        if self.is_running():
            await self.stop()
        else:
            await self.cleanup()

    # ==================== 同步运行方法 ====================

    def run(self, duration: float | None = None) -> None:
        """同步运行消息队列

        这是一个便利方法，适用于简单的使用场景。
        它会创建事件循环并运行消息队列，直到手动停止或达到指定时长。

        Args:
            duration: 运行时长（秒），None表示无限运行直到收到停止信号

        Note:
            此方法会阻塞当前线程。对于更复杂的场景，建议使用异步方法。
        """
        import asyncio

        async def _run_with_duration():
            """带时长限制的运行"""
            try:
                # 启动后台服务
                task = await self.start_background()

                if duration is not None:
                    # 运行指定时长
                    await asyncio.sleep(duration)
                    await self.stop()
                else:
                    # 无限运行，等待任务完成（通常是收到停止信号）
                    await task

            except KeyboardInterrupt:
                logger.info("收到键盘中断信号，开始停止...")
                await self.stop()
            except Exception as e:
                logger.exception("运行过程中出错")
                await self.stop()
                raise

        # 运行事件循环
        try:
            asyncio.run(_run_with_duration())
        except KeyboardInterrupt:
            logger.info("程序已停止")

    
    # ==================== 优雅停机相关方法 ====================

    async def _graceful_shutdown(self) -> None:
        """优雅停机"""
        if not self._context or self._context.shutting_down:
            return

        logger.info("开始优雅停机...")
        self._context.shutting_down = True

        try:
            # 0. 停止调度器服务
            logger.info("【stop】停止调度器服务...")
            if hasattr(self, "_monitor_service") and self._monitor_service:
                try:
                    await asyncio.wait_for(
                        self._monitor_service.stop_delay_processing(), timeout=10.0
                    )
                except asyncio.TimeoutError:
                    logger.error("【stop】停止调度器服务超时")
                except Exception as e:
                    logger.exception("【stop】停止调度器服务失败")

            # 1. 停止接收新消息
            logger.info("【stop】停止消息分发...")

            # 2. 等待本地队列消息处理完成
            logger.info("【stop】等待本地队列消息处理完成...")
            await asyncio.wait_for(self._wait_for_local_queue_empty(), timeout=30.0)

            # 3. 等待所有消费协程完成当前任务
            logger.info("【stop】等待活跃消费者完成...")
            await asyncio.wait_for(self._wait_for_consumers_finish(), timeout=30.0)

            # 4. 取消所有后台任务
            logger.info("【stop】取消后台任务...")
            await asyncio.wait_for(self._cleanup_tasks(), timeout=10.0)

            # 5. 设置关闭事件
            self._context.shutdown_event.set()
            logger.info("【stop】优雅停机完成")

        except asyncio.TimeoutError:
            logger.error("【stop】优雅停机超时")
        except Exception as e:
            logger.exception("【stop】优雅停机过程中出错")

    async def _wait_for_local_queue_empty(self) -> None:
        """等待本地队列清空"""
        timeout = 30  # 30秒超时
        start_time = time.time()

        while not self._task_queue.empty():
            if time.time() - start_time > timeout:
                logger.warning(
                    f"【stop】等待本地队列清空超时，剩余消息数量, remaining_count={self._task_queue.qsize()}"
                )
                break
            await asyncio.sleep(0.1)

        if self._task_queue.empty():
            logger.info("【stop】本地队列已清空")
        else:
            remaining = self._task_queue.qsize()
            logger.warning(f"【stop】本地队列仍有消息, remaining_count={remaining}")

    async def _wait_for_consumers_finish(self) -> None:
        """等待消费者完成"""
        if not self._context:
            return

        timeout = 30  # 30秒超时
        start_time = time.time()

        # 等待一段时间让当前处理的消息完成
        while time.time() - start_time < timeout:
            # 检查是否还有正在处理的消息
            processing_count = 0
            for topic in self._context.handlers.keys():
                count = await self._context.redis.llen(f"{topic}:processing")  # type: ignore
                processing_count += count

            if processing_count == 0:
                logger.info("【stop】所有消息处理完成")
                break

            await asyncio.sleep(1)
        else:
            logger.warning("【stop】等待消费者完成超时")

    async def _cleanup_tasks(self) -> None:
        """清理活跃任务"""
        if not self._context or not self._context.active_tasks:
            return

        logger.info(f"【stop】取消活跃任务, count={len(self._context.active_tasks)}")

        # 取消所有任务
        for task in self._context.active_tasks:
            if not task.done():
                task.cancel()

        # 等待所有任务结束
        if self._context.active_tasks:
            await asyncio.gather(*self._context.active_tasks, return_exceptions=True)

        self._context.active_tasks.clear()
        logger.info("【stop】活跃任务清理完成")
