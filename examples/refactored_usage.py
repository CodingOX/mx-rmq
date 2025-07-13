"""
MX-RMQ 重构版本使用示例 - 完全组合模式
展示新架构的各种使用方式
"""

import asyncio
import json
from typing import Any

from mx_rmq import (
    RedisMessageQueue,
    MQConfig,
    MessagePriority,
    LoggerService,
    QueueContext,
    ConsumerService,
    # 新增日志门面相关导入
    LoggerFactory,
    get_logger,
    auto_configure_logging,
    setup_loguru_integration,
    get_available_backends,
)


# 示例1：基本的生产者使用
async def producer_example():
    """生产者示例"""
    config = MQConfig(
        redis_url="redis://localhost:6379",
        redis_password="RedisPassword",
        max_retries=3,
        task_queue_size=10,
    )

    queue = RedisMessageQueue(config)

    try:
        # 发送普通消息
        message_id = await queue.produce(
            topic="user_events",
            payload={"user_id": 123, "action": "login"},
            priority=MessagePriority.NORMAL,
        )
        print(f"消息发送成功: {message_id}")

        # 发送高优先级延时消息
        delay_message_id = await queue.produce(
            topic="notifications",
            payload={"message": "会议提醒", "user_id": 456},
            delay=30,  # 30s后执行
            priority=MessagePriority.HIGH,
        )
        print(f"延时消息发送成功: {delay_message_id}")

    finally:
        await queue.cleanup()


# 示例2：消费者使用
async def consumer_example():
    """消费者示例"""
    config = MQConfig(
        redis_url="redis://localhost:6379",
        redis_password="RedisPassword",
        max_workers=4,
        processing_timeout=30,
    )

    queue = RedisMessageQueue(config)

    # 注册消息处理器
    async def handle_user_events(payload: dict[str, Any]) -> None:
        """处理用户事件"""
        user_id = payload.get("user_id")
        action = payload.get("action")
        print(f"处理用户事件: 用户{user_id}执行了{action}")

        # 模拟业务处理
        await asyncio.sleep(0.1)

    async def handle_notifications(payload: dict[str, Any]) -> None:
        """处理通知消息"""
        message = payload.get("message")
        user_id = payload.get("user_id")
        print(f"发送通知给用户{user_id}: {message}")

        # 模拟发送通知
        await asyncio.sleep(0.05)

    # 注册处理器
    queue.register("user_events", handle_user_events)
    queue.register("notifications", handle_notifications)

    # 启动消费
    try:
        await queue.start_dispatch_consuming()
    except KeyboardInterrupt:
        print("收到中断信号，正在停机...")
    finally:
        await queue.cleanup()


# 示例3：日志门面模式使用示例
def logging_facade_example():
    """日志门面模式使用示例"""

    # 检查可用的日志后端
    backends = get_available_backends()
    print(f"可用的日志后端: {backends}")

    # 自动配置最佳日志后端
    backend_used = auto_configure_logging(level="INFO")
    print(f"使用的日志后端: {backend_used}")

    # 获取日志器实例（类似 SLF4J）
    logger = get_logger("MyApplication")

    # 使用统一的日志接口
    logger.info("应用程序启动", version="1.0", backend=backend_used)
    logger.debug("调试信息", module="main", function="logging_facade_example")
    logger.warning("这是一个警告", level="warn")

    # 测试错误日志
    try:
        raise ValueError("模拟错误")
    except Exception as e:
        logger.error("发生错误", error=e, component="example")

    # 如果有 loguru 可用，演示手动设置 loguru
    if backends.get("loguru"):
        print("\n=== 手动配置 Loguru 示例 ===")

        # 设置特定的日志后端
        LoggerFactory.set_adapter_type("loguru")

        # 配置 loguru 拦截标准 logging
        setup_loguru_integration(level="INFO", intercept_standard_logging=True)

        # 获取新的日志器（使用 loguru 后端）
        loguru_logger = get_logger("WithLoguru")
        loguru_logger.info("现在使用 Loguru 后端", backend="loguru")


# 示例4：LoggerService 兼容性使用
def logger_service_example():
    """LoggerService 兼容性使用示例"""

    # 创建自定义的日志服务（向后兼容）
    logger_service = LoggerService("MyCustomComponent")

    # 使用门面模式的日志接口
    logger_service.logger.info("组件初始化", component="custom", version="1.0")

    # 记录消息事件
    logger_service.log_message_event(
        event="消息处理开始", message_id="msg_123", topic="orders", user_id=789
    )

    # 记录错误
    try:
        raise ValueError("模拟错误")
    except Exception as e:
        logger_service.log_error("处理订单时出错", e, order_id=456)

    # 记录指标
    logger_service.log_metric("处理延迟", 150, unit="ms", topic="orders")


# 示例5：高级用法 - 直接使用服务组件
async def advanced_service_usage():
    """高级用法：直接使用服务组件"""
    config = MQConfig(redis_url="redis://localhost:6379")

    # 创建日志服务
    logger_service = LoggerService("AdvancedExample")

    # 初始化 Redis 连接
    import redis.asyncio as aioredis

    redis_pool = aioredis.ConnectionPool.from_url(config.redis_url)
    redis = aioredis.Redis(connection_pool=redis_pool)

    try:
        # 创建上下文
        context = QueueContext(
            config=config,
            redis=redis,
            logger_service=logger_service,
            lua_scripts={},  # 在实际使用中需要加载 Lua 脚本
        )

        # 注册处理器
        async def custom_handler(payload: dict[str, Any]) -> None:
            logger_service.logger.info("自定义处理器", payload=payload)

        context.register_handler("custom_topic", custom_handler)

        # 创建消费服务
        task_queue = asyncio.Queue(maxsize=100)
        consumer_service = ConsumerService(context, task_queue)

        logger_service.logger.info("服务组件创建完成")

    finally:
        await redis_pool.disconnect()


# 示例6：完整的生产-消费演示
async def complete_demo():
    """完整演示：同时运行生产者和消费者"""
    config = MQConfig(
        redis_url="redis://localhost:6379",
        redis_password="RedisPassword",
        max_workers=2,
        task_queue_size=10,
        queue_prefix="demo",
    )

    repeat_times = 100

    # 创建队列实例
    queue = RedisMessageQueue(config)

    # 定义消息处理器
    processed_messages = []

    async def order_handler(payload: dict[str, Any]) -> None:
        """订单处理器"""
        order_id = payload.get("order_id")
        amount = payload.get("amount", 0)

        # 模拟订单处理
        await asyncio.sleep(0.1)
        processed_messages.append(order_id)

        print(f"订单处理完成: {order_id}, 金额: {amount}")

    # 注册处理器
    queue.register("orders", order_handler)

    # 生产者任务
    async def producer_task():
        """生产者任务"""
        for i in range(repeat_times):
            await queue.produce(
                topic="orders",
                payload={
                    "order_id": f"order_{i:03d}",
                    "amount": (i + 1) * 100,
                    "customer_id": f"customer_{i % 3}",
                },
                priority=MessagePriority.HIGH if i % 3 == 0 else MessagePriority.NORMAL,
            )
            await asyncio.sleep(0.1)

        print("所有消息生产完成")

    # 消费者任务
    async def consumer_task():
        """消费者任务"""
        try:
            await queue.start_dispatch_consuming()
        except asyncio.CancelledError:
            print("消费者任务被取消")

    # 监控任务
    async def monitor_task():
        """监控任务进度"""
        start_time = asyncio.get_event_loop().time()
        while len(processed_messages) < repeat_times:
            await asyncio.sleep(1)
            elapsed = asyncio.get_event_loop().time() - start_time
            print(
                f"已处理消息数量: {len(processed_messages)}/{repeat_times}, 耗时: {elapsed:.1f}s"
            )

            if elapsed > 30:  # 30秒超时
                print("监控超时，强制退出")
                break

    # 同时运行生产者、消费者和监控
    try:
        await producer_task()
        await asyncio.sleep(2.0)

        consumer_task_obj = asyncio.create_task(consumer_task())
        monitor_task_obj = asyncio.create_task(monitor_task())

        # 先启动消费者，等待一下再启动生产者
        await asyncio.sleep(0.5)

        # 等待所有消息处理完成,这里取消了，怪不得。
        await monitor_task_obj

        # 取消消费者任务
        consumer_task_obj.cancel()
        try:
            await consumer_task_obj
        except asyncio.CancelledError:
            pass

        print(f"演示完成，共处理 {len(processed_messages)} 条消息")

    finally:
        await queue.cleanup()


# 主函数演示
async def main():
    """主函数：演示各种用法"""
    print("=== MX-RMQ 日志门面模式示例 ===\n")

    # 1. 日志门面使用示例
    print("1. 日志门面模式演示")
    logging_facade_example()

    print("\n" + "=" * 50 + "\n")

    # 2. LoggerService 兼容性示例
    print("2. LoggerService 兼容性演示")
    logger_service_example()

    print("\n" + "=" * 50 + "\n")

    # 3. 基本生产者演示
    print("3. 基本生产者演示")
    await producer_example()

    print("\n演示完成！")


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("使用方法:")
        print("  python refactored_usage.py facade      # 运行日志门面示例")
        print("  python refactored_usage.py producer    # 运行生产者示例")
        print("  python refactored_usage.py consumer    # 运行消费者示例")
        print("  python refactored_usage.py logger      # 运行日志服务示例")
        print("  python refactored_usage.py advanced    # 运行高级用法示例")
        print("  python refactored_usage.py demo        # 运行完整演示")
        print("  python refactored_usage.py main        # 运行综合演示")
        sys.exit(1)

    mode = sys.argv[1]

    if mode == "facade":
        logging_facade_example()
    elif mode == "producer":
        asyncio.run(producer_example())
    elif mode == "consumer":
        asyncio.run(consumer_example())
    elif mode == "logger":
        logger_service_example()
    elif mode == "advanced":
        asyncio.run(advanced_service_usage())
    elif mode == "demo":
        asyncio.run(complete_demo())
    elif mode == "main":
        asyncio.run(main())
    else:
        print(f"未知模式: {mode}")
        sys.exit(1)
