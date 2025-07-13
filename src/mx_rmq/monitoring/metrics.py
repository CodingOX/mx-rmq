"""
指标收集器模块
"""

import time
from collections import defaultdict, deque
from threading import Lock
from typing import Any

import redis.asyncio as aioredis
from pydantic import BaseModel, Field

from ..constants import GlobalKeys, TopicKeys
from ..logging import LoggerService


class QueueMetrics(BaseModel):
    """队列指标数据类"""

    pending_count: int = Field(default=0, ge=0, description="待处理消息数")
    processing_count: int = Field(default=0, ge=0, description="处理中消息数")
    completed_count: int = Field(default=0, ge=0, description="已完成消息数")
    failed_count: int = Field(default=0, ge=0, description="失败消息数")
    dead_letter_count: int = Field(default=0, ge=0, description="死信消息数")
    delay_count: int = Field(default=0, ge=0, description="延时消息数")


class ProcessingMetrics(BaseModel):
    """处理指标数据类"""

    total_processed: int = Field(default=0, ge=0, description="总处理消息数")
    success_count: int = Field(default=0, ge=0, description="成功处理数")
    error_count: int = Field(default=0, ge=0, description="错误处理数")
    retry_count: int = Field(default=0, ge=0, description="重试次数")
    avg_processing_time: float = Field(default=0.0, ge=0.0, description="平均处理时间")
    max_processing_time: float = Field(default=0.0, ge=0.0, description="最大处理时间")
    min_processing_time: float = Field(default=0.0, ge=0.0, description="最小处理时间")


class MetricsCollector:
    """指标收集器"""

    def __init__(
        self, redis: aioredis.Redis | None = None, queue_prefix: str = ""
    ) -> None:
        """
        初始化指标收集器

        Args:
            redis: Redis连接实例（可选，用于持久化指标）
            queue_prefix: 队列前缀，用于生成正确的键名
        """
        self.redis = redis
        self.queue_prefix = queue_prefix
        self._lock = Lock()
        self.logger_service = LoggerService("metric-collector")

        # 队列计数器
        self._queue_counters: defaultdict[str, dict[str, int]] = defaultdict(
            lambda: {
                "pending": 0,
                "processing": 0,
                "completed": 0,
                "failed": 0,
                "dead_letter": 0,
                "delay": 0,
            }
        )

        # 处理计数器
        self._processing_counters: defaultdict[str, dict[str, int]] = defaultdict(
            lambda: {"total_processed": 0, "success": 0, "error": 0, "retry": 0}
        )

        # 处理时间统计
        self._processing_times: defaultdict[str, deque] = defaultdict(
            lambda: deque(maxlen=1000)
        )

        # 消息处理开始时间记录
        self._start_times: dict[str, float] = {}

        self.metrics_history: list[dict[str, Any]] = []
        self.max_history_size = 1000  # 保留最近1000条记录

    def _get_global_key(self, key: GlobalKeys) -> str:
        """获取全局键名，自动添加队列前缀"""
        if self.queue_prefix:
            return f"{self.queue_prefix}:{key.value}"
        return key.value

    def _get_topic_key(self, topic: str, suffix: TopicKeys) -> str:
        """获取主题相关键名，自动添加队列前缀"""
        if self.queue_prefix:
            return f"{self.queue_prefix}:{topic}:{suffix.value}"
        return f"{topic}:{suffix.value}"

    def record_message_produced(self, topic: str, priority: str = "normal") -> None:
        """
        记录消息生产

        Args:
            topic: 主题名称
            priority: 消息优先级
        """
        with self._lock:
            self._queue_counters[topic]["pending"] += 1

    def record_message_consumed(self, topic: str) -> None:
        """
        记录消息消费

        Args:
            topic: 主题名称
        """
        with self._lock:
            if self._queue_counters[topic]["pending"] > 0:
                self._queue_counters[topic]["pending"] -= 1
                self._queue_counters[topic]["processing"] += 1

    def record_message_completed(self, topic: str, processing_time: float) -> None:
        """
        记录消息完成处理

        Args:
            topic: 主题名称
            processing_time: 处理时间（秒）
        """
        with self._lock:
            if self._queue_counters[topic]["processing"] > 0:
                self._queue_counters[topic]["processing"] -= 1
                self._queue_counters[topic]["completed"] += 1

            self._processing_counters[topic]["total_processed"] += 1
            self._processing_counters[topic]["success"] += 1
            self._processing_times[topic].append(processing_time)

    def record_message_failed(
        self, topic: str, error_message: str, processing_time: float | None = None
    ) -> None:
        """
        记录消息处理失败

        Args:
            topic: 主题名称
            error_message: 错误消息
            processing_time: 处理时间（秒）
        """
        with self._lock:
            if self._queue_counters[topic]["processing"] > 0:
                self._queue_counters[topic]["processing"] -= 1
                self._queue_counters[topic]["failed"] += 1

            self._processing_counters[topic]["total_processed"] += 1
            self._processing_counters[topic]["error"] += 1

            if processing_time is not None:
                self._processing_times[topic].append(processing_time)

    def record_message_retried(self, topic: str) -> None:
        """
        记录消息重试

        Args:
            topic: 主题名称
        """
        with self._lock:
            self._processing_counters[topic]["retry"] += 1

    def record_message_dead_letter(self, topic: str) -> None:
        """
        记录消息进入死信队列

        Args:
            topic: 主题名称
        """
        with self._lock:
            if self._queue_counters[topic]["processing"] > 0:
                self._queue_counters[topic]["processing"] -= 1
            self._queue_counters[topic]["dead_letter"] += 1

    def record_delay_message(self, topic: str) -> None:
        """
        记录延时消息

        Args:
            topic: 主题名称
        """
        with self._lock:
            self._queue_counters[topic]["delay"] += 1

    def start_processing(self, message_id: str) -> None:
        """
        开始处理消息

        Args:
            message_id: 消息ID
        """
        self._start_times[message_id] = time.time()

    def end_processing(self, message_id: str) -> float:
        """
        结束处理消息并返回处理时间

        Args:
            message_id: 消息ID

        Returns:
            处理时间（秒）
        """
        start_time = self._start_times.pop(message_id, time.time())
        return time.time() - start_time

    def get_queue_metrics(self, topic: str) -> QueueMetrics:
        """
        获取指定主题的队列指标

        Args:
            topic: 主题名称

        Returns:
            队列指标实例
        """
        with self._lock:
            counters = self._queue_counters[topic]
            return QueueMetrics(
                pending_count=counters["pending"],
                processing_count=counters["processing"],
                completed_count=counters["completed"],
                failed_count=counters["failed"],
                dead_letter_count=counters["dead_letter"],
                delay_count=counters["delay"],
            )

    def get_processing_metrics(self, topic: str) -> ProcessingMetrics:
        """
        获取指定主题的处理指标

        Args:
            topic: 主题名称

        Returns:
            处理指标实例
        """
        with self._lock:
            counters = self._processing_counters[topic]
            times = list(self._processing_times[topic])

            if times:
                avg_time = sum(times) / len(times)
                max_time = max(times)
                min_time = min(times)
            else:
                avg_time = max_time = min_time = 0.0

            return ProcessingMetrics(
                total_processed=counters["total_processed"],
                success_count=counters["success"],
                error_count=counters["error"],
                retry_count=counters["retry"],
                avg_processing_time=avg_time,
                max_processing_time=max_time,
                min_processing_time=min_time,
            )

    def get_all_queue_metrics(self) -> dict[str, QueueMetrics]:
        """
        获取所有主题的队列指标

        Returns:
            主题到队列指标的映射
        """
        with self._lock:
            return {
                topic: self.get_queue_metrics(topic)
                for topic in self._queue_counters.keys()
            }

    def get_all_processing_metrics(self) -> dict[str, ProcessingMetrics]:
        """
        获取所有主题的处理指标

        Returns:
            主题到处理指标的映射
        """
        with self._lock:
            return {
                topic: self.get_processing_metrics(topic)
                for topic in self._processing_counters.keys()
            }

    def reset_metrics(self) -> None:
        """重置所有指标"""
        with self._lock:
            self._queue_counters.clear()
            self._processing_counters.clear()
            self._processing_times.clear()
            self._start_times.clear()

    async def collect_queue_metrics(self, topics: list[str]) -> dict[str, Any]:
        """
        收集队列相关指标

        Args:
            topics: 主题列表

        Returns:
            队列指标字典
        """
        metrics = {}

        if self.redis is None:
            return metrics

        try:
            # 队列长度指标
            for topic in topics:
                pending_count = await self.redis.llen(
                    self._get_topic_key(topic, TopicKeys.PENDING)
                )  # type: ignore
                processing_count = await self.redis.llen(
                    self._get_topic_key(topic, TopicKeys.PROCESSING)
                )  # type: ignore

                metrics[f"queue.{topic}.pending"] = pending_count
                metrics[f"queue.{topic}.processing"] = processing_count
                metrics[f"queue.{topic}.total"] = pending_count + processing_count

            # 延时队列指标
            delay_count = await self.redis.zcard(self._get_global_key(GlobalKeys.DELAY_TASKS))  # type: ignore
            metrics["delay_tasks.count"] = delay_count

            # 过期监控指标
            expire_count = await self.redis.zcard(
                self._get_global_key(GlobalKeys.EXPIRE_MONITOR)
            )  # type: ignore
            metrics["expire_monitor.count"] = expire_count

            # 消息存储指标
            payload_count = await self.redis.hlen(self._get_global_key(GlobalKeys.PAYLOAD_MAP))  # type: ignore
            metrics["payload_map.count"] = payload_count

            # 死信队列指标
            dlq_count = await self.redis.llen(self._get_global_key(GlobalKeys.DLQ_QUEUE))  # type: ignore
            dlq_payload_count = await self.redis.hlen(
                self._get_global_key(GlobalKeys.DLQ_PAYLOAD_MAP)
            )  # type: ignore
            metrics["dlq.count"] = dlq_count
            metrics["dlq_payload_map.count"] = dlq_payload_count

        except Exception as e:
            self.logger_service.log_error("收集队列指标失败", e)

        return metrics

    async def collect_processing_metrics(self, topics: list[str]) -> dict[str, Any]:
        """
        收集消息处理相关指标

        Args:
            topics: 主题列表

        Returns:
            处理指标字典
        """
        metrics = {}
        current_time = int(time.time() * 1000)

        if self.redis is None:
            return metrics

        try:
            # 处理中消息的时长分布
            for topic in topics:
                processing_key = f"{topic}:processing"
                processing_ids = await self.redis.lrange(processing_key, 0, -1)  # type: ignore

                if processing_ids:
                    processing_times = []
                    stuck_count = 0

                    for msg_id in processing_ids:
                        # 从过期监控中获取处理开始时间
                        expire_time = await self.redis.zscore(
                            "all_expire_monitor", msg_id
                        )
                        if expire_time:
                            # 处理开始时间 = 过期时间 - 处理超时时间(默认180秒)
                            start_time = int(expire_time) - 180
                            processing_time = current_time - start_time
                            processing_times.append(processing_time)

                            # 检查是否卡死（处理时间超过5分钟）
                            if processing_time > 300:
                                stuck_count += 1

                    if processing_times:
                        metrics[f"processing.{topic}.count"] = len(processing_times)
                        metrics[f"processing.{topic}.avg_time"] = sum(
                            processing_times
                        ) / len(processing_times)
                        metrics[f"processing.{topic}.max_time"] = max(processing_times)
                        metrics[f"processing.{topic}.min_time"] = min(processing_times)
                        metrics[f"processing.{topic}.stuck_count"] = stuck_count
                else:
                    metrics[f"processing.{topic}.count"] = 0
                    metrics[f"processing.{topic}.avg_time"] = 0
                    metrics[f"processing.{topic}.max_time"] = 0
                    metrics[f"processing.{topic}.min_time"] = 0
                    metrics[f"processing.{topic}.stuck_count"] = 0

        except Exception as e:
            self.logger_service.log_error("收集处理指标失败", e)

        return metrics

    async def collect_delay_metrics(self) -> dict[str, Any]:
        """
        收集延时消息相关指标

        Returns:
            延时指标字典
        """
        metrics = {}
        current_time = int(time.time() * 1000)

        if self.redis is None:
            return metrics

        try:
            # 延时消息时间分布
            # 获取所有延时任务的执行时间
            delay_tasks = await self.redis.zrange(
                self._get_global_key(GlobalKeys.DELAY_TASKS), 0, -1, withscores=True
            )  # type: ignore

            if delay_tasks:
                delays = []
                ready_count = 0

                for _task_id, execute_time in delay_tasks:
                    delay = int(execute_time) - current_time
                    delays.append(delay)

                    # 已到期的延时消息
                    if delay <= 0:
                        ready_count += 1

                metrics["delay.total_count"] = len(delays)
                metrics["delay.ready_count"] = ready_count
                metrics["delay.pending_count"] = len(delays) - ready_count

                if delays:
                    positive_delays = [d for d in delays if d > 0]
                    if positive_delays:
                        metrics["delay.avg_remaining"] = sum(positive_delays) / len(
                            positive_delays
                        )
                        metrics["delay.max_remaining"] = max(positive_delays)
                        metrics["delay.min_remaining"] = min(positive_delays)
                    else:
                        metrics["delay.avg_remaining"] = 0
                        metrics["delay.max_remaining"] = 0
                        metrics["delay.min_remaining"] = 0
            else:
                metrics["delay.total_count"] = 0
                metrics["delay.ready_count"] = 0
                metrics["delay.pending_count"] = 0
                metrics["delay.avg_remaining"] = 0
                metrics["delay.max_remaining"] = 0
                metrics["delay.min_remaining"] = 0

        except Exception as e:
            self.logger_service.log_error("收集延时指标失败", e)

        return metrics

    async def collect_error_metrics(self, topics: list[str]) -> dict[str, Any]:
        """
        收集错误相关指标

        Args:
            topics: 主题列表

        Returns:
            错误指标字典
        """
        metrics = {}

        if self.redis is None:
            return metrics

        try:
            # 死信队列统计
            dlq_messages = await self.redis.lrange(self._get_global_key(GlobalKeys.DLQ_QUEUE), 0, -1)  # type: ignore

            # 按topic统计死信消息
            topic_error_counts = dict.fromkeys(topics, 0)

            for msg_id in dlq_messages:
                queue_name = await self.redis.hget(
                    self._get_global_key(GlobalKeys.DLQ_PAYLOAD_MAP), f"{msg_id}:queue"
                )  # type: ignore
                if queue_name and queue_name in topic_error_counts:
                    topic_error_counts[queue_name] += 1

            for topic, count in topic_error_counts.items():
                metrics[f"error.{topic}.dlq_count"] = count

            # 总体错误率计算需要历史数据，这里只记录当前死信队列数量
            metrics["error.total_dlq"] = len(dlq_messages)

        except Exception as e:
            self.logger_service.log_error("收集错误指标失败", e)

        return metrics

    async def collect_throughput_metrics(
        self, window_seconds: int = 300
    ) -> dict[str, Any]:
        """
        收集吞吐率指标（需要配合历史数据计算）

        Args:
            window_seconds: 时间窗口（秒）

        Returns:
            吞吐率指标字典
        """
        metrics = {}
        current_time = int(time.time() * 1000)

        try:
            # 从历史记录计算吞吐率
            if len(self.metrics_history) >= 2:
                # 获取时间窗口内的记录
                window_start = current_time - window_seconds
                window_metrics = [
                    m
                    for m in self.metrics_history
                    if m.get("timestamp", 0) >= window_start
                ]

                if len(window_metrics) >= 2:
                    # 计算处理完成的消息数（通过payload_map的变化）
                    latest = window_metrics[-1]
                    earliest = window_metrics[0]

                    time_diff = latest["timestamp"] - earliest["timestamp"]
                    if time_diff > 0:
                        # 简单的吞吐率计算
                        payload_diff = earliest.get(
                            "payload_map.count", 0
                        ) - latest.get("payload_map.count", 0)

                        if payload_diff > 0:
                            throughput = payload_diff / time_diff * 60  # 每分钟处理数
                            metrics["throughput.messages_per_minute"] = throughput
                        else:
                            metrics["throughput.messages_per_minute"] = 0
                    else:
                        metrics["throughput.messages_per_minute"] = 0
                else:
                    metrics["throughput.messages_per_minute"] = 0
            else:
                metrics["throughput.messages_per_minute"] = 0

        except Exception as e:
            self.logger_service.log_error("收集吞吐率指标失败", e)

        return metrics

    async def collect_all_metrics(self, topics: list[str]) -> dict[str, Any]:
        """
        收集所有指标

        Args:
            topics: 主题列表

        Returns:
            所有指标字典
        """
        try:
            all_metrics = {}

            # 收集各类指标
            queue_metrics = await self.collect_queue_metrics(topics)
            processing_metrics = await self.collect_processing_metrics(topics)
            delay_metrics = await self.collect_delay_metrics()
            error_metrics = await self.collect_error_metrics(topics)
            throughput_metrics = await self.collect_throughput_metrics()

            # 合并所有指标
            all_metrics.update(queue_metrics)
            all_metrics.update(processing_metrics)
            all_metrics.update(delay_metrics)
            all_metrics.update(error_metrics)
            all_metrics.update(throughput_metrics)

            # 添加时间戳
            all_metrics["timestamp"] = int(time.time() * 1000)

            # 保存到历史记录
            self._save_to_history(all_metrics)

            return all_metrics

        except Exception as e:
            self.logger_service.log_error("收集所有指标失败", e)
            return {"timestamp": int(time.time() * 1000)}

    def _save_to_history(self, metrics: dict[str, Any]) -> None:
        """
        保存指标到历史记录

        Args:
            metrics: 指标数据
        """
        try:
            self.metrics_history.append(metrics.copy())

            # 限制历史记录大小
            if len(self.metrics_history) > self.max_history_size:
                self.metrics_history.pop(0)

        except Exception as e:
            self.logger_service.log_error("保存指标历史失败", e)

    def get_metrics_history(self, last_n: int = 100) -> list[dict[str, Any]]:
        """
        获取历史指标数据

        Args:
            last_n: 获取最近n条记录

        Returns:
            历史指标列表
        """
        return self.metrics_history[-last_n:] if self.metrics_history else []

    def clear_history(self) -> None:
        """清空历史记录"""
        self.metrics_history.clear()
        self.logger_service.logger.info("指标历史记录已清空")
