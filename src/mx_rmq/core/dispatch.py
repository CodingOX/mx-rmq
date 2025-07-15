"""
消息分发服务模块
"""

import asyncio
from dataclasses import dataclass
import json
import time

from ..constants import GlobalKeys, TopicKeys
from ..message import Message
from .context import QueueContext


@dataclass
class TaskItem:
    topic: str
    message: Message


class DispatchService:
    """消息分发服务类"""

    def __init__(self, context: QueueContext, task_queue: asyncio.Queue) -> None:
        self.context = context
        self.task_queue = task_queue

    async def dispatch_messages(self, topic: str) -> None:
        """消息分发协程"""
        pending_key = self.context.get_topic_key(topic, TopicKeys.PENDING)
        processing_key = self.context.get_topic_key(topic, TopicKeys.PROCESSING)

        self.context._logger.info(f"启动消息分发协程,topic:{topic},pending_key:{pending_key},processing_key:{processing_key}")

        while self.context.is_running():
            try:
                self.context._logger.debug(f"等待【Redis】消息分发，topic:{topic},pending_key:{pending_key}")
                
                # 使用LMOVE阻塞获取消息
                message_id = await self.context.redis.blmove(  # type: ignore
                    pending_key, processing_key, timeout=5, src="RIGHT", dest="LEFT"
                )

                # 卫语句：没有消息则继续下次循环
                if not message_id:
                    self.context._logger.debug(f"BLMOVE超时，无消息, topic={topic}")
                    continue
                
                self.context._logger.info(f"成功获取消息, topic={topic}, message_id={message_id}")

                # 获取消息内容
                payload_json = await self.context.redis.hget(
                    self.context.get_global_key(GlobalKeys.PAYLOAD_MAP), message_id
                )  # type: ignore

                # 卫语句：消息内容不存在则继续下次循环
                if not payload_json:
                    self.context.log_message_event(
                        "消息体不存在，消息 id:{}", message_id, topic
                    )
                    continue

                try:
                    message = Message.model_validate_json(payload_json)
                except (json.JSONDecodeError, ValueError) as e:
                    # 早期处理：消息格式错误，转入专用解析错误存储
                    self.context.log_error(
                        "消息格式错误", e, message_id=message_id, topic=topic
                    )
                    
                    # 使用 Lua 脚本原子性地处理解析错误
                    try:
                        error_message = str(e)[:20]  # 限制错误信息长度
                        current_timestamp = str(int(time.time() * 1000))
                        
                        await self.context.lua_scripts["handle_parse_error"](
                            keys=[
                                self.context.get_global_key(GlobalKeys.PARSE_ERROR_PAYLOAD_MAP),
                                self.context.get_global_key(GlobalKeys.PARSE_ERROR_QUEUE),
                                processing_key,
                                self.context.get_global_key(GlobalKeys.EXPIRE_MONITOR),
                                self.context.get_global_key(GlobalKeys.PAYLOAD_MAP),
                            ],
                            args=[
                                message_id,
                                payload_json,  # 原始损坏的JSON
                                topic,
                                error_message,
                                current_timestamp,
                            ],
                        )
                        
                        self.context.log_message_event(
                            "消息解析错误已转入错误存储", message_id, topic,
                            error_type="parse_error", error_message=error_message
                        )
                    except Exception as lua_error:
                        self.context.log_error(
                            "处理解析错误失败", lua_error, message_id=message_id, topic=topic
                        )
                        # 兜底清理：直接从processing队列移除
                        await self.context.redis.lrem(processing_key, 1, message_id)  # type: ignore

                    continue

                # 卫语句：系统正在关闭，将消息放回pending队列并退出
                if self.context.shutting_down:
                    await self.context.redis.lmove(  # type: ignore
                        processing_key, pending_key, src="LEFT", dest="LEFT"
                    )
                    break

                # 核心逻辑：处理正常消息
                expire_time = (
                    int(time.time() * 1000)
                    + self.context.config.processing_timeout * 1000
                )
                await self.context.redis.zadd(
                    self.context.get_global_key(GlobalKeys.EXPIRE_MONITOR),
                    {message_id: expire_time},
                )  # type: ignore

                # 插入本地 queue
                await self.task_queue.put(TaskItem(topic, message))

                self.context.log_message_event("消息分发成功", message_id, topic)

            except Exception as e:
                if not self.context.shutting_down:
                    self.context.log_error("消息分发错误", e, topic=topic)
                await asyncio.sleep(1)

        self.context._logger.info(f"消息分发协程已停止, topic={topic}")
