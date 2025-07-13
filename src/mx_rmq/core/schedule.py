"""
调度服务模块
负责延时消息处理、过期消息监控、processing队列监控和系统监控
"""

import asyncio
import json
import time
from typing import Any

from redis.commands.core import AsyncScript

from ..constants import GlobalKeys, TopicKeys
from ..message import Message
from .context import QueueContext
from .lifecycle import MessageLifecycleService


class ScheduleService:
    """定时，包括 监控和延长任务服务类"""

    def __init__(self, context: QueueContext) -> None:
        self.context = context
        self.handler_service = MessageLifecycleService(context)

    async def process_delay_messages(self) -> None:
        """延时消息处理协程 直接 lua 投递"""
        while self.context.is_running():
            try:
                current_time = int(time.time() * 1000)

                lua_script: AsyncScript = self.context.lua_scripts["process_delay"]
                results = await lua_script(
                    keys=[
                        self.context.get_global_key(GlobalKeys.DELAY_TASKS),
                        self.context.get_global_key(GlobalKeys.PAYLOAD_MAP),
                    ],
                    args=[current_time, self.context.config.batch_size],
                )

                if results:
                    self.context.logger.info(
                        "处理延时消息", count=len(results), current_time=current_time
                    )
                    for task_id, queue_name in results:
                        self.context.log_message_event(
                            "延时消息已就绪", task_id, queue_name
                        )

            except Exception as e:
                self.context.log_error("延时消息处理错误", e)

            await asyncio.sleep(3)

    async def monitor_expired_messages(self) -> None:
        """监控过期消息"""
        while self.context.is_running():
            try:
                current_time = int(time.time() * 1000)

                lua_script: AsyncScript = self.context.lua_scripts["handle_timeout"]
                expired_results = await lua_script(
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

                        self.context.log_message_event(
                            "过期消息处理", msg_id, queue_name, expire_reason="timeout"
                        )
                    except Exception as e:
                        self.context.log_error("处理过期消息失败", e, message_id=msg_id)

            except Exception as e:
                self.context.log_error("过期消息监控错误", e)

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
                self.context.log_error("Processing队列监控错误", e)
                await asyncio.sleep(30)

    async def _monitor_single_topic(self, topic: str) -> None:
        """监控单个主题的processing队列"""
        processing_key = self.context.get_topic_key(topic, TopicKeys.PROCESSING)

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
        self.context.logger.warning(
            "发现卡死消息",
            topic=topic,
            count=len(stuck_messages),
            stuck_messages=stuck_messages,
        )

        for msg_id in stuck_messages:
            try:
                await self.handler_service.handle_stuck_message(
                    msg_id, topic, processing_key
                )
                if msg_id in tracker:
                    del tracker[msg_id]
            except Exception as e:
                self.context.log_error(
                    "处理卡死消息失败", e, message_id=msg_id, topic=topic
                )

    async def system_monitor(self) -> None:
        """系统监控协程"""
        while self.context.is_running():
            try:
                metrics = await self._collect_metrics()

                for metric_name, value in metrics.items():
                    self.context.log_metric(metric_name, value)

                await self._check_alerts(metrics)

            except Exception as e:
                self.context.log_error("系统监控错误", e)

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
                    self.context.get_topic_key(topic, TopicKeys.PENDING)
                )
                topic_processing[topic] = pipe.llen(
                    self.context.get_topic_key(topic, TopicKeys.PROCESSING)
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
            self.context.log_error("收集指标失败", e)

        return metrics

    async def _check_alerts(self, metrics: dict[str, Any]) -> None:
        """检查告警条件"""
        try:
            for topic in self.context.handlers.keys():
                processing_count = metrics.get(f"{topic}.processing", 0)
                if processing_count > self.context.config.max_workers * 2:
                    self.context.logger.warning(
                        "Processing队列过长",
                        topic=topic,
                        count=processing_count,
                        threshold=self.context.config.max_workers * 2,
                    )
        except Exception as e:
            self.context.log_error("告警检查失败", e)
