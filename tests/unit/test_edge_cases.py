"""
边界条件和异常场景测试
"""

import asyncio
import pytest
import time
from unittest.mock import patch, MagicMock, AsyncMock

from mx_rmq import RedisMessageQueue, MQConfig
from mx_rmq.message import Message, MessagePriority, MessageStatus
from mx_rmq.monitoring.metrics import MetricsCollector


class TestBoundaryConditions:
    """边界条件测试"""
    
    def test_empty_topic_handling(self):
        """测试空主题处理"""
        with pytest.raises(ValueError):
            Message(topic="", payload={"test": "data"})
    
    def test_none_payload_handling(self):
        """测试None负载处理"""
        with pytest.raises(ValueError):
            Message(topic="test", payload=None) # type: ignore
    
    def test_empty_payload_handling(self):
        """测试空负载处理"""
        # 空字典应该是允许的
        message = Message(topic="test", payload={})
        assert message.payload == {}
    
    def test_large_payload_handling(self):
        """测试大负载处理"""
        # 创建大负载
        large_data = "x" * 1000000  # 1MB数据
        large_payload = {"large_data": large_data}
        
        message = Message(topic="large_test", payload=large_payload)
        assert len(message.payload["large_data"]) == 1000000
    
    def test_unicode_payload_handling(self):
        """测试Unicode负载处理"""
        unicode_payload = {
            "chinese": "你好世界",
            "japanese": "こんにちは",
            "emoji": "🚀🎉✨",
            "special": "äöü ñ"
        }
        
        message = Message(topic="unicode_test", payload=unicode_payload)
        assert message.payload["chinese"] == "你好世界"
        assert message.payload["emoji"] == "🚀🎉✨"
    
    def test_nested_payload_handling(self):
        """测试嵌套负载处理"""
        nested_payload = {
            "level1": {
                "level2": {
                    "level3": {
                        "data": "deep_value",
                        "array": [1, 2, 3, {"nested_in_array": True}]
                    }
                }
            }
        }
        
        message = Message(topic="nested_test", payload=nested_payload)
        assert message.payload["level1"]["level2"]["level3"]["data"] == "deep_value"
    
    def test_zero_ttl_handling(self):
        """测试零TTL处理"""
        with pytest.raises(ValueError):
            MQConfig(message_ttl=0)
    
    def test_negative_retry_count_handling(self):
        """测试负重试次数处理"""
        with pytest.raises(ValueError):
            MQConfig(max_retries=-1)
    
    def test_maximum_retry_count_handling(self):
        """测试最大重试次数处理"""
        message = Message(topic="max_retry_test", payload={"test": "data"})
        
        # 设置到最大重试次数
        message.meta.max_retries = 10
        message.meta.retry_count = 10
        
        # 不应该能够再重试
        assert message.can_retry() is False
    
    def test_zero_delay_message_handling(self):
        """测试零延迟消息处理"""
        message = Message(
            topic="zero_delay_test",
            payload={"test": "data"}
        )
        
        # 新创建的消息应该是待处理状态
        assert message.meta.status == MessageStatus.PENDING
    
    def test_maximum_delay_message_handling(self):
        """测试最大延迟消息处理"""
        # 测试非常大的延迟值
        large_delay = 365 * 24 * 3600  # 一年
        message = Message(
            topic="max_delay_test", 
            payload={"test": "data"}
        )
        
        # 测试消息的过期时间设置
        future_time = int((time.time() + large_delay) * 1000)
        message.meta.expire_at = future_time
        
        assert message.meta.expire_at > int(time.time() * 1000)
    
    def test_concurrent_message_processing(self):
        """测试并发消息处理"""
        from mx_rmq.monitoring.metrics import MetricsCollector
        import threading
        
        collector = MetricsCollector()
        topic = "concurrent_boundary_test"
        thread_count = 50
        messages_per_thread = 20
        
        results = []
        
        def worker_thread():
            try:
                for i in range(messages_per_thread):
                    collector.record_message_produced(topic)
                    collector.record_message_consumed(topic)
                    collector.record_message_completed(topic, processing_time=0.001)
                results.append("success")
            except Exception as e:
                results.append(f"error: {e}")
        
        # 启动大量并发线程
        threads = []
        for _ in range(thread_count):
            thread = threading.Thread(target=worker_thread)
            threads.append(thread)
            thread.start()
        
        # 等待所有线程完成
        for thread in threads:
            thread.join()
        
        # 验证所有线程都成功
        assert len(results) == thread_count
        assert all(result == "success" for result in results)
        
        # 验证最终计数正确
        metrics = collector.get_processing_metrics(topic)
        expected_total = thread_count * messages_per_thread
        assert metrics.total_processed == expected_total


class TestExceptionScenarios:
    """异常场景测试"""
    
    @pytest.mark.asyncio
    async def test_redis_connection_loss_during_operation(self):
        """测试操作过程中Redis连接丢失"""
        config = MQConfig()
        queue = RedisMessageQueue(config)
        
        # 模拟连接丢失
        with patch.object(queue, '_connection_manager') as mock_cm:
            mock_cm.cleanup.side_effect = ConnectionError("连接丢失")
            
            # 应该处理连接错误而不崩溃
            await queue.cleanup()
    
    def test_handler_registration_with_invalid_callable(self):
        """测试注册无效处理器"""
        config = MQConfig()
        queue = RedisMessageQueue(config)
        
        # 尝试注册非可调用对象
        with pytest.raises(TypeError):
            queue.register_handler("test_topic", "not_callable") # type: ignore
    
    def test_message_status_invalid_transition(self):
        """测试无效的消息状态转换"""
        message = Message(topic="status_test", payload={"test": "data"})
        
        # 消息应该按正确顺序转换状态
        assert message.meta.status == MessageStatus.PENDING
        
        # 直接标记为完成（跳过处理状态）应该可以
        message.mark_completed()
        assert message.meta.status == MessageStatus.COMPLETED
    
    def test_message_expiration_edge_cases(self):
        """测试消息过期边界情况"""
        message = Message(topic="expiry_test", payload={"test": "data"})
        
        # 测试刚好过期的消息
        current_time_ms = int(time.time() * 1000)
        message.meta.expire_at = current_time_ms - 1  # 1ms前过期
        
        assert message.is_expired() is True
        
        # 测试刚好未过期的消息
        message.meta.expire_at = current_time_ms + 1  # 1ms后过期
        assert message.is_expired() is False
    
    def test_metrics_overflow_handling(self):
        """测试指标溢出处理"""
        collector = MetricsCollector()
        topic = "overflow_test"
        
        # 添加大量处理时间记录
        large_count = 10000
        for i in range(large_count):
            collector.record_message_completed(topic, processing_time=float(i))
        
        # 验证内存使用受限
        processing_times = collector._processing_times[topic]
        assert len(processing_times) <= 1000  # 应该有上限
        
        # 验证统计仍然正确
        metrics = collector.get_processing_metrics(topic)
        assert metrics.total_processed == large_count
    
    def test_queue_shutdown_during_message_processing(self):
        """测试消息处理过程中的队列关闭"""
        config = MQConfig()
        queue = RedisMessageQueue(config)
        
        # 模拟处理过程中的关闭
        with patch.object(queue, 'is_running', side_effect=[True, False]):
            # 第一次调用返回True，第二次返回False（模拟关闭）
            assert queue.is_running() is True
            assert queue.is_running() is False
    
    @pytest.mark.asyncio 
    async def test_async_handler_exception_propagation(self):
        """测试异步处理器异常传播"""
        config = MQConfig()
        queue = RedisMessageQueue(config)
        
        async def failing_async_handler(payload):
            raise RuntimeError("异步处理失败")
        
        # 注册异步处理器
        queue.register_handler("async_error_topic", failing_async_handler)
        
        # 验证处理器已注册（具体异常处理在实际运行时测试）
        if queue._context:
            assert "async_error_topic" in queue._context.handlers
    
    def test_memory_pressure_scenarios(self):
        """测试内存压力场景"""
        collector = MetricsCollector()
        
        # 创建大量topic和指标
        topic_count = 1000
        for i in range(topic_count):
            topic = f"memory_test_{i}"
            collector.record_message_produced(topic)
            collector.record_message_consumed(topic)
            collector.record_message_completed(topic, processing_time=0.1)
        
        # 验证所有topic都被记录
        all_metrics = collector.get_all_processing_metrics()
        assert len(all_metrics) == topic_count
    
    def test_rapid_queue_start_stop_cycles(self):
        """测试快速启停循环"""
        config = MQConfig()
        queue = RedisMessageQueue(config)
        
        # 快速多次停止（应该安全处理）
        async def rapid_stop_test():
            for _ in range(10):
                await queue.stop()
        
        # 应该不抛出异常
        asyncio.run(rapid_stop_test())
    
    def test_invalid_redis_configuration(self):
        """测试无效Redis配置"""
        # 测试无效端口
        with pytest.raises(ValueError):
            MQConfig(redis_port=-1)
        
        with pytest.raises(ValueError):
            MQConfig(redis_port=100000)  # 端口超出范围
    
    def test_topic_name_edge_cases(self):
        """测试主题名边界情况"""
        # 测试非常长的主题名
        long_topic = "x" * 1000
        message = Message(topic=long_topic, payload={"test": "data"})
        assert message.topic == long_topic
        
        # 测试特殊字符主题名
        special_topic = "test:topic.with-special_chars@123"
        message = Message(topic=special_topic, payload={"test": "data"})
        assert message.topic == special_topic
    
    def test_processing_time_edge_cases(self):
        """测试处理时间边界情况"""
        collector = MetricsCollector()
        topic = "processing_time_test"
        
        # 测试零处理时间
        collector.record_message_completed(topic, processing_time=0.0)
        
        # 测试非常小的处理时间
        collector.record_message_completed(topic, processing_time=0.000001)
        
        # 测试很大的处理时间
        collector.record_message_completed(topic, processing_time=3600.0)  # 1小时
        
        metrics = collector.get_processing_metrics(topic)
        assert metrics.total_processed == 3
        assert metrics.min_processing_time == 0.0
        assert metrics.max_processing_time == 3600.0


class TestResourceExhaustion:
    """资源耗尽测试"""
    
    def test_memory_limited_metrics_collection(self):
        """测试内存受限的指标收集"""
        collector = MetricsCollector()
        topic = "memory_limit_test"
        
        # 模拟大量数据收集
        data_points = 50000
        for i in range(data_points):
            collector.record_message_completed(topic, processing_time=float(i % 100))
        
        # 验证内存使用被控制
        processing_times = collector._processing_times[topic]
        assert len(processing_times) <= 1000
        
        # 但总计数应该是准确的
        metrics = collector.get_processing_metrics(topic)
        assert metrics.total_processed == data_points
    
    def test_high_frequency_operations(self):
        """测试高频操作"""
        collector = MetricsCollector()
        topic = "high_freq_test"
        
        import time
        start_time = time.time()
        
        # 高频操作
        operation_count = 10000
        for i in range(operation_count):
            collector.record_message_produced(topic)
            collector.record_message_consumed(topic)
            collector.record_message_completed(topic, processing_time=0.001)
        
        elapsed_time = time.time() - start_time
        
        # 验证性能（应该在合理时间内完成）
        assert elapsed_time < 5.0  # 5秒内完成
        
        # 验证结果正确性
        metrics = collector.get_processing_metrics(topic)
        assert metrics.total_processed == operation_count
    
    def test_queue_size_limits(self):
        """测试队列大小限制"""
        config = MQConfig(task_queue_size=100)
        queue = RedisMessageQueue(config)
        
        # 验证配置被正确设置
        assert config.task_queue_size == 100
    
    def test_connection_pool_exhaustion(self):
        """测试连接池耗尽"""
        from mx_rmq.storage import RedisConnectionManager
        
        # 设置较小的连接池
        config = MQConfig(redis_max_connections=5)
        manager = RedisConnectionManager(config)
        
        # 验证配置被应用
        assert config.redis_max_connections == 5
    
    def test_message_retention_limits(self):
        """测试消息保留限制"""
        # 测试消息TTL机制
        message = Message(topic="retention_test", payload={"test": "data"})
        
        # 设置很短的TTL
        short_ttl_ms = int(time.time() * 1000) + 1000  # 1秒后过期
        message.meta.expire_at = short_ttl_ms
        
        # 验证消息将会过期
        assert message.meta.expire_at > 0
        
        # 模拟时间流逝
        future_time_ms = short_ttl_ms + 1000
        with patch('time.time', return_value=future_time_ms / 1000):
            assert message.is_expired() is True
    
    def test_error_accumulation_handling(self):
        """测试错误累积处理"""
        collector = MetricsCollector()
        topic = "error_accumulation_test"
        
        # 记录大量错误
        error_count = 1000
        for i in range(error_count):
            collector.record_message_failed(topic, f"错误_{i}", processing_time=0.1)
        
        # 验证错误被正确统计
        metrics = collector.get_processing_metrics(topic)
        assert metrics.error_count == error_count
        assert metrics.total_processed == error_count
    
    def test_topic_proliferation_handling(self):
        """测试主题激增处理"""
        collector = MetricsCollector()
        
        # 创建大量不同的主题
        topic_count = 5000
        for i in range(topic_count):
            topic = f"proliferation_test_{i}"
            collector.record_message_produced(topic)
        
        # 验证所有主题都被跟踪
        all_queue_metrics = collector.get_all_queue_metrics()
        assert len(all_queue_metrics) == topic_count
        
        # 验证每个主题的指标
        for i in range(topic_count):
            topic = f"proliferation_test_{i}"
            assert topic in all_queue_metrics
            assert all_queue_metrics[topic].pending_count == 1


class TestSystemLimits:
    """系统限制测试"""
    
    def test_maximum_message_size_handling(self):
        """测试最大消息大小处理"""
        # 创建接近系统限制的大消息
        large_payload = {
            "data": "x" * 1000000,  # 1MB
            "metadata": {"size": "large"},
            "array": list(range(10000))
        }
        
        message = Message(topic="large_message_test", payload=large_payload)
        
        # 验证大消息可以被创建
        assert len(message.payload["data"]) == 1000000
        assert len(message.payload["array"]) == 10000
    
    def test_maximum_retry_attempts(self):
        """测试最大重试次数"""
        message = Message(topic="max_retry_test", payload={"test": "data"})
        
        # 设置合理的最大重试次数
        message.meta.max_retries = 100
        
        # 模拟达到最大重试次数
        message.meta.retry_count = 100
        
        # 验证不能再重试
        assert message.can_retry() is False
    
    def test_timestamp_precision_handling(self):
        """测试时间戳精度处理"""
        message = Message(topic="timestamp_test", payload={"test": "data"})
        
        # 验证时间戳精度（毫秒级）
        created_at = message.meta.created_at
        assert created_at > 0
        assert created_at > 1000000000000  # 应该是毫秒时间戳（13位数字）
    
    def test_unicode_string_limits(self):
        """测试Unicode字符串限制"""
        # 创建包含各种Unicode字符的负载
        unicode_payload = {
            "emoji_string": "🚀" * 1000,
            "chinese_string": "你好" * 1000,
            "mixed_string": "Hello🌍世界" * 500
        }
        
        message = Message(topic="unicode_limit_test", payload=unicode_payload)
        
        # 验证Unicode字符串被正确处理
        assert len(message.payload["emoji_string"]) == 1000
        assert len(message.payload["chinese_string"]) == 2000  # 中文字符
        assert "Hello" in message.payload["mixed_string"]
        assert "🌍" in message.payload["mixed_string"]
        assert "世界" in message.payload["mixed_string"]