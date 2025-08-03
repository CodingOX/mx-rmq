"""
消息分发服务模块
"""

import asyncio
from dataclasses import dataclass
import json
import time

from loguru import logger
from ..constants import GlobalKeys, TopicKeys
from ..message import Message
from .context import QueueContext


BLMOVE_TIMEOUT = 5
ERROR_MESSAGE_MAX_LENGTH = 20
REDIS_FEATURE_SUPPORTED = "1"
REDIS_FEATURE_NOT_SUPPORTED = "0"
ERROR_RECOVERY_SLEEP_SECONDS = 1


@dataclass
class TaskItem:
    topic: str
    message: Message


class DispatchService:
    """消息分发服务类"""

    def __init__(
        self, context: QueueContext, task_queue: asyncio.Queue, connection_manager=None
    ) -> None:
        self.context = context
        self.task_queue = task_queue
        self.connection_manager = connection_manager

    async def dispatch_messages(self, topic: str) -> None:
        """消息分发协程
        该行为无法使用 lua 因为 blmove 阻塞的。
        所以原子性无法保障
        """
        topic_pending_key = self.context.get_global_topic_key(topic, TopicKeys.PENDING)
        topic_processing_key = self.context.get_global_topic_key(
            topic, TopicKeys.PROCESSING
        )

        logger.info(
            f"启动消息分发协程,topic:{topic},pending_key:{topic_pending_key},processing_key:{topic_processing_key}"
        )

        while self.context.is_running():
            try:
                message_id = await self._fetch_message(
                    topic, topic_pending_key, topic_processing_key
                )
                if not message_id:
                    continue

                message = await self._parse_message(message_id, topic)
                if not message:
                    continue

                if self.context.shutting_down:
                    await self._return_message_to_pending(
                        topic_processing_key, topic_pending_key
                    )
                    break

                await self._process_message(message_id, topic, message)

            except ConnectionError:
                logger.info(f"Redis连接已关闭，无法继续分发消息, topic={topic}")
                break
            except Exception:
                if not self.context.shutting_down:
                    logger.exception(f"消息分发错误: topic={topic}")
                await asyncio.sleep(ERROR_RECOVERY_SLEEP_SECONDS)

        logger.info(f"消息分发协程已停止, topic={topic}")

    async def _fetch_message(
        self, topic: str, pending_key: str, processing_key: str
    ) -> str | None:
        """从pending队列获取消息到processing队列"""
        logger.debug(f"等待【Redis】消息分发，topic:{topic},pending_key:{pending_key}")

        message_id = await self.context.redis.blmove(
            pending_key,
            processing_key,
            timeout=BLMOVE_TIMEOUT,
            src="RIGHT",
            dest="LEFT",
        )  # type: ignore

        if not message_id:
            logger.debug(f"BLMOVE超时，无消息, topic={topic}")
            return None

        logger.debug(f"成功获取消息, topic={topic}, message_id={message_id}")
        return message_id

    async def _parse_message(self, message_id: str, topic: str) -> Message | None:
        """解析消息内容"""
        payload_json = await self.context.redis.hget(
            self.context.get_global_key(GlobalKeys.PAYLOAD_MAP), message_id
        )  # type: ignore

        if not payload_json:
            logger.info(f"消息体不存在, message_id={message_id}, topic={topic}")
            return None

        try:
            return Message.model_validate_json(payload_json)
        except (json.JSONDecodeError, ValueError) as e:
            await self._handle_parse_error(message_id, topic, payload_json, e)
            return None

    async def _handle_parse_error(
        self, message_id: str, topic: str, payload_json: str, error: Exception
    ) -> None:
        """处理消息解析错误"""
        logger.exception(f"消息格式错误, message_id={message_id}, topic={topic}")

        try:
            error_message = str(error)[:ERROR_MESSAGE_MAX_LENGTH]
            current_timestamp = str(int(time.time() * 1000))
            ttl_days = self.context.config.parse_error_ttl_days
            max_count = self.context.config.parse_error_max_count
            supports_hexpire = (
                REDIS_FEATURE_SUPPORTED
                if self.connection_manager and self.connection_manager.supports_hexpire
                else REDIS_FEATURE_NOT_SUPPORTED
            )

            topic_processing_key = self.context.get_global_topic_key(
                topic, TopicKeys.PROCESSING
            )

            await self.context.lua_scripts["handle_parse_error"](
                keys=[
                    self.context.get_global_key(GlobalKeys.PARSE_ERROR_PAYLOAD_MAP),
                    self.context.get_global_key(GlobalKeys.PARSE_ERROR_QUEUE),
                    topic_processing_key,
                    self.context.get_global_key(GlobalKeys.EXPIRE_MONITOR),
                    self.context.get_global_key(GlobalKeys.PAYLOAD_MAP),
                ],
                args=[
                    message_id,
                    payload_json,
                    topic,
                    error_message,
                    current_timestamp,
                    ttl_days,
                    max_count,
                    supports_hexpire,
                ],
            )

            logger.info(
                f"消息解析错误已转入错误存储, message_id={message_id}, topic={topic}, error_type=parse_error, error_message={error_message}"
            )
        except Exception:
            logger.exception(
                f"处理解析错误失败, message_id={message_id}, topic={topic}"
            )
            topic_processing_key = self.context.get_global_topic_key(
                topic, TopicKeys.PROCESSING
            )
            await self.context.redis.lrem(topic_processing_key, 1, message_id)  # type: ignore

    async def _return_message_to_pending(
        self, processing_key: str, pending_key: str
    ) -> None:
        """将消息从processing队列返回到pending队列"""
        await self.context.redis.lmove(
            processing_key, pending_key, src="LEFT", dest="LEFT"
        )  # type: ignore

    async def _process_message(
        self, message_id: str, topic: str, message: Message
    ) -> None:
        """处理正常消息"""
        expire_time = (
            int(time.time() * 1000) + self.context.config.processing_timeout * 1000
        )

        await self.context.redis.zadd(
            self.context.get_global_key(GlobalKeys.EXPIRE_MONITOR),
            {message_id: expire_time},
        )  # type: ignore

        await self.task_queue.put(TaskItem(topic, message))
