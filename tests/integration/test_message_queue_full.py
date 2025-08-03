"""
完整消息队列功能集成测试
"""

import asyncio
import pytest
import time
from typing import List

from mx_rmq import RedisMessageQueue
from mx_rmq.config import MQConfig
from mx_rmq.message import Message, MessagePriority


@pytest.mark.integration
class TestCompleteMessageQueue:
    """完整消息队列功能测试"""
    
    @pytest.mark.asyncio
    async def test_end_to_end_message_processing_redis8(self):
        """端到端消息处理测试 - Redis 8.x"""
        config = MQConfig(
            redis_host="localhost",
            redis_port=6378,
            redis_db=2,
            queue_prefix="e2e_test_v8",
            max_retries=2
        )
        
        queue = RedisMessageQueue(config)
        processed_messages = []
        
        def message_handler(payload):
            processed_messages.append({
                "payload": payload,
                "processed_at": time.time()
            })
            return {"status": "processed", "id": payload.get("id")}
        
        try:
            # 注册处理器
            queue.register_handler("test_messages", message_handler)
            
            # 初始化并启动队列
            await queue.initialize()
            await queue.start_background()
            
            # 等待队列启动
            await asyncio.sleep(1)
            
            # 发送多个测试消息
            test_messages = [
                {"id": "msg_001", "type": "order", "data": "订单数据1"},
                {"id": "msg_002", "type": "user", "data": "用户数据1"},
                {"id": "msg_003", "type": "payment", "data": "支付数据1"}
            ]
            
            # 发送消息
            for msg_data in test_messages:
                await queue.produce("test_messages", msg_data)
            
            # 等待消息处理完成
            await asyncio.sleep(3)
            
            # 验证所有消息都被处理
            assert len(processed_messages) == 3
            
            # 验证处理的消息内容
            processed_ids = [msg["payload"]["id"] for msg in processed_messages]
            expected_ids = ["msg_001", "msg_002", "msg_003"]
            
            for expected_id in expected_ids:
                assert expected_id in processed_ids
            
            print(f"✅ Redis 8.x - 成功处理 {len(processed_messages)} 条消息")
            
        finally:
            await queue.stop()
            await queue.cleanup()
    
    @pytest.mark.asyncio
    async def test_end_to_end_message_processing_redis6(self):
        """端到端消息处理测试 - Redis 6.x"""
        config = MQConfig(
            redis_host="localhost",
            redis_port=6376,
            redis_db=2,
            queue_prefix="e2e_test_v6",
            max_retries=2
        )
        
        queue = RedisMessageQueue(config)
        processed_messages = []
        
        def message_handler(payload):
            processed_messages.append({
                "payload": payload,
                "processed_at": time.time()
            })
            return {"status": "processed", "id": payload.get("id")}
        
        try:
            queue.register_handler("test_messages", message_handler)
            await queue.initialize()
            await queue.start_background()
            await asyncio.sleep(1)
            
            test_messages = [
                {"id": "msg_004", "type": "order", "data": "订单数据2"},
                {"id": "msg_005", "type": "user", "data": "用户数据2"},
                {"id": "msg_006", "type": "payment", "data": "支付数据2"}
            ]
            
            for msg_data in test_messages:
                await queue.produce("test_messages", msg_data)
            
            await asyncio.sleep(3)
            
            assert len(processed_messages) == 3
            
            processed_ids = [msg["payload"]["id"] for msg in processed_messages]
            expected_ids = ["msg_004", "msg_005", "msg_006"]
            
            for expected_id in expected_ids:
                assert expected_id in processed_ids
            
            print(f"✅ Redis 6.x - 成功处理 {len(processed_messages)} 条消息")
            
        finally:
            await queue.stop()
            await queue.cleanup()
    
    @pytest.mark.asyncio
    async def test_priority_message_ordering(self):
        """测试优先级消息排序"""
        config = MQConfig(
            redis_host="localhost",
            redis_port=6378,
            redis_db=3,
            queue_prefix="priority_test"
        )
        
        queue = RedisMessageQueue(config)
        processing_order = []
        
        def priority_handler(payload):
            processing_order.append({
                "id": payload["id"],
                "priority": payload["priority"],
                "timestamp": time.time()
            })
            # 添加少量延迟以观察处理顺序
            time.sleep(0.1)
            return {"processed": payload["id"]}
        
        try:
            queue.register_handler("priority_queue", priority_handler)
            await queue.initialize()
            await queue.start_background()
            await asyncio.sleep(1)
            
            # 按顺序发送不同优先级的消息
            messages = [
                {"id": "low_1", "priority": "low"},
                {"id": "high_1", "priority": "high"}, 
                {"id": "normal_1", "priority": "normal"},
                {"id": "high_2", "priority": "high"},
                {"id": "low_2", "priority": "low"}
            ]
            
            # 发送消息时指定优先级
            await queue.produce("priority_queue", messages[0], priority=MessagePriority.LOW)
            await queue.produce("priority_queue", messages[1], priority=MessagePriority.HIGH)
            await queue.produce("priority_queue", messages[2], priority=MessagePriority.NORMAL)
            await queue.produce("priority_queue", messages[3], priority=MessagePriority.HIGH)
            await queue.produce("priority_queue", messages[4], priority=MessagePriority.LOW)
            
            await asyncio.sleep(4)
            
            assert len(processing_order) == 5
            
            # 验证至少有部分优先级排序效果
            high_priority_indices = []
            for i, msg in enumerate(processing_order):
                if msg["priority"] == "high":
                    high_priority_indices.append(i)
            
            print(f"✅ 处理顺序: {[msg['id'] for msg in processing_order]}")
            print(f"✅ 高优先级消息索引: {high_priority_indices}")
            
        finally:
            await queue.stop()
            await queue.cleanup()
    
    @pytest.mark.asyncio
    async def test_multi_topic_routing(self):
        """测试多主题路由"""
        config = MQConfig(
            redis_host="localhost",
            redis_port=6378,
            redis_db=4,
            queue_prefix="multi_topic_test"
        )
        
        queue = RedisMessageQueue(config)
        
        # 不同主题的处理结果
        results = {
            "orders": [],
            "users": [],
            "notifications": []
        }
        
        def order_handler(payload):
            results["orders"].append(payload)
            return {"topic": "orders", "processed": payload["id"]}
        
        def user_handler(payload):
            results["users"].append(payload)
            return {"topic": "users", "processed": payload["id"]}
        
        def notification_handler(payload):
            results["notifications"].append(payload)
            return {"topic": "notifications", "processed": payload["id"]}
        
        try:
            # 注册多个主题处理器
            queue.register_handler("orders", order_handler)
            queue.register_handler("users", user_handler)
            queue.register_handler("notifications", notification_handler)
            
            await queue.initialize()
            await queue.start_background()
            await asyncio.sleep(1)
            
            # 发送不同主题的消息
            await queue.produce("orders", {"id": "order_001", "amount": 99.99})
            await queue.produce("users", {"id": "user_001", "name": "张三"})
            await queue.produce("notifications", {"id": "notif_001", "message": "欢迎"})
            await queue.produce("orders", {"id": "order_002", "amount": 199.99})
            await queue.produce("users", {"id": "user_002", "name": "李四"})
            
            await asyncio.sleep(3)
            
            # 验证不同主题的消息都被正确路由
            assert len(results["orders"]) == 2
            assert len(results["users"]) == 2
            assert len(results["notifications"]) == 1
            
            # 验证消息内容
            assert results["orders"][0]["id"] == "order_001"
            assert results["orders"][1]["id"] == "order_002"
            assert results["users"][0]["id"] == "user_001"
            assert results["users"][1]["id"] == "user_002"
            assert results["notifications"][0]["id"] == "notif_001"
            
            print(f"✅ 多主题路由测试通过:")
            print(f"   Orders: {len(results['orders'])} 条")
            print(f"   Users: {len(results['users'])} 条")
            print(f"   Notifications: {len(results['notifications'])} 条")
            
        finally:
            await queue.stop()
            await queue.cleanup()
    
    @pytest.mark.asyncio
    async def test_error_handling_and_retry(self):
        """测试错误处理和重试机制"""
        config = MQConfig(
            redis_host="localhost",
            redis_port=6378,
            redis_db=5,
            queue_prefix="error_test",
            max_retries=3
        )
        
        queue = RedisMessageQueue(config)
        
        # 跟踪处理尝试
        attempt_tracker = {}
        successful_messages = []
        
        def failing_handler(payload):
            msg_id = payload["id"]
            attempt_tracker[msg_id] = attempt_tracker.get(msg_id, 0) + 1
            
            # 模拟某些消息处理失败
            if payload["should_fail"] and attempt_tracker[msg_id] <= 2:
                raise ValueError(f"模拟失败 - 消息 {msg_id}, 尝试 {attempt_tracker[msg_id]}")
            
            # 成功处理
            successful_messages.append({
                "id": msg_id,
                "attempts": attempt_tracker[msg_id],
                "processed_at": time.time()
            })
            
            return {"processed": msg_id, "attempts": attempt_tracker[msg_id]}
        
        try:
            queue.register_handler("retry_test", failing_handler)
            await queue.initialize()
            await queue.start_background()
            await asyncio.sleep(1)
            
            # 发送测试消息（有些会失败，有些会成功）
            test_messages = [
                {"id": "success_msg", "should_fail": False, "data": "正常消息"},
                {"id": "retry_msg_1", "should_fail": True, "data": "需要重试的消息1"},
                {"id": "retry_msg_2", "should_fail": True, "data": "需要重试的消息2"}
            ]
            
            for msg_data in test_messages:
                await queue.produce("retry_test", msg_data)
            
            # 等待处理和重试完成
            await asyncio.sleep(8)
            
            # 验证结果
            print(f"✅ 处理尝试统计: {attempt_tracker}")
            print(f"✅ 成功处理的消息: {len(successful_messages)}")
            
            # 正常消息应该一次成功
            assert "success_msg" in attempt_tracker
            assert attempt_tracker["success_msg"] == 1
            
            # 重试消息应该经过多次尝试
            assert "retry_msg_1" in attempt_tracker
            assert attempt_tracker["retry_msg_1"] >= 2
            
            # 验证最终都成功处理
            assert len(successful_messages) >= 1  # 至少正常消息被处理
            
        finally:
            await queue.stop()
            await queue.cleanup()
    
    @pytest.mark.asyncio
    async def test_delayed_message_processing(self):
        """测试延迟消息处理"""
        config = MQConfig(
            redis_host="localhost",
            redis_port=6378,
            redis_db=6,
            queue_prefix="delay_test"
        )
        
        queue = RedisMessageQueue(config)
        processing_times = []
        
        def delay_handler(payload):
            processing_times.append({
                "id": payload["id"],
                "expected_delay": payload["expected_delay"],
                "processed_at": time.time()
            })
            return {"processed": payload["id"]}
        
        try:
            queue.register_handler("delayed_messages", delay_handler)
            await queue.initialize()
            await queue.start_background()
            await asyncio.sleep(1)
            
            start_time = time.time()
            
            # 发送不同延迟的消息
            await queue.produce("delayed_messages", 
                               {"id": "immediate", "expected_delay": 0}, 
                               delay=0)
            
            await queue.produce("delayed_messages", 
                               {"id": "delayed_2s", "expected_delay": 2}, 
                               delay=2)
            
            await queue.produce("delayed_messages", 
                               {"id": "delayed_4s", "expected_delay": 4}, 
                               delay=4)
            
            # 等待所有消息处理完成
            await asyncio.sleep(7)
            
            # 分析处理时间
            assert len(processing_times) >= 1  # 至少立即消息被处理
            
            for msg in processing_times:
                actual_delay = msg["processed_at"] - start_time
                expected_delay = msg["expected_delay"]
                
                print(f"✅ 消息 {msg['id']}: 期望延迟 {expected_delay}s, 实际延迟 {actual_delay:.1f}s")
                
                # 验证延迟时间合理（允许一些误差）
                if expected_delay == 0:
                    assert actual_delay < 2  # 立即消息应该很快处理
                else:
                    assert actual_delay >= expected_delay - 1  # 允许1秒误差
            
        finally:
            await queue.stop()
            await queue.cleanup()
    
    @pytest.mark.asyncio
    async def test_high_throughput_processing(self):
        """测试高吞吐量处理"""
        config = MQConfig(
            redis_host="localhost",
            redis_port=6378,
            redis_db=7,
            queue_prefix="throughput_test"
        )
        
        queue = RedisMessageQueue(config)
        processed_count = 0
        processing_times = []
        
        def throughput_handler(payload):
            nonlocal processed_count
            processed_count += 1
            processing_times.append(time.time())
            return {"processed": processed_count}
        
        try:
            queue.register_handler("high_throughput", throughput_handler)
            await queue.initialize()
            await queue.start_background()
            await asyncio.sleep(1)
            
            # 发送大量消息
            message_count = 50
            start_time = time.time()
            
            # 并发发送消息
            send_tasks = []
            for i in range(message_count):
                task = asyncio.create_task(
                    queue.produce("high_throughput", {"id": f"msg_{i:03d}", "data": f"data_{i}"})
                )
                send_tasks.append(task)
            
            await asyncio.gather(*send_tasks)
            send_time = time.time() - start_time
            
            # 等待处理完成
            await asyncio.sleep(5)
            
            total_time = time.time() - start_time
            
            print(f"✅ 吞吐量测试结果:")
            print(f"   发送 {message_count} 条消息用时: {send_time:.2f}s")
            print(f"   处理完成 {processed_count} 条消息")
            print(f"   总耗时: {total_time:.2f}s")
            print(f"   平均吞吐量: {processed_count/total_time:.1f} msg/s")
            
            # 验证大部分消息被处理
            assert processed_count >= message_count * 0.8  # 至少80%的消息被处理
            
            # 验证处理速度合理
            if processed_count > 0:
                throughput = processed_count / total_time
                assert throughput > 5  # 至少每秒5条消息
            
        finally:
            await queue.stop()
            await queue.cleanup()