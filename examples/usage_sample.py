"""
MX-RMQ 重构版本使用示例 - 完全组合模式
展示新架构的各种使用方式
"""

import asyncio
import json
import random
import time
from typing import Any

import logging

from mx_rmq import (
    RedisMessageQueue,
    MQConfig,
    MessagePriority,
    LoggerService,
    QueueContext,
)


# 示例1：基本的生产者使用
async def producer_example():
    """生产者示例"""
    config = MQConfig(
        redis_host="redis://localhost:6479",
        # redis_password="RedisPassword",
        max_retries=3,
        task_queue_size=10,
    )

    queue = RedisMessageQueue(config)

    try:
        # # 发送普通消息
        # message_id = await queue.produce(
        #     topic="user_events",
        #     payload={"user_id": 123, "action": "login"},
        #     priority=MessagePriority.NORMAL,
        # )
        # print(f"消息发送成功: {message_id}")

        # 
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


# 示例1b：批量生成 notifications 消息
async def batch_notifications_producer(n: int = 10):
    """批量生成 n 条 notifications 消息，延时 5-60 秒随机"""
    config = MQConfig(
        redis_host="redis://localhost:6479",
        # redis_password="RedisPassword",
        max_retries=3,
        task_queue_size=10,
    )

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
                "message": f"批量通知消息 #{i+1}",
                "user_id": 1000 + i,
                "batch_id": int(current_time),
                "sequence": i + 1,
                "total": n,
                "created_at": current_time,
                "expected_execution_time": expected_execution_time,
                "delay_seconds": delay
            }
            
            # 发送延时消息
            message_id = await queue.produce(
                topic="notifications",
                payload=payload,
                delay=delay,
                priority=MessagePriority.NORMAL,
            )
            
            print(f"[{i+1}/{n}] 消息发送成功: {message_id}, 延时: {delay}秒, 期待执行时间: {time.strftime('%H:%M:%S', time.localtime(expected_execution_time))}")
            
            # 避免发送过于频繁，稍微延时
            await asyncio.sleep(0.1)
        
        print(f"批量生成完成！共发送 {n} 条消息")

    finally:
        await queue.cleanup()


# 示例2：消费者使用
async def consumer_example():
    """消费者示例"""
    # 配置彩色日志输出，这样就能看到内部日志了
    from mx_rmq.logging import setup_colored_logging
    setup_colored_logging("INFO")
    
    config = MQConfig(redis_host="redis://localhost:6479")
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
            expected_time_str = time.strftime('%H:%M:%S', time.localtime(expected_time))
            actual_time_str = time.strftime('%H:%M:%S', time.localtime(actual_execution_time))
            
            print(f"📨 通知消息: {payload['message']}")
            print(f"   期待执行时间: {expected_time_str}")
            print(f"   实际执行时间: {actual_time_str}")
            print(f"   延迟差异: {delay_diff:.2f}秒 {'(提前)' if delay_diff < 0 else '(延后)' if delay_diff > 0 else '(准时)'}")
            print(f"   用户ID: {payload.get('user_id', 'N/A')}, 序号: {payload.get('sequence', 'N/A')}/{payload.get('total', 'N/A')}")
            print("---")
        else:
            print(f"发送通知: {payload}")
        
        # 模拟通知发送
        await asyncio.sleep(0.2)

    # 注册处理器
    queue.register("user_events", handle_user_event)
    queue.register("notifications", handle_notification)

    try:
        # 启动消费者，这里会阻塞住哦。
        await queue.start_background()
        await asyncio.sleep(160)  # 运行160秒
        print("消费者运行60秒完成")
        # 手动停止消费者
        await queue.stop()
    finally:
        await queue.cleanup()


# 示例2b：专门的notifications延时测试消费者
async def notifications_delay_test_consumer():
    """专门用于测试notifications延时执行时间对比的消费者"""
    # 配置彩色日志输出
    from mx_rmq.logging import setup_colored_logging
    setup_colored_logging("INFO")
    
    config = MQConfig(redis_host="redis://localhost:6479")
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
            created_time_str = time.strftime('%H:%M:%S', time.localtime(created_time))
            expected_time_str = time.strftime('%H:%M:%S', time.localtime(expected_time))
            actual_time_str = time.strftime('%H:%M:%S', time.localtime(actual_execution_time))
            
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
            print(f"   用户信息: ID={payload.get('user_id', 'N/A')}, 批次={payload.get('batch_id', 'N/A')}")
            print(f"   进度信息: {payload.get('sequence', 'N/A')}/{payload.get('total', 'N/A')}")
            print("" + "="*50)
        else:
            print(f"📨 通知消息: {payload}")
        
        # 模拟通知处理
        await asyncio.sleep(0.1)

    # 注册处理器
    queue.register("notifications", handle_notification_with_delay_analysis)

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


# 示例3：标准日志使用示例
def logging_example():
    """标准日志使用示例"""
    
    # 首先配置日志输出
    from mx_rmq.logging import setup_basic_logging
    setup_basic_logging("INFO")
    
    # 使用标准的 Python logging 方式
    app_logger = logging.getLogger("MyApplication")
    queue_logger = logging.getLogger("mx_rmq.queue")
    component_logger = logging.getLogger("mx_rmq.PaymentService")
    
    # 使用标准的日志接口
    app_logger.info("应用程序启动")
    app_logger.debug("调试信息")
    app_logger.warning("这是一个警告")
    
    # 测试错误日志
    try:
        raise ValueError("模拟错误")
    except Exception as e:
        app_logger.error("发生错误", exc_info=e)
    
    # 队列相关日志
    queue_logger.info("队列初始化完成")
    
    # 组件相关日志
    component_logger.info("支付服务启动")


# 示例3b：彩色日志使用示例
def colored_logging_example():
    """彩色日志使用示例"""
    
    # 配置彩色日志输出
    from mx_rmq.logging import setup_colored_logging
    setup_colored_logging("DEBUG")
    
    # 使用标准的 Python logging 方式
    app_logger = logging.getLogger("MyApplication")
    queue_logger = logging.getLogger("mx_rmq.queue")
    component_logger = logging.getLogger("mx_rmq.PaymentService")
    
    print("=== 彩色日志示例 ===")
    
    # 测试各种日志级别
    app_logger.debug("这是调试信息")
    app_logger.info("这是普通信息")
    app_logger.warning("这是警告信息")
    app_logger.error("这是错误信息")
    app_logger.critical("这是严重错误信息")
    
    # 测试不同组件的日志
    queue_logger.info("队列服务启动")
    component_logger.warning("支付服务连接超时")
    
    # 测试错误日志
    try:
        raise ValueError("模拟错误")
    except Exception as e:
        app_logger.error("发生错误", exc_info=e)


# 示例3c：简洁彩色日志示例
def simple_colored_logging_example():
    """简洁彩色日志示例"""
    
    # 配置简洁彩色日志输出
    from mx_rmq.logging import setup_simple_colored_logging
    setup_simple_colored_logging("DEBUG")
    
    # 使用标准的 Python logging 方式
    app_logger = logging.getLogger("MyApplication")
    queue_logger = logging.getLogger("mx_rmq.queue")
    
    print("=== 简洁彩色日志示例 ===")
    
    # 测试各种日志级别
    app_logger.debug("调试信息")
    app_logger.info("普通信息")
    app_logger.warning("警告信息")
    app_logger.error("错误信息")
    app_logger.critical("严重错误")
    
    queue_logger.info("队列初始化完成")


# 示例4：LoggerService 兼容性使用
def logger_service_example():
    """LoggerService 兼容性使用示例"""

    # 创建自定义的日志服务（向后兼容）
    logger_service = LoggerService("MyCustomComponent")

    # 使用标准的日志接口
    logger_service.logger.info("组件初始化")

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
    config = MQConfig(redis_host="redis://localhost:6479")

    # 创建日志服务
    logger_service = LoggerService("AdvancedExample")

    # 初始化 Redis 连接
    import redis.asyncio as aioredis

    redis_pool = aioredis.ConnectionPool.from_url(config.redis_host)
    redis = aioredis.Redis(connection_pool=redis_pool)

    try:
        # 创建上下文
        context = QueueContext(
            config=config,
            redis=redis,
            logger=logger_service.logger,
            lua_scripts={},  # 在实际使用中需要加载 Lua 脚本
        )

        # 注册处理器
        async def custom_handler(payload: dict[str, Any]) -> None:
            logger_service.logger.info(f"自定义处理器 - payload={payload}")

        context.register_handler("custom_topic", custom_handler)

        logger_service.logger.info("服务组件创建完成")

    finally:
        await redis_pool.disconnect()


# 示例6：批量生成延时任务
async def generate_tasks():
    """批量生成延时任务"""
    config = MQConfig(redis_host="redis://localhost:6479")
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
    config = MQConfig(redis_host="redis://localhost:6479")
    
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
    consumer.register("orders", handle_order)
    consumer.register("notifications", handle_notification)
    
    try:
        # 启动消费者
        # asyncio.create_task(consumer.start_dispatch_consuming())
        await consumer.start_background()
        
        # 等待消费者启动
        await asyncio.sleep(1)
        
        # 发送一些消息
        for i in range(5):
            # 立即执行的订单
            await producer.produce(
                topic="orders",
                payload={"order_id": f"ORD_{i:03d}", "amount": 100 + i * 10}
            )
            
            # 延时通知
            await producer.produce(
                topic="notifications",
                payload={"message": f"订单 ORD_{i:03d} 已创建"},
                delay=5 + i  # 5-9秒后发送
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


# 主函数演示
async def main():
    """主函数：演示各种用法"""
    print("=== MX-RMQ 简化日志系统示例 ===\n")
    
    # 1. 简化日志使用示例
    print("1. 简化日志系统演示")
    logging_example()

    print("\n" + "=" * 50 + "\n")

    # 2. LoggerService 兼容性示例
    print("2. LoggerService 兼容性演示")
    logger_service_example()

    print("\n" + "=" * 50 + "\n")

    # 3. 基本生产者演示
    print("3. 基本生产者演示")
    await producer_example()

    print("\n演示完成！")


# 示例5：综合日志测试
def test_all_logging():
    """测试所有日志功能的综合示例"""
    print("=== MX-RMQ 日志功能综合测试 ===\n")
    
    # 1. 测试基本日志
    print("1. 测试基本日志配置：")
    from mx_rmq.logging import setup_basic_logging
    setup_basic_logging("INFO")
    
    logger = logging.getLogger("BasicTest")
    logger.info("基本日志测试")
    logger.warning("基本日志警告")
    logger.error("基本日志错误")
    
    print("\n" + "="*50 + "\n")
    
    # 2. 测试彩色日志
    print("2. 测试彩色日志配置：")
    from mx_rmq.logging import setup_colored_logging
    setup_colored_logging("DEBUG")
    
    logger = logging.getLogger("ColoredTest")
    logger.debug("彩色日志调试")
    logger.info("彩色日志信息")
    logger.warning("彩色日志警告")
    logger.error("彩色日志错误")
    logger.critical("彩色日志严重错误")
    
    print("\n" + "="*50 + "\n")
    
    # 3. 测试简洁彩色日志
    print("3. 测试简洁彩色日志配置：")
    from mx_rmq.logging import setup_simple_colored_logging
    setup_simple_colored_logging("INFO")
    
    logger = logging.getLogger("SimpleColoredTest")
    logger.info("简洁彩色日志信息")
    logger.warning("简洁彩色日志警告")
    logger.error("简洁彩色日志错误")
    
    print("\n" + "="*50 + "\n")
    
    # 4. 测试 LoggerService
    print("4. 测试 LoggerService 兼容性：")
    from mx_rmq import LoggerService
    
    logger_service = LoggerService("TestService")
    logger_service.logger.info("LoggerService 测试")
    logger_service.log_message_event("测试事件", "msg_001", "test_topic", test_param="value")
    logger_service.log_metric("测试指标", 100, unit="ms")
    
    try:
        raise ValueError("测试错误")
    except Exception as e:
        logger_service.log_error("测试错误处理", e, context="测试")
    
    print("\n=== 所有日志功能测试完成 ===")


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("使用方法:")
        print(" uv run  python usage_sample.py logging        # 运行标准日志示例")
        print(" uv run  python usage_sample.py colored        # 运行彩色日志示例")
        print(" uv run  python usage_sample.py simple_colored # 运行简洁彩色日志示例")
        print(" uv run  python usage_sample.py test_all_logging # 测试所有日志功能")
        print(" uv run  python usage_sample.py producer       # 运行生产者示例")
        print(" uv run  python usage_sample.py consumer       # 运行消费者示例")
        print(" uv run  python usage_sample.py logger         # 运行日志服务示例")
        print(" uv run  python usage_sample.py advanced       # 运行高级用法示例")
        print(" uv run  python usage_sample.py demo           # 运行完整演示")
        print(" uv run  python usage_sample.py main           # 运行综合演示")
        print(" uv run  python usage_sample.py generate       # 运行生成批量延时任务")
        print(" uv run  python usage_sample.py batch_notifications [n] # 批量生成 n 条 notifications 消息(默认10条)")
        print(" uv run  python usage_sample.py notifications_consumer    # 启动notifications延时测试消费者")
        sys.exit(1)

    mode = sys.argv[1]

    if mode == "logging":
        logging_example()
    elif mode == "colored":
        colored_logging_example()
    elif mode == "simple_colored":
        simple_colored_logging_example()
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
    elif mode == "test_all_logging":
        test_all_logging()
    else:
        print(f"未知模式: {mode}")
        sys.exit(1)
