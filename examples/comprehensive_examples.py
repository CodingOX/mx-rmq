#!/usr/bin/env python3
"""
MX-RMQ 综合使用示例
展示从基础到高级的各种使用方式，包括新添加的API功能
"""

import asyncio
import random
import time
import logging
from typing import Any
from loguru import logger

from mx_rmq import (
    RedisMessageQueue,
    MQConfig,
    MessagePriority,
    QueueContext,
)

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


# ==================== 基础功能示例 ====================

# 示例1：基本的生产者使用
async def producer_example():
    """生产者示例"""
    config = MQConfig()

    queue = RedisMessageQueue(config)

    try:
        # 发送高优先级延时消息
        delay_message_id = await queue.produce(
            topic="notifications",
            payload={"message": "会议提醒", "user_id": 456},
            delay=30,  # 30s后执行
            priority=MessagePriority.HIGH,
        )
        print(f"{time.time()}:延时消息发送成功: {delay_message_id}")

    finally:
        await queue.cleanup()


# 示例2：批量生成 notifications 消息
async def batch_notifications_producer(n: int = 10):
    """批量生成 n 条 notifications 消息，延时 5-60 秒随机"""
    config = MQConfig()

    queue = RedisMessageQueue(config)

    try:
        print(f"开始批量生成 {n} 条 notifications 消息...")

        for i in range(n):
            # 生成 5-60 秒的随机延时
            delay = random.randint(5, 60)

            # 计算期待执行时间
            current_time = time.time()
            expected_execution_time = current_time + delay

            # 生成消息内容，包含期待执行时间
            payload = {
                "message": f"批量通知消息 #{i + 1}",
                "user_id": 1000 + i,
                "batch_id": int(current_time),
                "sequence": i + 1,
                "total": n,
                "created_at": current_time,
                "expected_execution_time": expected_execution_time,
                "delay_seconds": delay,
            }

            # 发送延时消息
            message_id = await queue.produce(
                topic="notifications",
                payload=payload,
                delay=delay,
                priority=MessagePriority.NORMAL,
            )

            print(
                f"[{i + 1}/{n}] 消息发送成功: {message_id}, 延时: {delay}秒, 期待执行时间: {time.strftime('%H:%M:%S', time.localtime(expected_execution_time))}"
            )

            # 避免发送过于频繁，稍微延时
            await asyncio.sleep(0.1)

        print(f"批量生成完成！共发送 {n} 条消息")

    finally:
        await queue.cleanup()


# 示例3：消费者使用
async def consumer_example():
    """消费者示例"""

    config = MQConfig()
    queue = RedisMessageQueue(config)

    async def handle_user_event(payload: dict[str, Any]) -> None:
        """处理用户事件"""
        print(f"处理用户事件: {payload}")
        # 模拟业务处理
        await asyncio.sleep(0.1)

    async def handle_notification(payload: dict[str, Any]) -> None:
        """处理通知"""
        actual_execution_time = time.time()

        # 检查是否包含期待执行时间信息
        if "expected_execution_time" in payload:
            expected_time = payload["expected_execution_time"]
            delay_diff = actual_execution_time - expected_time

            # 格式化时间显示
            expected_time_str = time.strftime("%H:%M:%S", time.localtime(expected_time))
            actual_time_str = time.strftime(
                "%H:%M:%S", time.localtime(actual_execution_time)
            )

            print(f"📨 通知消息: {payload['message']}")
            print(f"   期待执行时间: {expected_time_str}")
            print(f"   实际执行时间: {actual_time_str}")
            print(
                f"   延迟差异: {delay_diff:.2f}秒 {'(提前)' if delay_diff < 0 else '(延后)' if delay_diff > 0 else '(准时)'}"
            )
            print(
                f"   用户ID: {payload.get('user_id', 'N/A')}, 序号: {payload.get('sequence', 'N/A')}/{payload.get('total', 'N/A')}"
            )
            print("---")
        else:
            print(f"发送通知: {payload}")

        # 模拟通知发送
        await asyncio.sleep(0.2)

    # 注册处理器
    queue.register_handler("user_events", handle_user_event)
    queue.register_handler("notifications", handle_notification)

    try:
        # 启动消费者，这里会阻塞住哦。
        await queue.start_background()
        await asyncio.sleep(160)  # 运行160秒
        print("消费者运行60秒完成")
        # 手动停止消费者
        await queue.stop()
    finally:
        await queue.cleanup()


# 示例4：专门的notifications延时测试消费者
async def notifications_delay_test_consumer():
    """专门用于测试notifications延时执行时间对比的消费者"""

    config = MQConfig()
    queue = RedisMessageQueue(config)

    async def handle_notification_with_delay_analysis(payload: dict[str, Any]) -> None:
        """处理通知并分析延时差异"""
        actual_execution_time = time.time()

        # 检查是否包含期待执行时间信息
        if "expected_execution_time" in payload:
            expected_time = payload["expected_execution_time"]
            created_time = payload.get("created_at", 0)
            delay_seconds = payload.get("delay_seconds", 0)
            delay_diff = actual_execution_time - expected_time

            # 格式化时间显示
            created_time_str = time.strftime("%H:%M:%S", time.localtime(created_time))
            expected_time_str = time.strftime("%H:%M:%S", time.localtime(expected_time))
            actual_time_str = time.strftime(
                "%H:%M:%S", time.localtime(actual_execution_time)
            )

            # 计算延时状态
            if abs(delay_diff) <= 1:  # 1秒内认为准时
                status = "✅ 准时"
            elif delay_diff > 0:
                status = f"⏰ 延后 {delay_diff:.2f}秒"
            else:
                status = f"⚡ 提前 {abs(delay_diff):.2f}秒"

            print(f"\n📨 {payload['message']}")
            print(f"   创建时间: {created_time_str}")
            print(f"   设定延时: {delay_seconds}秒")
            print(f"   期待执行: {expected_time_str}")
            print(f"   实际执行: {actual_time_str}")
            print(f"   执行状态: {status}")
            print(
                f"   用户信息: ID={payload.get('user_id', 'N/A')}, 批次={payload.get('batch_id', 'N/A')}"
            )
            print(
                f"   进度信息: {payload.get('sequence', 'N/A')}/{payload.get('total', 'N/A')}"
            )
            print("" + "=" * 50)
        else:
            print(f"📨 通知消息: {payload}")

        # 模拟通知处理
        await asyncio.sleep(0.1)

    # 注册处理器
    queue.register_handler("notifications", handle_notification_with_delay_analysis)

    try:
        print("🚀 启动notifications延时测试消费者...")
        print("等待消息处理，按 Ctrl+C 停止\n")

        # 启动消费者
        await queue.start_background()
        await asyncio.sleep(300)  # 运行5分钟
        print("\n⏹️  消费者运行完成")

        # 手动停止消费者
        await queue.stop()
    except KeyboardInterrupt:
        print("\n⏹️  收到停止信号，正在关闭消费者...")
        await queue.stop()
    finally:
        await queue.cleanup()


# 示例5：高级用法 - 直接使用服务组件
async def advanced_service_usage():
    """高级用法：直接使用服务组件"""
    config = MQConfig()

    # 初始化 Redis 连接
    import redis.asyncio as aioredis

    redis_pool = aioredis.ConnectionPool.from_url(config.redis_host)
    redis = aioredis.Redis(connection_pool=redis_pool)

    try:
        # 创建上下文
        context = QueueContext(
            config=config,
            redis=redis,
            lua_scripts={},  # 在实际使用中需要加载 Lua 脚本
        )

        # 注册处理器
        async def custom_handler(payload: dict[str, Any]) -> None:
            logger.info(f"自定义处理器 - payload={payload}")

        context.register_handler("custom_topic", custom_handler)

        logger.info("服务组件创建完成")

    finally:
        await redis_pool.disconnect()


# 示例6：批量生成延时任务
async def generate_tasks():
    """批量生成延时任务"""
    config = MQConfig()
    queue = RedisMessageQueue(config)

    try:
        # 生成100个延时任务
        for i in range(100):
            delay = random.randint(5, 300)  # 5到300秒的随机延时
            await queue.produce(
                topic="batch_task",
                payload={"task_id": i, "data": f"task_{i}"},
                delay=delay,
            )
            print(f"生成任务 {i}: 延时 {delay} 秒")
            await asyncio.sleep(0.1)  # 避免过于频繁

    finally:
        await queue.cleanup()


# 示例7：完整的演示
async def complete_demo():
    """完整的演示：生产者+消费者"""
    config = MQConfig()

    # 创建生产者
    producer = RedisMessageQueue(config)

    # 创建消费者
    consumer = RedisMessageQueue(config)

    # 定义处理器
    async def handle_order(payload: dict[str, Any]) -> None:
        order_id = payload.get("order_id")
        print(f"处理订单: {order_id}")
        await asyncio.sleep(0.5)  # 模拟处理时间
        print(f"订单 {order_id} 处理完成")

    async def handle_notification(payload: dict[str, Any]) -> None:
        message = payload.get("message")
        print(f"发送通知: {message}")
        await asyncio.sleep(0.2)

    # 注册处理器
    consumer.register_handler("orders", handle_order)
    consumer.register_handler("notifications", handle_notification)

    try:
        # 启动消费者
        # asyncio.create_task(consumer.start())
        await consumer.start_background()

        # 等待消费者启动
        await asyncio.sleep(1)

        # 发送一些消息
        for i in range(5):
            # 立即执行的订单
            await producer.produce(
                topic="orders",
                payload={"order_id": f"ORD_{i:03d}", "amount": 100 + i * 10},
            )

            # 延时通知
            await producer.produce(
                topic="notifications",
                payload={"message": f"订单 ORD_{i:03d} 已创建"},
                delay=5 + i,  # 5-9秒后发送
            )

            await asyncio.sleep(0.5)

        # 等待处理完成
        print("等待消息处理...")
        await asyncio.sleep(15)
        # 停止消费者
        await consumer.stop()

    finally:
        await producer.cleanup()
        await consumer.cleanup()


# ==================== 新API功能示例 ====================

# 示例8: 非阻塞启动 - 推荐的异步使用方式
async def example_non_blocking_startup():
    """示例: 非阻塞启动 - 推荐的异步使用方式"""
    print("\n=== 示例: 非阻塞启动 ===")

    config = MQConfig()
    queue = RedisMessageQueue(config)

    # 注册消息处理器
    async def handle_message(payload):
        print(f"处理消息: {payload}")
        await asyncio.sleep(0.1)  # 模拟处理时间

    queue.register_handler("test_topic", handle_message)

    try:
        # 非阻塞启动 - 立即返回Task对象
        background_task = await queue.start_background()
        print(f"队列已启动，运行状态: {queue.is_running()}")

        # 发送一些测试消息
        for i in range(3):
            message_id = await queue.produce("test_topic", {"data": f"message_{i}"})
            print(f"发送消息: {message_id}")

        # 等待消息处理
        await asyncio.sleep(2)

        # 检查状态
        status = queue.status
        print(f"队列状态: {status}")

        # 健康检查
        health = await queue.health_check()
        print(f"健康状态: {health['healthy']}")

        # 优雅停止
        await queue.stop()
        print(f"队列已停止，运行状态: {queue.is_running()}")

    except Exception as e:
        print(f"错误: {e}")
        if queue.is_running():
            await queue.stop()


# 示例9: 异步上下文管理器 - 自动资源管理
async def example_context_manager():
    """示例: 异步上下文管理器 - 自动资源管理"""
    print("\n=== 示例: 异步上下文管理器 ===")

    config = MQConfig()

    # 使用异步上下文管理器，自动初始化和清理
    async with RedisMessageQueue(config) as queue:
        # 注册处理器
        async def handle_context_message(payload):
            print(f"上下文处理消息: {payload}")

        queue.register_handler("context_topic", handle_context_message)

        # 启动后台服务
        await queue.start_background()

        # 发送消息
        await queue.produce("context_topic", {"message": "使用上下文管理器"})

        # 等待处理
        await asyncio.sleep(1)

        print("上下文管理器将自动清理资源")
    # 这里会自动调用 __aexit__，停止队列并清理资源


# 示例10: 同步运行 - 简单场景的便利方法
def example_synchronous_run():
    """示例: 同步运行 - 简单场景的便利方法"""
    print("\n=== 示例: 同步运行 ===")

    config = MQConfig()
    queue = RedisMessageQueue(config)

    # 注册处理器
    async def handle_sync_message(payload):
        print(f"同步模式处理消息: {payload}")

    queue.register_handler("sync_topic", handle_sync_message)

    # 在另一个线程中发送消息（模拟生产者）
    async def producer():
        await asyncio.sleep(0.5)  # 等待队列启动
        for i in range(2):
            await queue.produce("sync_topic", {"sync_data": i})
            await asyncio.sleep(0.5)

    # 启动生产者任务
    asyncio.create_task(producer())

    # 同步运行3秒后自动停止
    print("同步运行3秒...")
    queue.run(duration=3.0)
    print("同步运行完成")


# 示例11: 高级生命周期管理
async def example_advanced_lifecycle():
    """示例: 高级生命周期管理"""
    print("\n=== 示例: 高级生命周期管理 ===")

    config = MQConfig()
    queue = RedisMessageQueue(config)

    async def handle_lifecycle_message(payload):
        print(f"生命周期消息: {payload}")

    queue.register_handler("lifecycle_topic", handle_lifecycle_message)

    try:
        # 手动初始化
        await queue.initialize()
        print(f"初始化状态: {queue.status['initialized']}")

        # 启动后台服务
        task = await queue.start_background()
        print(f"启动后状态: {queue.status}")

        # 发送消息
        await queue.produce("lifecycle_topic", {"stage": "running"})

        # 监控运行状态
        for i in range(3):
            await asyncio.sleep(1)
            status = queue.status
            print(
                f"第{i + 1}秒状态: 运行={status['running']}, 活跃任务={status.get('active_tasks_count', 0)}"
            )

        # 检查后台任务状态
        if not task.done():
            print("后台任务正常运行")
        else:
            print(f"后台任务已完成，异常: {task.exception()}")

    finally:
        await queue.stop()


# 示例12: 错误处理和恢复
async def example_error_handling():
    """示例: 错误处理和恢复"""
    print("\n=== 示例: 错误处理 ===")

    config = MQConfig()
    queue = RedisMessageQueue(config)

    async def handle_error_message(payload):
        if payload.get("should_fail"):
            raise ValueError("模拟处理错误")
        print(f"成功处理: {payload}")

    queue.register_handler("error_topic", handle_error_message)

    try:
        await queue.start_background()

        # 发送正常消息
        await queue.produce("error_topic", {"data": "正常消息"})

        # 发送会失败的消息
        await queue.produce("error_topic", {"data": "错误消息", "should_fail": True})

        await asyncio.sleep(2)

        # 检查健康状态
        health = await queue.health_check()
        print(f"健康检查结果: {health}")

    except Exception as e:
        print(f"捕获到错误: {e}")
    finally:
        await queue.stop()


# 示例13: 改进前后对比
async def comparison_old_vs_new():
    """对比改进前后的使用方式"""
    print("\n=== 改进前后对比 ===")

    print("\n改进前（阻塞式）:")
    print("""
    queue = RedisMessageQueue()
    
    @queue.register_handler("topic")
    async def handler(payload):
        print(payload)
    
    # 问题：这会阻塞调用者
    await queue.start()  # 阻塞！
    """)

    print("\n改进后（多种选择）:")
    print("""
    # 选择1: 非阻塞启动（推荐）
    task = await queue.start_background()  # 立即返回
    # ... 做其他事情 ...
    await queue.stop()  # 优雅停止
    
    # 选择2: 上下文管理器
    async with RedisMessageQueue() as queue:
        await queue.start_background()
        # 自动清理
    
    # 选择3: 同步运行（简单场景）
    queue.run(duration=10)  # 运行10秒
    
    # 选择4: 保持兼容性
    await queue.start()  # 仍然可用
    """)


# ==================== 主函数和命令行接口 ====================

async def main():
    """主函数：演示各种用法"""
    print("RedisMessageQueue 综合功能演示")
    print("=" * 50)

    # 3. 基本生产者演示
    print("基本生产者演示")
    await producer_example()

    print("\n演示完成！")


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("RedisMessageQueue 综合使用示例")
        print("=" * 50)
        print("基础功能示例:")
        print(" uv run python comprehensive_examples.py producer       # 运行生产者示例")
        print(" uv run python comprehensive_examples.py consumer       # 运行消费者示例")
        print(" uv run python comprehensive_examples.py advanced       # 运行高级用法示例")
        print(" uv run python comprehensive_examples.py demo           # 运行完整演示")
        print(" uv run python comprehensive_examples.py main           # 运行综合演示")
        print(" uv run python comprehensive_examples.py generate       # 运行生成批量延时任务")
        print(" uv run python comprehensive_examples.py notifications_consumer    # 启动notifications延时测试消费者")
        print(" uv run python comprehensive_examples.py batch_notifications [n]   # 批量生成 n 条 notifications 消息(默认10条)")
        print("\n新API功能示例:")
        print(" uv run python comprehensive_examples.py non_blocking   # 非阻塞启动示例")
        print(" uv run python comprehensive_examples.py context        # 异步上下文管理器示例")
        print(" uv run python comprehensive_examples.py sync           # 同步运行示例")
        print(" uv run python comprehensive_examples.py lifecycle      # 高级生命周期管理示例")
        print(" uv run python comprehensive_examples.py error          # 错误处理示例")
        print(" uv run python comprehensive_examples.py compare        # 新旧API对比")
        print("\n运行所有新API示例:")
        print(" uv run python comprehensive_examples.py all_new        # 运行所有新API示例")
        
        sys.exit(1)

    mode = sys.argv[1]

    if mode == "producer":
        asyncio.run(producer_example())
    elif mode == "consumer":
        asyncio.run(consumer_example())
    elif mode == "advanced":
        asyncio.run(advanced_service_usage())
    elif mode == "demo":
        asyncio.run(complete_demo())
    elif mode == "main":
        asyncio.run(main())
    elif mode == "generate":
        asyncio.run(generate_tasks())
    elif mode == "batch_notifications":
        # 获取消息数量参数，默认为10
        n = 10
        if len(sys.argv) > 2:
            try:
                n = int(sys.argv[2])
            except ValueError:
                print("错误：消息数量必须是整数")
                sys.exit(1)
        asyncio.run(batch_notifications_producer(n))
    elif mode == "notifications_consumer":
        asyncio.run(notifications_delay_test_consumer())
    elif mode == "non_blocking":
        asyncio.run(example_non_blocking_startup())
    elif mode == "context":
        asyncio.run(example_context_manager())
    elif mode == "sync":
        example_synchronous_run()
    elif mode == "lifecycle":
        asyncio.run(example_advanced_lifecycle())
    elif mode == "error":
        asyncio.run(example_error_handling())
    elif mode == "compare":
        asyncio.run(comparison_old_vs_new())
    elif mode == "all_new":
        # 运行所有新API示例
        async def run_all_new_examples():
            try:
                await example_non_blocking_startup()
                await example_context_manager()
                await example_advanced_lifecycle()
                await example_error_handling()
                await comparison_old_vs_new()
                print("\n注意: 同步运行示例需要单独运行")
                print("运行命令: python comprehensive_examples.py sync")
            except Exception as e:
                print(f"演示过程中出错: {e}")
        
        asyncio.run(run_all_new_examples())
    else:
        print(f"未知模式: {mode}")
        sys.exit(1)