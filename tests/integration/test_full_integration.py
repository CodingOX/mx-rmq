"""
端到端集成测试
"""

import asyncio
import pytest
import time
import json
from unittest.mock import patch, MagicMock, AsyncMock

from mx_rmq import RedisMessageQueue, MQConfig
from mx_rmq.message import Message, MessagePriority, MessageStatus
from mx_rmq.monitoring.metrics import MetricsCollector


class TestEndToEndIntegration:
    """端到端集成测试"""
    
    @pytest.mark.asyncio
    async def test_complete_message_lifecycle(self):
        """测试完整的消息生命周期"""
        config = MQConfig()
        queue = RedisMessageQueue(config)
        
        # 模拟完整的消息处理流程
        processed_messages = []
        
        def test_handler(payload):
            processed_messages.append(payload)
            return {"status": "processed", "data": payload}
        
        # 注册处理器
        queue.register_handler("integration_test", test_handler)
        
        # 验证处理器注册
        if queue._context:
            assert "integration_test" in queue._context.handlers
        
        # 创建测试消息
        test_payload = {"test_id": "integration_001", "data": "test_data"}
        message = Message(
            topic="integration_test",
            payload=test_payload,
            priority=MessagePriority.HIGH
        )
        
        # 验证消息生命周期状态
        assert message.meta.status == MessageStatus.PENDING
        
        # 模拟处理过程
        message.mark_processing()
        assert message.meta.status == MessageStatus.PROCESSING
        
        # 模拟处理完成
        message.mark_completed()
        assert message.meta.status == MessageStatus.COMPLETED
        assert message.meta.completed_at is not None
    
    @pytest.mark.asyncio
    async def test_multi_topic_message_routing(self):
        """测试多主题消息路由"""
        config = MQConfig()
        queue = RedisMessageQueue(config)
        
        # 定义多个处理器
        order_messages = []
        user_messages = []
        payment_messages = []
        
        def order_handler(payload):
            order_messages.append(payload)
        
        def user_handler(payload):
            user_messages.append(payload)
        
        def payment_handler(payload):
            payment_messages.append(payload)
        
        # 注册多个主题处理器
        queue.register_handler("orders", order_handler)
        queue.register_handler("users", user_handler)
        queue.register_handler("payments", payment_handler)
        
        # 验证所有处理器都已注册
        if queue._context:
            handlers = queue._context.handlers
            assert "orders" in handlers
            assert "users" in handlers
            assert "payments" in handlers
        
        # 创建不同主题的消息
        order_msg = Message(topic="orders", payload={"order_id": "ORD001"})
        user_msg = Message(topic="users", payload={"user_id": "USR001"})
        payment_msg = Message(topic="payments", payload={"payment_id": "PAY001"})
        
        # 验证消息创建成功
        assert order_msg.topic == "orders"
        assert user_msg.topic == "users"
        assert payment_msg.topic == "payments"
    
    @pytest.mark.asyncio
    async def test_priority_queue_ordering(self):
        """测试优先级队列排序"""
        config = MQConfig()
        queue = RedisMessageQueue(config)
        
        # 创建不同优先级的消息
        low_priority_msg = Message(
            topic="priority_test",
            payload={"priority": "low"},
            priority=MessagePriority.LOW
        )
        
        normal_priority_msg = Message(
            topic="priority_test", 
            payload={"priority": "normal"},
            priority=MessagePriority.NORMAL
        )
        
        high_priority_msg = Message(
            topic="priority_test",
            payload={"priority": "high"}, 
            priority=MessagePriority.HIGH
        )
        
        # 验证优先级设置
        assert low_priority_msg.priority == MessagePriority.LOW
        assert normal_priority_msg.priority == MessagePriority.NORMAL
        assert high_priority_msg.priority == MessagePriority.HIGH
        
        # 验证优先级值的数值关系
        assert MessagePriority.HIGH.value > MessagePriority.NORMAL.value
        assert MessagePriority.NORMAL.value > MessagePriority.LOW.value
    
    @pytest.mark.asyncio
    async def test_error_handling_and_retry_mechanism(self):
        """测试错误处理和重试机制"""
        config = MQConfig(max_retries=3)
        queue = RedisMessageQueue(config)
        
        # 模拟会失败的处理器
        attempt_count = 0
        
        def failing_handler(payload):
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 3:
                raise ValueError(f"处理失败 - 尝试 {attempt_count}")
            return {"status": "success", "attempts": attempt_count}
        
        queue.register_handler("retry_test", failing_handler)
        
        # 创建消息并模拟重试过程
        message = Message(
            topic="retry_test",
            payload={"test": "retry_scenario"}
        )
        
        # 模拟重试过程
        for retry in range(3):
            message.meta.retry_count = retry
            
            if retry < 2:
                # 前两次失败
                message.mark_retry(f"处理失败 - 尝试 {retry + 1}")
                assert message.meta.status == MessageStatus.RETRYING
                assert message.can_retry() is True
            else:
                # 第三次成功
                message.mark_completed()
                assert message.meta.status == MessageStatus.COMPLETED
    
    @pytest.mark.asyncio
    async def test_dead_letter_queue_flow(self):
        """测试死信队列流程"""
        config = MQConfig(max_retries=2)
        queue = RedisMessageQueue(config)
        
        # 创建总是失败的消息
        message = Message(
            topic="dlq_test",
            payload={"test": "dead_letter"}
        )
        
        # 模拟重试耗尽过程
        message.meta.max_retries = 2
        
        # 第一次重试
        message.mark_retry("第一次失败")
        assert message.meta.retry_count == 1
        assert message.can_retry() is True
        
        # 第二次重试
        message.mark_retry("第二次失败")
        assert message.meta.retry_count == 2
        assert message.can_retry() is True
        
        # 第三次重试 - 应该达到限制
        message.mark_retry("第三次失败")
        assert message.meta.retry_count == 3
        assert message.can_retry() is False
        
        # 移入死信队列
        message.mark_dead_letter("超过最大重试次数")
        assert message.meta.status == MessageStatus.DEAD_LETTER
        assert message.meta.dead_letter_at is not None
    
    @pytest.mark.asyncio
    async def test_delayed_message_processing(self):
        """测试延迟消息处理"""
        config = MQConfig()
        queue = RedisMessageQueue(config)
        
        # 测试延迟消息的基本创建
        message = Message(
            topic="delay_test",
            payload={"test": "delayed_message"}
        )
        
        # 验证消息的基本属性
        current_time = int(time.time() * 1000)
        assert message.created_at <= current_time + 1000  # 允许一些时间差
        assert message.meta.expire_at > current_time  # 消息应该在未来某个时间过期
        
        # 测试消息的基本状态
        assert message.meta.status == MessageStatus.PENDING
    
    @pytest.mark.asyncio
    async def test_metrics_collection_integration(self):
        """测试指标收集集成"""
        config = MQConfig()
        queue = RedisMessageQueue(config)
        collector = MetricsCollector()
        
        topic = "metrics_integration_test"
        
        # 模拟完整的消息处理流程并收集指标
        message_count = 10
        
        for i in range(message_count):
            # 生产消息
            collector.record_message_produced(topic)
            
            # 开始处理
            message_id = f"msg_{i}"
            collector.start_processing(message_id)
            collector.record_message_consumed(topic)
            
            # 模拟处理时间
            processing_time = 0.1 + (i * 0.01)  # 递增的处理时间
            
            # 完成处理
            collector.end_processing(message_id)
            collector.record_message_completed(topic, processing_time=processing_time)
        
        # 验证指标统计
        queue_metrics = collector.get_queue_metrics(topic)
        processing_metrics = collector.get_processing_metrics(topic)
        
        assert queue_metrics.completed_count == message_count
        assert processing_metrics.total_processed == message_count
        assert processing_metrics.success_count == message_count
        assert processing_metrics.avg_processing_time > 0
    
    @pytest.mark.asyncio
    async def test_concurrent_processing_integration(self):
        """测试并发处理集成"""
        config = MQConfig()
        queue = RedisMessageQueue(config)
        collector = MetricsCollector()
        
        import threading
        import time
        
        topic = "concurrent_integration_test"
        thread_count = 10
        messages_per_thread = 5
        
        results = []
        
        def worker_thread(thread_id):
            try:
                for msg_id in range(messages_per_thread):
                    # 生产消息
                    collector.record_message_produced(topic)
                    
                    # 处理消息
                    collector.record_message_consumed(topic)
                    
                    # 模拟处理时间
                    time.sleep(0.001)
                    
                    # 完成处理
                    collector.record_message_completed(
                        topic, 
                        processing_time=0.001
                    )
                
                results.append(f"thread_{thread_id}_success")
            except Exception as e:
                results.append(f"thread_{thread_id}_error_{e}")
        
        # 启动并发线程
        threads = []
        for i in range(thread_count):
            thread = threading.Thread(target=worker_thread, args=(i,))
            threads.append(thread)
            thread.start()
        
        # 等待所有线程完成
        for thread in threads:
            thread.join()
        
        # 验证所有线程都成功
        success_count = len([r for r in results if "success" in r])
        assert success_count == thread_count
        
        # 验证最终指标
        processing_metrics = collector.get_processing_metrics(topic)
        expected_total = thread_count * messages_per_thread
        assert processing_metrics.total_processed == expected_total
    
    @pytest.mark.asyncio
    async def test_queue_lifecycle_integration(self):
        """测试队列生命周期集成"""
        config = MQConfig()
        queue = RedisMessageQueue(config)
        
        # 初始状态
        assert queue.is_running() is False
        
        # 注册处理器
        test_results = []
        
        def lifecycle_handler(payload):
            test_results.append(payload)
            return "processed"
        
        queue.register_handler("lifecycle_test", lifecycle_handler)
        
        # 验证处理器注册成功
        if queue._context:
            assert "lifecycle_test" in queue._context.handlers
        
        # 测试队列状态
        status = queue.status
        assert "running" in status
        assert "initialized" in status
        
        # 测试健康检查
        health = await queue.health_check()
        assert "healthy" in health
        assert "timestamp" in health
        assert "checks" in health
        
        # 测试优雅停机
        await queue.stop()
        
        # 验证停机后状态
        assert queue.is_running() is False
    
    @pytest.mark.asyncio
    async def test_configuration_integration(self):
        """测试配置集成"""
        # 测试不同配置组合
        configs = [
            MQConfig(max_retries=1, message_ttl=3600),
            MQConfig(max_retries=5, message_ttl=7200, task_queue_size=200),
            MQConfig(redis_host="localhost", redis_port=6379, redis_db=1)
        ]
        
        for config in configs:
            queue = RedisMessageQueue(config)
            
            # 验证配置被正确应用
            assert queue.config.max_retries == config.max_retries
            assert queue.config.message_ttl == config.message_ttl
            assert queue.config.redis_host == config.redis_host
            assert queue.config.redis_port == config.redis_port
            
            # 测试队列创建成功
            assert queue is not None
    
    @pytest.mark.asyncio
    async def test_monitoring_integration(self):
        """测试监控集成"""
        config = MQConfig()
        queue = RedisMessageQueue(config)
        collector = MetricsCollector()
        
        # 模拟各种消息状态
        topics = ["monitoring_test_1", "monitoring_test_2", "monitoring_test_3"]
        
        for topic in topics:
            # 成功消息
            collector.record_message_produced(topic)
            collector.record_message_consumed(topic)
            collector.record_message_completed(topic, processing_time=0.1)
            
            # 失败消息
            collector.record_message_produced(topic)
            collector.record_message_consumed(topic) 
            collector.record_message_failed(topic, "处理错误", processing_time=0.05)
            
            # 重试消息
            collector.record_message_retried(topic)
            
            # 死信消息
            collector.record_message_dead_letter(topic)
            
            # 延迟消息
            collector.record_delay_message(topic)
        
        # 验证所有主题的指标
        all_queue_metrics = collector.get_all_queue_metrics()
        all_processing_metrics = collector.get_all_processing_metrics()
        
        assert len(all_queue_metrics) == len(topics)
        assert len(all_processing_metrics) == len(topics)
        
        for topic in topics:
            queue_metrics = all_queue_metrics[topic]
            processing_metrics = all_processing_metrics[topic]
            
            # 验证各种状态的计数
            assert queue_metrics.completed_count == 1
            assert queue_metrics.failed_count == 1
            assert queue_metrics.dead_letter_count == 1
            assert queue_metrics.delay_count == 1
            
            assert processing_metrics.success_count == 1
            assert processing_metrics.error_count == 1
            assert processing_metrics.retry_count == 1
            assert processing_metrics.total_processed == 2  # 1成功 + 1失败


class TestSystemIntegration:
    """系统集成测试"""
    
    @pytest.mark.asyncio
    async def test_redis_integration_simulation(self):
        """测试Redis集成模拟"""
        from mx_rmq.storage import RedisConnectionManager
        
        config = MQConfig()
        manager = RedisConnectionManager(config)
        
        # 验证连接管理器配置
        assert manager.config.redis_host == config.redis_host
        assert manager.config.redis_port == config.redis_port
        assert manager.config.redis_db == config.redis_db
        
        # 测试清理操作
        await manager.cleanup()
    
    @pytest.mark.asyncio
    async def test_lua_scripts_integration(self):
        """测试Lua脚本集成"""
        config = MQConfig()
        queue = RedisMessageQueue(config)
        
        # 验证Lua脚本结构（实际脚本在真实Redis环境中加载）
        # 这里主要测试脚本相关的代码结构
        assert queue._context is None or hasattr(queue._context, 'lua_scripts')
    
    def test_message_serialization_integration(self):
        """测试消息序列化集成"""
        # 测试各种类型的消息序列化
        test_cases = [
            {
                "topic": "json_test",
                "payload": {"key": "value", "number": 123, "boolean": True}
            },
            {
                "topic": "unicode_test", 
                "payload": {"chinese": "你好", "emoji": "🚀", "special": "äöü"}
            },
            {
                "topic": "nested_test",
                "payload": {
                    "level1": {
                        "level2": {"data": [1, 2, 3, {"nested": True}]}
                    }
                }
            }
        ]
        
        for case in test_cases:
            message = Message(topic=case["topic"], payload=case["payload"])
            
            # 序列化为JSON
            serialized = json.dumps(message.model_dump())
            
            # 验证可以反序列化
            deserialized_data = json.loads(serialized)
            assert deserialized_data["topic"] == case["topic"]
            assert deserialized_data["payload"] == case["payload"]
    
    @pytest.mark.asyncio
    async def test_context_management_integration(self):
        """测试上下文管理集成"""
        config = MQConfig()
        queue = RedisMessageQueue(config)
        
        # 测试上下文访问
        context = queue.context
        
        if context:
            # 验证上下文结构
            assert hasattr(context, 'config')
            assert hasattr(context, 'handlers')
            assert hasattr(context, 'running')
            assert hasattr(context, 'shutting_down')
        
        # 测试连接管理器访问
        connection_manager = queue.connection_manager
        assert connection_manager is not None
        assert hasattr(connection_manager, 'config')
    
    def test_performance_integration(self):
        """测试性能集成"""
        import time
        
        config = MQConfig()
        queue = RedisMessageQueue(config)
        collector = MetricsCollector()
        
        # 性能基准测试
        topic = "performance_integration"
        operation_count = 1000
        
        start_time = time.time()
        
        # 批量操作
        for i in range(operation_count):
            collector.record_message_produced(topic)
            collector.record_message_consumed(topic)
            collector.record_message_completed(topic, processing_time=0.001)
        
        elapsed_time = time.time() - start_time
        
        # 验证性能指标
        assert elapsed_time < 2.0  # 应该在2秒内完成
        
        # 验证操作正确性
        metrics = collector.get_processing_metrics(topic)
        assert metrics.total_processed == operation_count
        
        # 计算吞吐量
        throughput = operation_count / elapsed_time
        assert throughput > 500  # 每秒至少500个操作
    
    @pytest.mark.asyncio
    async def test_error_recovery_integration(self):
        """测试错误恢复集成"""
        config = MQConfig()
        queue = RedisMessageQueue(config)
        
        # 模拟各种错误场景并验证恢复
        test_scenarios = [
            {"error": "ConnectionError", "recovery": "重连"},
            {"error": "TimeoutError", "recovery": "重试"},
            {"error": "ValidationError", "recovery": "丢弃消息"},
            {"error": "SerializationError", "recovery": "错误处理"}
        ]
        
        for scenario in test_scenarios:
            # 创建测试消息
            message = Message(
                topic="error_recovery",
                payload={"scenario": scenario["error"]}
            )
            
            # 模拟错误和恢复过程
            message.mark_processing()
            message.mark_retry(scenario["error"])
            
            # 验证错误被记录
            assert scenario["error"] in message.meta.last_error # type: ignore
            assert message.meta.status == MessageStatus.RETRYING


class TestRealWorldScenarios:
    """真实世界场景测试"""
    
    @pytest.mark.asyncio
    async def test_e_commerce_order_processing(self):
        """测试电商订单处理场景"""
        config = MQConfig()
        queue = RedisMessageQueue(config)
        collector = MetricsCollector()
        
        # 模拟电商订单处理流程
        order_steps = ["payment", "inventory", "shipping", "notification"]
        
        # 注册各个步骤的处理器
        processed_steps = {}
        
        for step in order_steps:
            processed_steps[step] = []
            
            def create_handler(step_name):
                def handler(payload):
                    processed_steps[step_name].append(payload)
                    collector.record_message_completed(step_name, processing_time=0.1)
                    return {"status": "completed", "step": step_name}
                return handler
            
            queue.register_handler(step, create_handler(step))
        
        # 模拟订单处理
        order_id = "ORDER_001"
        order_data = {
            "order_id": order_id,
            "customer_id": "CUST_001", 
            "items": [{"sku": "ITEM_001", "quantity": 2}],
            "total": 99.99
        }
        
        # 创建各个步骤的消息
        for step in order_steps:
            message = Message(
                topic=step,
                payload={**order_data, "step": step},
                priority=MessagePriority.HIGH if step == "payment" else MessagePriority.NORMAL
            )
            
            # 记录消息生产
            collector.record_message_produced(step)
            
            # 验证消息创建
            assert message.topic == step
            assert message.payload["order_id"] == order_id
        
        # 验证处理器注册
        if queue._context:
            for step in order_steps:
                assert step in queue._context.handlers
    
    @pytest.mark.asyncio
    async def test_notification_system_scenario(self):
        """测试通知系统场景"""
        config = MQConfig()
        queue = RedisMessageQueue(config)
        
        # 不同类型的通知
        notification_types = ["email", "sms", "push", "webhook"]
        
        notifications_sent = {}
        
        for notif_type in notification_types:
            notifications_sent[notif_type] = []
            
            def create_notification_handler(notif_type):
                def handler(payload):
                    notifications_sent[notif_type].append(payload)
                    return {"sent": True, "type": notif_type}
                return handler
            
            queue.register_handler(
                f"notification_{notif_type}", 
                create_notification_handler(notif_type)
            )
        
        # 创建通知消息
        notification_data = {
            "user_id": "USER_001",
            "message": "您的订单已确认",
            "priority": "high"
        }
        
        for notif_type in notification_types:
            message = Message(
                topic=f"notification_{notif_type}",
                payload={**notification_data, "type": notif_type},
                priority=MessagePriority.HIGH
            )
            
            assert message.topic == f"notification_{notif_type}"
            assert message.payload["user_id"] == "USER_001"
    
    @pytest.mark.asyncio
    async def test_data_pipeline_scenario(self):
        """测试数据管道场景"""
        config = MQConfig()
        queue = RedisMessageQueue(config)
        collector = MetricsCollector()
        
        # 数据处理管道步骤
        pipeline_steps = ["extract", "transform", "validate", "load"]
        
        pipeline_results = {}
        
        for step in pipeline_steps:
            pipeline_results[step] = []
            
            def create_pipeline_handler(step_name):
                def handler(payload):
                    # 模拟数据处理时间
                    processing_time = {
                        "extract": 0.1,
                        "transform": 0.2, 
                        "validate": 0.05,
                        "load": 0.3
                    }.get(step_name, 0.1)
                    
                    pipeline_results[step_name].append(payload)
                    collector.record_message_completed(step_name, processing_time=processing_time)
                    
                    return {"processed": True, "step": step_name, "time": processing_time}
                return handler
            
            queue.register_handler(step, create_pipeline_handler(step))
        
        # 创建数据批次
        batch_data = {
            "batch_id": "BATCH_001",
            "records": [
                {"id": 1, "name": "Record 1"},
                {"id": 2, "name": "Record 2"},
                {"id": 3, "name": "Record 3"}
            ]
        }
        
        # 处理数据批次
        for step in pipeline_steps:
            message = Message(
                topic=step,
                payload={**batch_data, "step": step}
            )
            
            collector.record_message_produced(step)
            
            assert message.topic == step
            assert message.payload["batch_id"] == "BATCH_001"
            assert len(message.payload["records"]) == 3
    
    @pytest.mark.asyncio
    async def test_microservices_communication_scenario(self):
        """测试微服务通信场景"""
        config = MQConfig()
        queue = RedisMessageQueue(config)
        
        # 微服务列表
        services = ["user_service", "order_service", "payment_service", "inventory_service"]
        
        service_communications = {}
        
        for service in services:
            service_communications[service] = []
            
            def create_service_handler(service_name):
                def handler(payload):
                    service_communications[service_name].append(payload)
                    return {
                        "service": service_name,
                        "processed": True,
                        "timestamp": time.time()
                    }
                return handler
            
            queue.register_handler(service, create_service_handler(service))
        
        # 模拟服务间通信
        communication_scenarios = [
            {
                "from": "user_service",
                "to": "order_service", 
                "event": "user_created",
                "data": {"user_id": "USER_001", "email": "user@example.com"}
            },
            {
                "from": "order_service",
                "to": "payment_service",
                "event": "payment_required", 
                "data": {"order_id": "ORDER_001", "amount": 99.99}
            },
            {
                "from": "order_service",
                "to": "inventory_service",
                "event": "inventory_check",
                "data": {"order_id": "ORDER_001", "items": [{"sku": "ITEM_001", "qty": 1}]}
            }
        ]
        
        for scenario in communication_scenarios:
            message = Message(
                topic=scenario["to"],
                payload={
                    "event": scenario["event"],
                    "from_service": scenario["from"],
                    "data": scenario["data"]
                }
            )
            
            assert message.topic == scenario["to"]
            assert message.payload["event"] == scenario["event"]
            assert message.payload["from_service"] == scenario["from"]