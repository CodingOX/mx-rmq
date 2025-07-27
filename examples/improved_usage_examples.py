#!/usr/bin/env python3
"""
改进后的 RedisMessageQueue 使用示例
展示新增的非阻塞启动、状态管理和上下文管理器功能
"""

import asyncio
import logging
from mx_rmq import RedisMessageQueue, MQConfig

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


async def example_1_non_blocking_startup():
    """示例1: 非阻塞启动 - 推荐的异步使用方式"""
    print("\n=== 示例1: 非阻塞启动 ===")
    
    config = MQConfig()
    queue = RedisMessageQueue(config)
    
    # 注册消息处理器
    async def handle_message(payload):
        print(f"处理消息: {payload}")
        await asyncio.sleep(0.1)  # 模拟处理时间
    
    queue.register("test_topic", handle_message)
    
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
        status = queue.get_status()
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


async def example_2_context_manager():
    """示例2: 异步上下文管理器 - 自动资源管理"""
    print("\n=== 示例2: 异步上下文管理器 ===")
    
    config = MQConfig()
    
    # 使用异步上下文管理器，自动初始化和清理
    async with RedisMessageQueue(config) as queue:
        # 注册处理器
        async def handle_context_message(payload):
            print(f"上下文处理消息: {payload}")
            
        queue.register("context_topic", handle_context_message)
            
        # 启动后台服务
        await queue.start_background()
        
        # 发送消息
        await queue.produce("context_topic", {"message": "使用上下文管理器"})
        
        # 等待处理
        await asyncio.sleep(1)
        
        print("上下文管理器将自动清理资源")
    # 这里会自动调用 __aexit__，停止队列并清理资源


def example_3_synchronous_run():
    """示例3: 同步运行 - 简单场景的便利方法"""
    print("\n=== 示例3: 同步运行 ===")
    
    config = MQConfig()
    queue = RedisMessageQueue(config)
    
    # 注册处理器
    async def handle_sync_message(payload):
        print(f"同步模式处理消息: {payload}")
    
    queue.register("sync_topic", handle_sync_message)
    
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


async def example_4_advanced_lifecycle():
    """示例4: 高级生命周期管理"""
    print("\n=== 示例4: 高级生命周期管理 ===")
    
    config = MQConfig()
    queue = RedisMessageQueue(config)
    
    async def handle_lifecycle_message(payload):
        print(f"生命周期消息: {payload}")
    
    queue.register("lifecycle_topic", handle_lifecycle_message)
    
    try:
        # 手动初始化
        await queue.initialize()
        print(f"初始化状态: {queue.get_status()['initialized']}")
        
        # 启动后台服务
        task = await queue.start_background()
        print(f"启动后状态: {queue.get_status()}")
        
        # 发送消息
        await queue.produce("lifecycle_topic", {"stage": "running"})
        
        # 监控运行状态
        for i in range(3):
            await asyncio.sleep(1)
            status = queue.get_status()
            print(f"第{i+1}秒状态: 运行={status['running']}, 活跃任务={status.get('active_tasks_count', 0)}")
        
        # 检查后台任务状态
        if not task.done():
            print("后台任务正常运行")
        else:
            print(f"后台任务已完成，异常: {task.exception()}")
            
    finally:
        await queue.stop()


async def example_5_error_handling():
    """示例5: 错误处理和恢复"""
    print("\n=== 示例5: 错误处理 ===")
    
    config = MQConfig()
    queue = RedisMessageQueue(config)
    
    async def handle_error_message(payload):
        if payload.get("should_fail"):
            raise ValueError("模拟处理错误")
        print(f"成功处理: {payload}")
    
    queue.register("error_topic", handle_error_message)
    
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
    await queue.start_dispatch_consuming()  # 阻塞！
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
    await queue.start_dispatch_consuming()  # 仍然可用
    """)


async def main():
    """运行所有示例"""
    print("RedisMessageQueue 改进功能演示")
    print("=" * 50)
    
    try:
        await example_1_non_blocking_startup()
        await example_2_context_manager()
        await example_4_advanced_lifecycle()
        await example_5_error_handling()
        await comparison_old_vs_new()
        
        print("\n注意: 示例3需要单独运行（同步方法）")
        print("运行命令: python improved_usage_examples.py --sync")
        
    except Exception as e:
        print(f"演示过程中出错: {e}")


if __name__ == "__main__":
    import sys
    
    if "--sync" in sys.argv:
        # 运行同步示例
        example_3_synchronous_run()
    else:
        # 运行异步示例
        asyncio.run(main())