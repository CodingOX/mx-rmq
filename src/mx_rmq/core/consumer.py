"""
消息消费服务模块
"""

import asyncio

from .context import QueueContext
from .dispatch import TaskItem
from .lifecycle import MessageLifecycleService


class ConsumerService:
    """消费者服务类"""

    def __init__(self, context: QueueContext, task_queue: asyncio.Queue) -> None:
        self.context = context
        self.task_queue = task_queue

    async def consume_messages(self) -> None:
        """消费者协程"""
        while self.context.is_running():
            try:
                # 从本地队列获取任务 超时3秒 目的为了优雅关机
                task_item: TaskItem = await asyncio.wait_for(
                    self.task_queue.get(), timeout=3.0
                )

                topic = task_item.topic
                message = task_item.message

                message_id = message.id
                handler = self.context.handlers.get(topic)

                # 卫语句：处理器不存在则跳过此消息
                if not handler:
                    self.context.log_error(
                        "未找到处理器",
                        ValueError(f"No handler for topic: {topic}"),
                        topic=topic,
                    )
                    continue

                # 标记消息为处理中
                message.mark_processing()
                handler_service = MessageLifecycleService(self.context)

                try:
                    # 执行业务逻辑
                    await handler(message.payload)
                    # 标记完成
                    await handler_service.complete_message(message_id, topic)
                    self.context.log_message_event("消息处理成功", message_id, topic)
                except Exception as e:
                    # 处理失败
                    await handler_service.handle_message_failure(message, e)

            except TimeoutError:
                continue
            except Exception as e:
                self.context.log_error("消费者协程错误", e)
                await asyncio.sleep(1)
