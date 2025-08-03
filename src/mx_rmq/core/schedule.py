"""
调度服务模块
负责延时消息处理、过期消息监控、processing队列监控和系统监控
"""

import asyncio
import json
import time
from typing import Any

from loguru import logger
from redis.commands.core import AsyncScript

from ..constants import GlobalKeys, TopicKeys
from ..message import Message
from .context import QueueContext
from .lifecycle import MessageLifecycleService


class ScheduleService:
    """统一的调度服务类（已优化延时调度部分）"""

    def __init__(self, context: QueueContext) -> None:
        self.context = context
        self.handler_service = MessageLifecycleService(context)

        # --- 重构部分：状态管理 ---
        self.is_running = False
        # 单一的调度循环任务，用于优雅地启动和停止
        self.scheduler_task: asyncio.Task | None = None

        # 使用Event进行通知，替代Lock
        # 一对多通知: 一个 set() 可以唤醒多个等待的协程
        # 状态持久: 事件一旦设置，后续的 wait() 会立即返回
        # 可重置: 通过 clear() 可以重新使用同一个事件对象
        self.notification_event = asyncio.Event()

    async def process_delay_messages(self) -> None:
        """延时消息处理协程 - 使用优化的调度逻辑"""
        if self.is_running:
            logger.debug("延时任务调度器已在运行")
            return

        self.is_running = True
        logger.debug("启动延时任务调度器")

        # 将主调度逻辑封装在一个任务中，方便管理
        self.scheduler_task = asyncio.create_task(self.delay_scheduler_loop())

        # 启动其他辅助任务
        await asyncio.gather(
            self.scheduler_task,
            self.pubsub_listener(),
            self.periodic_fallback(),
            return_exceptions=True,
        )

    async def stop_delay_processing(self) -> None:
        """优雅地停止延时消息处理"""
        # 运行状态检查，如果未运行则直接返回
        if not self.is_running:
            logger.debug("延时任务调度器未运行，无需停止")
            return

        self.is_running = False
        logger.info("开始停止延时任务调度器...")

        try:
            # 设置事件，确保如果调度器正在等待中，能被立即唤醒并检查到 is_running == False
            self.notification_event.set()

            # 取消主调度任务
            if self.scheduler_task and not self.scheduler_task.done():
                self.scheduler_task.cancel()

            # 等待任务完成取消，添加5秒超时保护
            if self.scheduler_task:
                try:
                    await asyncio.wait_for(self.scheduler_task, timeout=5.0)
                except asyncio.TimeoutError:
                    logger.error("停止延时任务调度器超时，强制结束")
                    # 如果超时，确保任务被取消
                    if not self.scheduler_task.done():
                        self.scheduler_task.cancel()
                except asyncio.CancelledError:
                    pass  # 预期内的异常
                except Exception as e:
                    logger.exception(f"停止延时任务调度器时发生异常: {e}")

            logger.debug("延时任务调度器已停止")
        except Exception as e:
            logger.exception(f"停止延时任务调度器过程中发生错误: {e}")
        finally:
            # 确保 scheduler_task 被重置为 None
            self.scheduler_task = None

    async def delay_scheduler_loop(self) -> None:
        """
        核心调度循环（状态机）。
        这是整个优化的核心，它取代了旧的 timer_lock 和 current_timer_task 管理。
        """
        logger.debug("延时调度主循环已启动")

        # 首次启动时，短暂延时后立即触发一次调度检查
        await asyncio.sleep(0.2)
        logger.debug("进程启动，初始化延时任务调度")

        while self.is_running:
            # 在循环开始时添加 is_running 状态检查
            if not self.is_running:
                break

            try:
                # 1. 从Redis获取下一个任务信息和等待时间
                start_time = time.time()
                lua_script: AsyncScript = self.context.lua_scripts[
                    "get_next_delay_task"
                ]
                delay_tasks_key = self.context.get_global_key(GlobalKeys.DELAY_TASKS)
                result = await lua_script(keys=[delay_tasks_key], args=[])
                status = result[0]
                end_time = time.time()
                # 🔍 详细日志：调试 Lua 脚本返回值 保留 3 位小数
                logger.debug(
                    f"get_next_delay_task 扫描延时队列【{delay_tasks_key}】 耗时: {end_time - start_time:.3f} 秒,返回: {result}"
                )

                wait_milliseconds: float | None = None

                # 2. 根据状态决定下一步操作
                if status == "NO_TASK":
                    logger.debug("当前无延时任务，等待新任务通知...")
                    wait_milliseconds = None  # 无限期等待
                elif status == "EXPIRED":
                    logger.info(f"发现过期任务 {result[2]}，立即处理")
                    await self.try_process_expired_tasks()
                    continue  # 处理完后，立即开始下一次循环检查
                elif status == "WAITING":
                    wait_milliseconds = int(result[1])

                    # 🛡️ 边界保护：如果等待时间很小，添加小延迟避免时间竞争
                    if wait_milliseconds < 10:  # 小于10毫秒
                        logger.debug(
                            f"任务 {result[3]} 等待时间很短 ({wait_milliseconds}毫秒)，添加缓冲延迟避免时间竞争"
                        )
                        await asyncio.sleep(0.01)  # 等待10毫秒让时间完全过期
                        await self.try_process_expired_tasks()
                        continue

                    logger.debug(
                        f"下一个任务 {result[3]}将在 {wait_milliseconds} 毫秒后到期，开始等待..."
                    )

                # 3. 等待：要么超时，要么被外部事件唤醒
                try:
                    # 清除旧信号，准备接收新信号
                    self.notification_event.clear()
                    # 🔧 关键修复：将毫秒转换为秒数
                    wait_seconds = (
                        wait_milliseconds / 1000.0
                        if wait_milliseconds is not None
                        else None
                    )

                    # 为长时间等待（>5秒）实现分段等待机制
                    if wait_seconds is not None and wait_seconds > 5.0:
                        # 分段等待，每5秒检查一次停止状态
                        remaining_time = wait_seconds
                        while remaining_time > 0 and self.is_running:
                            segment_wait = min(5.0, remaining_time)
                            try:
                                await asyncio.wait_for(
                                    self.notification_event.wait(), timeout=segment_wait
                                )
                                # 如果收到通知，跳出分段等待
                                break
                            except asyncio.TimeoutError:
                                # 分段超时，继续等待剩余时间
                                remaining_time -= segment_wait
                                if not self.is_running:
                                    break

                        # 如果是因为停止状态退出，抛出 CancelledError
                        if not self.is_running:
                            raise asyncio.CancelledError("调度器已停止")
                    else:
                        # 短时间等待，直接等待
                        # 在这里增加对 is_running 的检查，确保在停止时能快速退出
                        if self.is_running:
                            await asyncio.wait_for(
                                self.notification_event.wait(), timeout=wait_seconds
                            )
                        else:
                            # 如果已经停止运行，直接抛出 CancelledError
                            raise asyncio.CancelledError("调度器已停止")

                    # 如果代码执行到这里，说明是 notification_event 被触发了 【兜底 或者 pub/sub 通知】
                    logger.debug("收到外部通知，重新评估调度计划...")
                    # 直接进入下一次 while 循环，重新从 Redis 获取最新等待时间

                except asyncio.TimeoutError:
                    # 如果代码执行到这里，说明是 wait_for 超时了，定时器自然到期
                    logger.debug("定时器到期，开始处理过期任务...")
                    await self.try_process_expired_tasks()
                    # 处理完后，会自动进入下一次 while 循环

            except asyncio.CancelledError:
                logger.warning("调度主循环被取消，正在退出...")
                break  # 退出循环
            except Exception as e:
                # 在异常处理中添加 is_running 状态检查
                if self.is_running:
                    logger.exception("调度主循环发生未知错误，暂停后重试")
                    await asyncio.sleep(
                        1
                    )  # 发生未知错误时，短暂等待防止CPU占用过高（优化：减少等待时间）
                else:
                    # 如果已经停止，不记录错误日志，直接退出
                    break

        logger.warning("延时调度主循环已退出")

    async def pubsub_listener(self) -> None:
        """监听pubsub通道 - 逻辑已大大简化"""
        retry_delay = 1
        pubsub = None
        consecutive_failures = 0
        max_consecutive_failures = 5

        while self.is_running:
            try:
                # 创建新的pubsub连接
                if pubsub is None:
                    pubsub = self.context.redis.pubsub()
                    channel = self.context.get_global_key(
                        GlobalKeys.DELAY_PUBSUB_CHANNEL
                    )
                    await pubsub.subscribe(channel)
                    logger.info(f"开始监听延时任务通知, channel={channel}")
                    retry_delay = 1  # 重置重试延迟
                    consecutive_failures = 0  # 重置失败计数

                # 添加连接状态检查
                last_ping = asyncio.get_event_loop().time()
                ping_interval = 30  # 30秒ping一次检查连接状态

                async for message in pubsub.listen():
                    if not self.is_running:
                        break

                    # 定期ping检查连接状态
                    current_time = asyncio.get_event_loop().time()
                    if current_time - last_ping > ping_interval:
                        try:
                            await self.context.redis.ping()
                            last_ping = current_time
                        except Exception as ping_error:
                            logger.exception("Redis连接检查失败")
                            raise ping_error

                    if message["type"] == "message":
                        try:
                            notified_time = int(message["data"])
                            logger.debug(f"收到延时任务通知: {notified_time}")

                            # --- 核心改变：只设置事件，不处理任何复杂逻辑 ---
                            self.notification_event.set()

                        except Exception as e:
                            logger.exception("处理延时通知错误")

            except Exception as e:
                consecutive_failures += 1
                logger.exception(
                    f"Pubsub监听器错误, consecutive_failures={consecutive_failures}"
                )

                # 清理损坏的连接
                if pubsub:
                    try:
                        await pubsub.close()
                    except Exception:
                        pass
                    pubsub = None

                # 如果系统正在关闭，直接退出
                if not self.is_running:
                    break

                # 如果连续失败次数过多，增加等待时间
                if consecutive_failures >= max_consecutive_failures:
                    retry_delay = min(retry_delay * 2, 60)
                    logger.warning(
                        f"Pubsub连续失败过多，延长重连间隔, consecutive_failures={consecutive_failures}, retry_delay={retry_delay}"
                    )
                else:
                    # 快速重连
                    retry_delay = min(retry_delay * 1.5, 10)

                logger.warning(
                    f"Pubsub连接断开，等待重连, retry_delay={retry_delay}, consecutive_failures={consecutive_failures}"
                )

                # 将长时间等待分解为小段，每0.1秒检查一次停止状态
                remaining_delay = retry_delay
                while remaining_delay > 0 and self.is_running:
                    sleep_time = min(0.1, remaining_delay)
                    await asyncio.sleep(sleep_time)
                    remaining_delay -= sleep_time

        # 确保资源清理
        if pubsub:
            try:
                await pubsub.close()
                logger.info("Pubsub连接已关闭")
            except Exception as e:
                logger.exception("关闭Pubsub连接失败")

        logger.info("pubsub_listener close!")

    async def periodic_fallback(self) -> None:
        """定期兜底检查，防止pubsub消息丢失"""
        while self.is_running:
            await asyncio.sleep(self.context.config.delay_fallback_interval)
            try:
                logger.debug("执行兜底检查，触发一次调度评估")
                # 同样，只是简单地设置事件
                self.notification_event.set()
            except Exception as e:
                logger.exception("兜底检查执行失败")
        logger.info("periodic_fallback close!")

    async def try_process_expired_tasks(self) -> None:
        """尝试处理过期任务"""
        try:
            lua_script: AsyncScript = self.context.lua_scripts["process_delay"]
            delay_tasks_key = self.context.get_global_key(GlobalKeys.DELAY_TASKS)
            payload_map_key = self.context.get_global_key(GlobalKeys.PAYLOAD_MAP)
            batch_size = str(self.context.config.batch_size)  # Lua脚本要求字符串参数
            result = await lua_script(
                keys=[delay_tasks_key, payload_map_key], args=[batch_size]
            )
            if result:
                logger.info(f"处理延时任务成功, result={result}")
        except Exception as e:
            logger.exception("处理延时任务失败")

    async def monitor_expired_messages(self) -> None:
        """监控过期消息"""
        while self.context.is_running():
            try:
                current_time = int(time.time() * 1000)

                lua_script: AsyncScript = self.context.lua_scripts["handle_timeout"]
                expired_results = await lua_script(
                    # 这里 keys 都是 redis 中的键名称
                    keys=[
                        self.context.get_global_key(GlobalKeys.EXPIRE_MONITOR),
                        self.context.get_global_key(GlobalKeys.PAYLOAD_MAP),
                    ],
                    args=[current_time, self.context.config.batch_size],
                )

                for msg_id, payload_json, queue_name in expired_results:
                    try:
                        message = Message.model_validate_json(payload_json)

                        await self.handler_service.handle_expired_message(
                            message, queue_name
                        )

                        logger.info(
                            f"过期消息处理, message_id={msg_id}, queue_name={queue_name}, expire_reason=timeout"
                        )
                    except Exception as e:
                        logger.exception(f"处理过期消息失败, message_id={msg_id}")

            except Exception as e:
                logger.exception("过期消息监控错误")

            await asyncio.sleep(self.context.config.expired_check_interval)

    async def monitor_processing_queues(self) -> None:
        """监控processing队列"""
        while self.context.is_running():
            try:
                for topic in self.context.handlers.keys():
                    await self._monitor_single_topic(topic)
                    await asyncio.sleep(1)

                await asyncio.sleep(self.context.config.processing_monitor_interval)

            except Exception as e:
                logger.exception("Processing队列监控错误")
                await asyncio.sleep(30)

    async def _monitor_single_topic(self, topic: str) -> None:
        """监控单个主题的processing队列"""
        processing_key = self.context.get_global_topic_key(topic, TopicKeys.PROCESSING)

        # 获取processing队列中的所有消息
        processing_ids = await self.context.redis.lrange(processing_key, 0, -1)  # type: ignore

        # 初始化该topic的跟踪器
        if topic not in self.context.stuck_messages_tracker:
            self.context.stuck_messages_tracker[topic] = {}

        current_tracker = self.context.stuck_messages_tracker[topic]
        current_ids_set = set(processing_ids)

        # 更新跟踪状态
        self._update_message_tracking(current_tracker, processing_ids, current_ids_set)

        # 检查并处理卡死的消息
        stuck_messages = self._identify_stuck_messages(current_tracker)
        if stuck_messages:
            await self._handle_stuck_messages(
                stuck_messages, topic, processing_key, current_tracker
            )

    def _update_message_tracking(
        self, tracker: dict[str, int], processing_ids: list, current_ids_set: set
    ) -> None:
        """更新消息跟踪状态"""
        # 更新连续检测计数
        for msg_id in processing_ids:
            if msg_id in tracker:
                tracker[msg_id] += 1
            else:
                tracker[msg_id] = 1

        # 清理已经不在processing队列中的消息ID
        ids_to_remove = [
            msg_id for msg_id in tracker.keys() if msg_id not in current_ids_set
        ]
        for msg_id in ids_to_remove:
            del tracker[msg_id]

    def _identify_stuck_messages(self, tracker: dict[str, int]) -> list[str]:
        """识别卡死的消息"""
        return [msg_id for msg_id, count in tracker.items() if count >= 3]

    async def _handle_stuck_messages(
        self,
        stuck_messages: list[str],
        topic: str,
        processing_key: str,
        tracker: dict[str, int],
    ) -> None:
        """处理卡死的消息列表"""
        logger.warning(
            f"发现卡死消息, topic={topic}, count={len(stuck_messages)}, stuck_messages={stuck_messages}"
        )

        for msg_id in stuck_messages:
            try:
                await self.handler_service.handle_stuck_message(
                    msg_id, topic, processing_key
                )
                if msg_id in tracker:
                    del tracker[msg_id]
            except Exception as e:
                logger.exception(
                    f"处理卡死消息失败, message_id={msg_id}, topic={topic}"
                )

    async def system_monitor(self) -> None:
        """系统监控协程"""
        while self.context.is_running():
            try:
                metrics = await self._collect_metrics()

                for metric_name, value in metrics.items():
                    logger.debug(f"metric: {metric_name}={value}")

                await self._check_alerts(metrics)

            except Exception as e:
                logger.exception("系统监控错误")

            await asyncio.sleep(self.context.config.monitor_interval)

    async def _collect_metrics(self) -> dict[str, Any]:
        """收集系统指标"""
        metrics = {}

        try:
            pipe = self.context.redis.pipeline()  # type: ignore

            topic_pending = {}
            topic_processing = {}
            for topic in self.context.handlers.keys():
                topic_pending[topic] = pipe.llen(
                    self.context.get_global_topic_key(topic, TopicKeys.PENDING)
                )
                topic_processing[topic] = pipe.llen(
                    self.context.get_global_topic_key(topic, TopicKeys.PROCESSING)
                )

            pipe.zcard(self.context.get_global_key(GlobalKeys.DELAY_TASKS))
            pipe.zcard(self.context.get_global_key(GlobalKeys.EXPIRE_MONITOR))
            pipe.hlen(self.context.get_global_key(GlobalKeys.PAYLOAD_MAP))
            pipe.llen(self.context.get_global_key(GlobalKeys.DLQ_QUEUE))

            results = await pipe.execute()

            # Parse results
            result_idx = 0
            for topic in self.context.handlers.keys():
                metrics[f"{topic}.pending"] = results[result_idx]
                result_idx += 1
                metrics[f"{topic}.processing"] = results[result_idx]
                result_idx += 1

            metrics[f"{GlobalKeys.DELAY_TASKS.value}.count"] = results[result_idx]
            result_idx += 1
            metrics[f"{GlobalKeys.EXPIRE_MONITOR.value}.count"] = results[result_idx]
            result_idx += 1
            metrics[f"{GlobalKeys.PAYLOAD_MAP.value}.count"] = results[result_idx]
            result_idx += 1
            metrics[f"{GlobalKeys.DLQ_QUEUE.value}.count"] = results[result_idx]

        except Exception as e:
            logger.exception("收集指标失败")

        return metrics

    async def _check_alerts(self, metrics: dict[str, Any]) -> None:
        """检查告警条件"""
        try:
            for topic in self.context.handlers.keys():
                processing_count = metrics.get(f"{topic}.processing", 0)
                if processing_count > self.context.config.max_workers * 2:
                    logger.warning(
                        f"Processing队列过长, topic={topic}, count={processing_count}, threshold={self.context.config.max_workers * 2}"
                    )
        except Exception as e:
            logger.exception("告警检查失败")
