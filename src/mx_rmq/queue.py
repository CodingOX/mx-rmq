"""
Redis消息队列核心实现 - 重构为组合模式
"""

import asyncio
import signal
import time
import uuid
from collections.abc import Callable
from typing import Any

import redis.asyncio as aioredis
from redis.commands.core import AsyncScript

from .config import MQConfig
from .constants import GlobalKeys, TopicKeys
from .core import (
    ConsumerService,
    DispatchService,
    MessageLifecycleService,
    QueueContext,
    ScheduleService,
)
from .logging import LoggerService
from .message import Message, MessagePriority


class RedisMessageQueue:
    """Redis消息队列核心类 - 完全组合模式"""

    def __init__(self, config: MQConfig | None = None) -> None:
        """
        初始化消息队列

        Args:
            config: 消息队列配置，如为None则使用默认配置
        """
        self.config = config or MQConfig()

        # 所有队列前缀

        # Redis连接
        self.redis_pool: aioredis.ConnectionPool | None = None
        self.redis: aioredis.Redis | None = None

        # 日志服务
        self.logger_service = LoggerService("RedisMessageQueue")

        # 核心上下文（延迟初始化）
        self.context: QueueContext | None = None

        # 本地任务队列
        self.task_queue: asyncio.Queue = asyncio.Queue(
            maxsize=self.config.task_queue_size
        )

        # 服务组件（延迟初始化）
        self.consumer_service: ConsumerService | None = None
        self.message_handler_service: MessageLifecycleService | None = None
        self.monitor_service: ScheduleService | None = None
        self.dispatch_service: DispatchService | None = None

        # 状态管理
        self.initialized = False

    # 便捷属性，保持向后兼容
    @property
    def logger(self):
        """获取logger，保持向后兼容"""
        return self.logger_service.logger

    def log_error(self, message: str, error: Exception, **kwargs) -> None:
        """记录错误日志"""
        self.logger_service.log_error(message, error, **kwargs)

    def log_message_event(
        self, event: str, message_id: str, topic: str, **kwargs
    ) -> None:
        """记录消息事件"""
        self.logger_service.log_message_event(event, message_id, topic, **kwargs)

    async def initialize(self) -> None:
        """初始化连接和服务组件"""
        # 卫语句：已初始化则直接返回
        if self.initialized:
            return

        try:
            # 步骤1：建立Redis连接
            await self._initialize_redis_connection()

            # 步骤2：加载Lua脚本
            from .storage import LuaScriptManager

            # 确保redis已初始化
            assert self.redis is not None, "Redis连接未初始化"
            script_manager = LuaScriptManager(self.redis, self.logger_service)
            lua_scripts = await script_manager.load_scripts()

            # 步骤3：创建核心上下文和服务组件
            await self._initialize_services(lua_scripts)

            self.initialized = True
            self.logger_service.logger.info("消息队列初始化完成")

        except Exception as e:
            self.log_error("消息队列初始化失败", e)
            raise

    async def _initialize_redis_connection(self) -> None:
        """初始化Redis连接"""
        # 创建Redis连接池
        self.redis_pool = aioredis.ConnectionPool.from_url(
            self.config.redis_url,
            password=self.config.redis_password,
            max_connections=self.config.connection_pool_size,
            db=self.config.redis_db,
            decode_responses=True,
            socket_keepalive=True,
            socket_keepalive_options={},
            health_check_interval=30,
        )

        self.redis = aioredis.Redis(connection_pool=self.redis_pool)

        # 测试连接
        await self.redis.ping()
        self.logger_service.logger.info(
            "Redis连接建立成功", redis_url=self.config.redis_url
        )

    async def _initialize_services(self, lua_scripts: dict[str, AsyncScript]) -> None:
        """初始化服务组件"""
        # 确保Redis连接已建立
        assert self.redis is not None, "Redis连接未初始化"

        # 创建核心上下文
        self.context = QueueContext(
            config=self.config,
            redis=self.redis,
            logger_service=self.logger_service,
            lua_scripts=lua_scripts,
        )

        # 初始化服务组件
        self.consumer_service = ConsumerService(self.context, self.task_queue)
        self.message_handler_service = MessageLifecycleService(self.context)
        self.monitor_service = ScheduleService(self.context)
        self.dispatch_service = DispatchService(self.context, self.task_queue)

    def _setup_signal_handlers(self) -> None:
        """设置信号处理器"""

        def signal_handler(signum: int, frame: Any) -> None:
            self.logger_service.logger.info("收到停机信号", signal=signum)
            asyncio.create_task(self._graceful_shutdown())

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    async def cleanup(self) -> None:
        """清理资源"""
        try:
            if self.redis_pool:
                await self.redis_pool.disconnect()
                self.logger_service.logger.info("Redis连接池已关闭")
        except Exception as e:
            self.log_error("清理资源时出错", e)

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

        assert self.context is not None

        # 创建消息对象
        message = Message(
            id=message_id or str(uuid.uuid4()),
            topic=topic,
            payload=payload,
            priority=priority,
        )

        # 设置过期时间
        ttl = ttl or self.config.message_ttl
        expire_time = int(time.time() * 1000) + ttl * 1000
        message.meta.expire_at = expire_time
        message.meta.max_retries = self.config.max_retries
        message.meta.retry_delays = self.config.retry_delays.copy()

        message_json = message.model_dump_json()

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
            self.log_error("消息生产失败", e, message_id=message.id, topic=topic)
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
        execute_time = int(time.time() * 1000) + delay * 1000
        await self._produce_delay_message(message.id, message_json, topic, execute_time)
        self.log_message_event(
            "消息生产成功[延时]",
            message.id,
            topic,
            delay=delay,
            priority=priority.value,
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
        self.log_message_event(
            "消息生产成功[立即]", message.id, topic, priority=priority.value
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
        assert self.context is not None
        is_urgent = "1" if priority == MessagePriority.HIGH else "0"

        await self.context.lua_scripts["produce_normal"](
            keys=[
                self.context.get_global_key(GlobalKeys.PAYLOAD_MAP),
                self.context.get_topic_key(topic, TopicKeys.PENDING),
                self.context.get_global_key(GlobalKeys.EXPIRE_MONITOR),
            ],
            args=[message_id, payload_json, topic, expire_time, is_urgent],
        )

    async def _produce_delay_message(
        self, message_id: str, payload_json: str, topic: str, execute_time: int
    ) -> None:
        """生产延时消息"""
        assert self.context is not None
        await self.context.lua_scripts["produce_delay"](
            keys=[
                self.context.get_global_key(GlobalKeys.PAYLOAD_MAP),
                self.context.get_global_key(GlobalKeys.DELAY_TASKS),
            ],
            args=[message_id, payload_json, topic, execute_time],
        )

    # ==================== 消费者接口 ====================

    def register(
        self, topic: str, handler: Callable, timeout: float | None = None
    ) -> None:
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
        if self.context:
            self.context.register_handler(topic, handler)
        else:
            # 延迟注册，等待初始化
            if not hasattr(self, "_pending_handlers"):
                self._pending_handlers: dict[str, Callable] = {}
            self._pending_handlers[topic] = handler

        self.logger_service.logger.info(
            "消息处理器注册成功", topic=topic, handler=handler.__name__
        )

    async def start_dispatch_consuming(self) -> None:
        """启动消费"""
        if not self.initialized:
            await self.initialize()

        assert self.context is not None

        # 注册延迟的处理器
        if hasattr(self, "_pending_handlers"):
            for topic, handler in self._pending_handlers.items():
                self.context.register_handler(topic, handler)
            delattr(self, "_pending_handlers")

        if not self.context.handlers:
            raise ValueError("未注册任何消息处理器")

        self.context.running = True
        self._setup_signal_handlers()

        self.logger_service.logger.info(
            "启动消息消费",
            topics=list(self.context.handlers.keys()),
            max_workers=self.config.max_workers,
        )

        tasks: list[asyncio.Task] = []

        try:
            # 1. 消息分发协程（每个topic一个）
            for topic in self.context.handlers.keys():
                task = asyncio.create_task(
                    self.dispatch_service.dispatch_messages(topic),  # type: ignore
                    name=f"dispatch_{topic}",
                )
                tasks.append(task)
                self.context.active_tasks.add(task)

            # 2. 延时消息处理协程
            task = asyncio.create_task(
                self.monitor_service.process_delay_messages(),  # type: ignore
                name="delay_processor",
            )
            tasks.append(task)
            self.context.active_tasks.add(task)

            # 3. 过期消息监控协程
            task = asyncio.create_task(
                self.monitor_service.monitor_expired_messages(),  # type: ignore
                name="expired_monitor",
            )
            tasks.append(task)
            self.context.active_tasks.add(task)

            # 4. Processing队列监控协程
            task = asyncio.create_task(
                self.monitor_service.monitor_processing_queues(),  # type: ignore
                name="processing_monitor",
            )
            tasks.append(task)
            self.context.active_tasks.add(task)

            # 5. 消费者协程池
            for i in range(self.config.max_workers):
                task = asyncio.create_task(
                    self.consumer_service.consume_messages(),  # type: ignore
                    name=f"consumer_{i}",
                )
                tasks.append(task)
                self.context.active_tasks.add(task)

            # 6. 系统监控协程
            task = asyncio.create_task(
                self.monitor_service.system_monitor(),  # type: ignore
                name="system_monitor",
            )
            tasks.append(task)
            self.context.active_tasks.add(task)

            # 等待所有任务完成
            await asyncio.gather(*tasks, return_exceptions=True)

        except Exception as e:
            self.log_error("消息消费过程中出错", e)
            raise
        finally:
            await self._cleanup_tasks()
            await self.cleanup()

    # ==================== 优雅停机相关方法 ====================

    async def _graceful_shutdown(self) -> None:
        """优雅停机"""
        if not self.context or self.context.shutting_down:
            return

        self.logger_service.logger.info("开始优雅停机...")
        self.context.shutting_down = True

        try:
            # 1. 停止接收新消息
            self.logger_service.logger.info("停止消息分发...")

            # 2. 等待本地队列消息处理完成
            self.logger_service.logger.info("等待本地队列消息处理完成...")
            await self._wait_for_local_queue_empty()

            # 3. 等待所有消费协程完成当前任务
            self.logger_service.logger.info("等待活跃消费者完成...")
            await self._wait_for_consumers_finish()

            # 4. 取消所有后台任务
            self.logger_service.logger.info("取消后台任务...")
            await self._cleanup_tasks()

            # 5. 设置关闭事件
            self.context.shutdown_event.set()
            self.logger_service.logger.info("优雅停机完成")

        except Exception as e:
            self.log_error("优雅停机过程中出错", e)

    async def _wait_for_local_queue_empty(self) -> None:
        """等待本地队列清空"""
        timeout = 30  # 30秒超时
        start_time = time.time()

        while not self.task_queue.empty():
            if time.time() - start_time > timeout:
                self.logger_service.logger.warning(
                    "等待本地队列清空超时，剩余消息数量",
                    remaining_count=self.task_queue.qsize(),
                )
                break
            await asyncio.sleep(0.1)

        if self.task_queue.empty():
            self.logger_service.logger.info("本地队列已清空")
        else:
            remaining = self.task_queue.qsize()
            self.logger_service.logger.warning(
                "本地队列仍有消息", remaining_count=remaining
            )

    async def _wait_for_consumers_finish(self) -> None:
        """等待消费者完成"""
        if not self.context:
            return

        timeout = 30  # 30秒超时
        start_time = time.time()

        # 等待一段时间让当前处理的消息完成
        while time.time() - start_time < timeout:
            # 检查是否还有正在处理的消息
            processing_count = 0
            for topic in self.context.handlers.keys():
                count = await self.context.redis.llen(f"{topic}:processing")  # type: ignore
                processing_count += count

            if processing_count == 0:
                self.logger_service.logger.info("所有消息处理完成")
                break

            await asyncio.sleep(1)
        else:
            self.logger_service.logger.warning("等待消费者完成超时")

    async def _cleanup_tasks(self) -> None:
        """清理活跃任务"""
        if not self.context or not self.context.active_tasks:
            return

        self.logger_service.logger.info(
            "取消活跃任务", count=len(self.context.active_tasks)
        )

        # 取消所有任务
        for task in self.context.active_tasks:
            if not task.done():
                task.cancel()

        # 等待所有任务结束
        if self.context.active_tasks:
            await asyncio.gather(*self.context.active_tasks, return_exceptions=True)

        self.context.active_tasks.clear()
        self.logger_service.logger.info("活跃任务清理完成")
