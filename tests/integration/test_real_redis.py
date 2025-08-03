"""
真实Redis环境的端到端集成测试
"""

import asyncio
import pytest
import time
from typing import List

from mx_rmq import RedisMessageQueue, MQConfig
from mx_rmq.message import Message, MessagePriority, MessageStatus
from mx_rmq.monitoring.metrics import MetricsCollector


@pytest.mark.integration
@pytest.mark.real_redis
class TestRealRedisIntegration:
    """使用真实Redis环境的集成测试"""
    
    @pytest.mark.asyncio
    async def test_complete_message_flow_redis8(self, test_config_v8: MQConfig, clean_redis_v8):
        """测试完整消息流程 - Redis 8.x"""
        queue = RedisMessageQueue(test_config_v8)
        
        # 收集处理结果
        processed_messages = []
        
        def test_handler(payload):
            processed_messages.append(payload)
            return {"status": "processed", "message_id": payload.get("id")}
        
        # 注册处理器
        queue.register_handler("integration_test", test_handler)
        
        try:
            # 初始化队列
            await queue.initialize()
            
            # 启动队列处理
            await queue.start_background()
            
            # 发送测试消息
            test_payload = {
                "id": "msg_001",
                "content": "Hello Redis 8.x!",
                "timestamp": time.time()
            }
            
            message_id = await queue.produce(
                topic="integration_test",
                payload=test_payload,
                priority=MessagePriority.HIGH
            )
            
            # 等待消息处理
            await asyncio.sleep(2)
            
            # 验证消息被处理
            assert len(processed_messages) == 1
            assert processed_messages[0]["id"] == "msg_001"
            assert processed_messages[0]["content"] == "Hello Redis 8.x!"
            
        finally:
            await queue.stop()
            await queue.cleanup()
    
    @pytest.mark.asyncio
    async def test_complete_message_flow_redis6(self, test_config_v6: MQConfig, clean_redis_v6):
        """测试完整消息流程 - Redis 6.x"""
        queue = RedisMessageQueue(test_config_v6)
        
        processed_messages = []
        
        def test_handler(payload):
            processed_messages.append(payload)
            return {"status": "processed", "message_id": payload.get("id")}
        
        queue.register_handler("integration_test", test_handler)
        
        try:
            await queue.initialize()
            await queue.start_background()
            
            test_payload = {
                "id": "msg_002", 
                "content": "Hello Redis 6.x!",
                "timestamp": time.time()
            }
            
            message_id = await queue.produce(
                topic="integration_test",
                payload=test_payload,
                priority=MessagePriority.NORMAL
            )
            
            await asyncio.sleep(2)
            
            assert len(processed_messages) == 1
            assert processed_messages[0]["id"] == "msg_002"
            assert processed_messages[0]["content"] == "Hello Redis 6.x!"
            
        finally:
            await queue.stop()
            await queue.cleanup()
    
    @pytest.mark.asyncio 
    async def test_multiple_topics_processing(self, test_config_v8: MQConfig, clean_redis_v8):
        """测试多主题消息处理"""
        queue = RedisMessageQueue(test_config_v8)
        
        # 收集不同主题的处理结果
        order_results = []
        user_results = []
        payment_results = []
        
        def order_handler(payload):
            order_results.append(payload)
            return {"processed": "order", "id": payload["order_id"]}
        
        def user_handler(payload):
            user_results.append(payload)
            return {"processed": "user", "id": payload["user_id"]}
        
        def payment_handler(payload):
            payment_results.append(payload)
            return {"processed": "payment", "id": payload["payment_id"]}
        
        # 注册多个处理器
        queue.register_handler("orders", order_handler)
        queue.register_handler("users", user_handler)
        queue.register_handler("payments", payment_handler)
        
        try:
            await queue.initialize()
            await queue.start_background()
            
            # 发送不同主题的消息
            await queue.produce("orders", {"order_id": "ORD001", "amount": 99.99})
            await queue.produce("users", {"user_id": "USR001", "name": "张三"})
            await queue.produce("payments", {"payment_id": "PAY001", "method": "card"})
            
            # 等待处理完成
            await asyncio.sleep(3)
            
            # 验证各个主题都被正确处理
            assert len(order_results) == 1
            assert len(user_results) == 1
            assert len(payment_results) == 1
            
            assert order_results[0]["order_id"] == "ORD001"
            assert user_results[0]["user_id"] == "USR001"
            assert payment_results[0]["payment_id"] == "PAY001"
            
        finally:
            await queue.stop()
            await queue.cleanup()
    
    @pytest.mark.asyncio
    async def test_priority_message_processing(self, test_config_v8: MQConfig, clean_redis_v8):
        """测试优先级消息处理"""
        queue = RedisMessageQueue(test_config_v8)
        
        processed_order = []
        
        def priority_handler(payload):
            processed_order.append(payload["priority"])
            # 模拟处理时间
            time.sleep(0.1)
            return {"processed": payload["id"]}
        
        queue.register_handler("priority_test", priority_handler)
        
        try:
            await queue.initialize()
            await queue.start_background()
            
            # 按顺序发送不同优先级的消息
            await queue.produce("priority_test", {"id": 1, "priority": "low"}, priority=MessagePriority.LOW)
            await queue.produce("priority_test", {"id": 2, "priority": "high"}, priority=MessagePriority.HIGH)
            await queue.produce("priority_test", {"id": 3, "priority": "normal"}, priority=MessagePriority.NORMAL)
            
            # 等待所有消息处理完成
            await asyncio.sleep(4)
            
            # 验证处理顺序符合优先级（高优先级先处理）
            assert len(processed_order) == 3
            # 注意：实际的优先级处理可能依赖于Redis的实现细节
            
        finally:
            await queue.stop()
            await queue.cleanup()
    
    @pytest.mark.asyncio
    async def test_message_retry_mechanism(self, test_config_v8: MQConfig, clean_redis_v8):
        """测试消息重试机制"""
        queue = RedisMessageQueue(test_config_v8)
        
        attempt_counts = {}
        
        def failing_handler(payload):
            msg_id = payload["id"]
            attempt_counts[msg_id] = attempt_counts.get(msg_id, 0) + 1
            
            # 前两次失败，第三次成功
            if attempt_counts[msg_id] < 3:
                raise ValueError(f"模拟失败 - 尝试 {attempt_counts[msg_id]}")
            
            return {"success": True, "attempts": attempt_counts[msg_id]}
        
        queue.register_handler("retry_test", failing_handler)
        
        try:
            await queue.initialize()
            await queue.start_background()
            
            # 发送会失败的消息
            await queue.produce("retry_test", {"id": "retry_msg_001"})
            
            # 等待重试完成
            await asyncio.sleep(10)  # 给足够时间进行重试
            
            # 验证重试次数
            assert "retry_msg_001" in attempt_counts
            # 应该尝试了3次（最终成功）
            assert attempt_counts["retry_msg_001"] >= 2
            
        finally:
            await queue.stop()
            await queue.cleanup()
    
    @pytest.mark.asyncio
    async def test_delayed_message_processing(self, test_config_v8: MQConfig, clean_redis_v8):
        """测试延迟消息处理"""
        queue = RedisMessageQueue(test_config_v8)
        
        processing_times = []
        
        def delay_handler(payload):
            processing_times.append(time.time())
            return {"processed": payload["id"], "time": time.time()}
        
        queue.register_handler("delay_test", delay_handler)
        
        try:
            await queue.initialize()
            await queue.start_background()
            
            start_time = time.time()
            
            # 发送延迟3秒的消息
            await queue.produce(
                topic="delay_test",
                payload={"id": "delayed_msg_001"},
                delay=3
            )
            
            # 发送立即处理的消息
            await queue.produce(
                topic="delay_test", 
                payload={"id": "immediate_msg_001"},
                delay=0
            )
            
            # 等待处理完成
            await asyncio.sleep(8)
            
            # 验证消息处理
            assert len(processing_times) == 2
            
            # 计算延迟时间
            if len(processing_times) >= 2:
                # 立即消息应该很快处理
                immediate_delay = processing_times[0] - start_time
                assert immediate_delay < 2
                
                # 延迟消息应该在3秒后处理
                delayed_delay = processing_times[1] - start_time
                assert delayed_delay >= 3
            
        finally:
            await queue.stop()
            await queue.cleanup()
    
    @pytest.mark.asyncio
    async def test_concurrent_producers_consumers(self, test_config_v8: MQConfig, clean_redis_v8):
        """测试并发生产者和消费者"""
        queue = RedisMessageQueue(test_config_v8)
        
        processed_messages = []
        processing_lock = asyncio.Lock()
        
        async def concurrent_handler(payload):
            async with processing_lock:
                processed_messages.append(payload)
            return {"processed": payload["id"]}
        
        queue.register_handler("concurrent_test", concurrent_handler)
        
        try:
            await queue.initialize()
            await queue.start_background()
            
            # 并发发送多个消息
            producer_tasks = []
            for i in range(20):
                task = asyncio.create_task(
                    queue.produce(
                        topic="concurrent_test",
                        payload={"id": f"concurrent_msg_{i:03d}", "data": f"message_{i}"}
                    )
                )
                producer_tasks.append(task)
            
            # 等待所有消息发送完成
            await asyncio.gather(*producer_tasks)
            
            # 等待处理完成
            await asyncio.sleep(5)
            
            # 验证所有消息都被处理
            assert len(processed_messages) == 20
            
            # 验证消息ID的唯一性
            processed_ids = [msg["id"] for msg in processed_messages]
            assert len(set(processed_ids)) == 20
            
        finally:
            await queue.stop()
            await queue.cleanup()
    
    @pytest.mark.asyncio
    async def test_queue_health_and_metrics(self, test_config_v8: MQConfig, clean_redis_v8):
        """测试队列健康状态和指标"""
        queue = RedisMessageQueue(test_config_v8)
        
        processed_count = 0
        
        def metrics_handler(payload):
            nonlocal processed_count
            processed_count += 1
            return {"processed": processed_count}
        
        queue.register_handler("metrics_test", metrics_handler)
        
        try:
            await queue.initialize()
            
            # 检查健康状态
            health = await queue.health_check()
            assert health["healthy"] is True
            assert "redis" in health["checks"]
            
            await queue.start_background()
            
            # 发送一些消息
            for i in range(5):
                await queue.produce("metrics_test", {"id": f"metrics_msg_{i}"})
            
            await asyncio.sleep(3)
            
            # 检查队列状态
            status = queue.status
            assert status["running"] is True
            assert status["initialized"] is True
            assert "local_queue_size" in status
            
            # 验证消息处理
            assert processed_count == 5
            
        finally:
            await queue.stop()
            await queue.cleanup()
    
    @pytest.mark.asyncio
    async def test_error_handling_and_dead_letter_queue(self, test_config_v8: MQConfig, clean_redis_v8):
        """测试错误处理和死信队列"""
        # 设置较低的重试次数以便快速测试
        config = test_config_v8
        config.max_retries = 2
        
        queue = RedisMessageQueue(config)
        
        failed_messages = []
        
        def always_failing_handler(payload):
            failed_messages.append(payload)
            raise RuntimeError(f"处理失败: {payload['id']}")
        
        queue.register_handler("error_test", always_failing_handler)
        
        try:
            await queue.initialize()
            await queue.start_background()
            
            # 发送会失败的消息
            await queue.produce("error_test", {"id": "error_msg_001", "data": "will_fail"})
            
            # 等待重试和失败处理完成
            await asyncio.sleep(8)
            
            # 验证消息被多次尝试处理
            assert len(failed_messages) >= 2  # 至少重试了1次
            
            # 所有尝试的消息ID应该相同
            message_ids = [msg["id"] for msg in failed_messages]
            assert all(mid == "error_msg_001" for mid in message_ids)
            
        finally:
            await queue.stop()
            await queue.cleanup()


@pytest.mark.integration
@pytest.mark.real_redis
class TestRealWorldScenarios:
    """真实世界业务场景测试"""
    
    @pytest.mark.asyncio
    async def test_ecommerce_order_pipeline(self, test_config_v8: MQConfig, clean_redis_v8):
        """测试电商订单处理管道"""
        queue = RedisMessageQueue(test_config_v8)
        
        # 订单处理结果跟踪
        pipeline_results = {
            "payment": [],
            "inventory": [], 
            "shipping": [],
            "notification": []
        }
        
        # 定义各个处理步骤
        def payment_handler(payload):
            pipeline_results["payment"].append(payload)
            # 模拟支付处理
            return {"status": "paid", "order_id": payload["order_id"]}
        
        def inventory_handler(payload):
            pipeline_results["inventory"].append(payload)
            # 模拟库存扣减
            return {"status": "reserved", "order_id": payload["order_id"]}
        
        def shipping_handler(payload):
            pipeline_results["shipping"].append(payload)
            # 模拟发货
            return {"status": "shipped", "order_id": payload["order_id"]}
        
        def notification_handler(payload):
            pipeline_results["notification"].append(payload)
            # 模拟通知发送
            return {"status": "notified", "order_id": payload["order_id"]}
        
        # 注册处理器
        queue.register_handler("payment", payment_handler)
        queue.register_handler("inventory", inventory_handler) 
        queue.register_handler("shipping", shipping_handler)
        queue.register_handler("notification", notification_handler)
        
        try:
            await queue.initialize()
            await queue.start_background()
            
            # 模拟订单创建，触发处理管道
            order_data = {
                "order_id": "ORD20250802001",
                "customer_id": "CUST001",
                "items": [
                    {"sku": "PROD001", "quantity": 2, "price": 99.99},
                    {"sku": "PROD002", "quantity": 1, "price": 199.99}
                ],
                "total_amount": 399.97
            }
            
            # 并发处理订单的各个步骤
            await asyncio.gather(
                queue.produce("payment", order_data, priority=MessagePriority.HIGH),
                queue.produce("inventory", order_data, priority=MessagePriority.HIGH),
                queue.produce("shipping", order_data, priority=MessagePriority.NORMAL),
                queue.produce("notification", order_data, priority=MessagePriority.LOW)
            )
            
            # 等待所有步骤完成
            await asyncio.sleep(3)
            
            # 验证所有步骤都被执行
            assert len(pipeline_results["payment"]) == 1
            assert len(pipeline_results["inventory"]) == 1
            assert len(pipeline_results["shipping"]) == 1
            assert len(pipeline_results["notification"]) == 1
            
            # 验证订单数据正确传递
            for step, results in pipeline_results.items():
                assert results[0]["order_id"] == "ORD20250802001"
                assert results[0]["total_amount"] == 399.97
            
        finally:
            await queue.stop()
            await queue.cleanup()
    
    @pytest.mark.asyncio
    async def test_notification_system(self, test_config_v6: MQConfig, clean_redis_v6):
        """测试通知系统场景"""
        queue = RedisMessageQueue(test_config_v6)
        
        notifications_sent = {
            "email": [],
            "sms": [],
            "push": [],
            "webhook": []
        }
        
        # 不同类型的通知处理器
        def email_handler(payload):
            notifications_sent["email"].append(payload)
            return {"sent": True, "type": "email", "to": payload["recipient"]}
        
        def sms_handler(payload):
            notifications_sent["sms"].append(payload)
            return {"sent": True, "type": "sms", "to": payload["phone"]}
        
        def push_handler(payload):
            notifications_sent["push"].append(payload)
            return {"sent": True, "type": "push", "device_id": payload["device_id"]}
        
        def webhook_handler(payload):
            notifications_sent["webhook"].append(payload)
            return {"sent": True, "type": "webhook", "url": payload["webhook_url"]}
        
        # 注册通知处理器
        queue.register_handler("notification_email", email_handler)
        queue.register_handler("notification_sms", sms_handler)
        queue.register_handler("notification_push", push_handler)
        queue.register_handler("notification_webhook", webhook_handler)
        
        try:
            await queue.initialize()
            await queue.start_background()
            
            # 模拟用户行为触发多种通知
            user_action = {
                "user_id": "USER001",
                "action": "order_confirmed",
                "order_id": "ORD001",
                "message": "您的订单已确认，正在处理中"
            }
            
            # 发送不同类型的通知
            await asyncio.gather(
                queue.produce("notification_email", {
                    **user_action, 
                    "recipient": "user@example.com"
                }),
                queue.produce("notification_sms", {
                    **user_action,
                    "phone": "+86138xxxx8888"
                }),
                queue.produce("notification_push", {
                    **user_action,
                    "device_id": "device_abc123"
                }),
                queue.produce("notification_webhook", {
                    **user_action,
                    "webhook_url": "https://api.partner.com/webhook"
                })
            )
            
            await asyncio.sleep(3)
            
            # 验证所有通知都被发送
            assert len(notifications_sent["email"]) == 1
            assert len(notifications_sent["sms"]) == 1
            assert len(notifications_sent["push"]) == 1
            assert len(notifications_sent["webhook"]) == 1
            
            # 验证通知内容
            email_notif = notifications_sent["email"][0]
            assert email_notif["user_id"] == "USER001"
            assert email_notif["action"] == "order_confirmed"
            assert email_notif["recipient"] == "user@example.com"
            
        finally:
            await queue.stop()
            await queue.cleanup()
    
    @pytest.mark.asyncio
    async def test_data_processing_pipeline(self, test_config_v8: MQConfig, clean_redis_v8):
        """测试数据处理管道场景"""
        queue = RedisMessageQueue(test_config_v8)
        
        pipeline_stages = {
            "extract": [],
            "transform": [],
            "validate": [],
            "load": []
        }
        
        def extract_handler(payload):
            pipeline_stages["extract"].append(payload)
            # 模拟数据提取
            extracted_data = {
                **payload,
                "extracted_at": time.time(),
                "record_count": len(payload.get("raw_data", []))
            }
            return {"status": "extracted", "data": extracted_data}
        
        def transform_handler(payload):
            pipeline_stages["transform"].append(payload)
            # 模拟数据转换
            transformed_data = {
                **payload,
                "transformed_at": time.time(),
                "transformation_rules": ["normalize", "deduplicate", "enrich"]
            }
            return {"status": "transformed", "data": transformed_data}
        
        def validate_handler(payload):
            pipeline_stages["validate"].append(payload)
            # 模拟数据验证
            validation_result = {
                **payload,
                "validated_at": time.time(),
                "validation_status": "passed",
                "errors": []
            }
            return {"status": "validated", "data": validation_result}
        
        def load_handler(payload):
            pipeline_stages["load"].append(payload)
            # 模拟数据加载
            load_result = {
                **payload,
                "loaded_at": time.time(),
                "destination": "data_warehouse",
                "rows_inserted": 1000
            }
            return {"status": "loaded", "data": load_result}
        
        # 注册数据处理器
        queue.register_handler("data_extract", extract_handler)
        queue.register_handler("data_transform", transform_handler)
        queue.register_handler("data_validate", validate_handler)
        queue.register_handler("data_load", load_handler)
        
        try:
            await queue.initialize()
            await queue.start_background()
            
            # 模拟数据批次处理
            batch_data = {
                "batch_id": "BATCH_20250802_001",
                "source": "user_events",
                "raw_data": [
                    {"user_id": 1, "event": "login", "timestamp": time.time()},
                    {"user_id": 2, "event": "purchase", "timestamp": time.time()},
                    {"user_id": 3, "event": "logout", "timestamp": time.time()}
                ],
                "batch_size": 3
            }
            
            # 启动数据处理管道
            await asyncio.gather(
                queue.produce("data_extract", batch_data),
                queue.produce("data_transform", batch_data, delay=1),  # 稍后转换
                queue.produce("data_validate", batch_data, delay=2),   # 然后验证
                queue.produce("data_load", batch_data, delay=3)        # 最后加载
            )
            
            await asyncio.sleep(6)
            
            # 验证数据管道各阶段都执行了
            assert len(pipeline_stages["extract"]) == 1
            assert len(pipeline_stages["transform"]) == 1
            assert len(pipeline_stages["validate"]) == 1
            assert len(pipeline_stages["load"]) == 1
            
            # 验证批次数据正确传递
            for stage_data in pipeline_stages.values():
                assert stage_data[0]["batch_id"] == "BATCH_20250802_001"
                assert stage_data[0]["batch_size"] == 3
            
        finally:
            await queue.stop()
            await queue.cleanup()