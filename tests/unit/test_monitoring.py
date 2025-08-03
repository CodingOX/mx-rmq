"""
监控模块单元测试
"""

import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from collections import deque

from mx_rmq.monitoring.metrics import (
    MetricsCollector, 
    QueueMetrics, 
    ProcessingMetrics
)


class TestQueueMetrics:
    """队列指标数据类测试"""
    
    def test_default_queue_metrics(self):
        """测试默认队列指标"""
        metrics = QueueMetrics()
        
        assert metrics.pending_count == 0
        assert metrics.processing_count == 0
        assert metrics.completed_count == 0
        assert metrics.failed_count == 0
        assert metrics.dead_letter_count == 0
        assert metrics.delay_count == 0
    
    def test_custom_queue_metrics(self):
        """测试自定义队列指标"""
        metrics = QueueMetrics(
            pending_count=10,
            processing_count=5,
            completed_count=100,
            failed_count=3,
            dead_letter_count=1,
            delay_count=8
        )
        
        assert metrics.pending_count == 10
        assert metrics.processing_count == 5
        assert metrics.completed_count == 100
        assert metrics.failed_count == 3
        assert metrics.dead_letter_count == 1
        assert metrics.delay_count == 8
    
    def test_queue_metrics_validation(self):
        """测试队列指标验证"""
        # 负数应该引发验证错误
        with pytest.raises(ValueError):
            QueueMetrics(pending_count=-1)
        
        with pytest.raises(ValueError):
            QueueMetrics(processing_count=-1)


class TestProcessingMetrics:
    """处理指标数据类测试"""
    
    def test_default_processing_metrics(self):
        """测试默认处理指标"""
        metrics = ProcessingMetrics()
        
        assert metrics.total_processed == 0
        assert metrics.success_count == 0
        assert metrics.error_count == 0
        assert metrics.retry_count == 0
        assert metrics.avg_processing_time == 0.0
        assert metrics.max_processing_time == 0.0
        assert metrics.min_processing_time == 0.0
    
    def test_custom_processing_metrics(self):
        """测试自定义处理指标"""
        metrics = ProcessingMetrics(
            total_processed=150,
            success_count=140,
            error_count=10,
            retry_count=5,
            avg_processing_time=2.5,
            max_processing_time=10.0,
            min_processing_time=0.1
        )
        
        assert metrics.total_processed == 150
        assert metrics.success_count == 140
        assert metrics.error_count == 10
        assert metrics.retry_count == 5
        assert metrics.avg_processing_time == 2.5
        assert metrics.max_processing_time == 10.0
        assert metrics.min_processing_time == 0.1
    
    def test_processing_metrics_validation(self):
        """测试处理指标验证"""
        # 负数应该引发验证错误
        with pytest.raises(ValueError):
            ProcessingMetrics(total_processed=-1)
        
        with pytest.raises(ValueError):
            ProcessingMetrics(avg_processing_time=-0.1)


class TestMetricsCollector:
    """指标收集器测试"""
    
    def test_collector_initialization_without_redis(self):
        """测试不带Redis的收集器初始化"""
        collector = MetricsCollector()
        
        assert collector.redis is None
        assert collector.queue_prefix == ""
        assert collector._queue_counters == {}
        assert collector._processing_counters == {}
        assert collector._processing_times == {}
        assert collector._lock is not None
    
    def test_collector_initialization_with_redis(self):
        """测试带Redis的收集器初始化"""
        mock_redis = AsyncMock()
        queue_prefix = "test_mq"
        
        collector = MetricsCollector(redis=mock_redis, queue_prefix=queue_prefix)
        
        assert collector.redis == mock_redis
        assert collector.queue_prefix == queue_prefix
    
    def test_record_message_produced(self):
        """测试记录消息生产"""
        collector = MetricsCollector()
        topic = "test_topic"
        
        # 记录普通消息
        collector.record_message_produced(topic)
        
        metrics = collector.get_queue_metrics(topic)
        assert metrics.pending_count == 1
        
        # 记录更多消息
        collector.record_message_produced(topic, priority="high")
        
        metrics = collector.get_queue_metrics(topic)
        assert metrics.pending_count == 2
    
    def test_record_message_consumed(self):
        """测试记录消息消费（开始处理）"""
        collector = MetricsCollector()
        topic = "test_topic"
        
        # 先生产一条消息
        collector.record_message_produced(topic)
        
        # 开始处理（消费）
        collector.record_message_consumed(topic)
        
        metrics = collector.get_queue_metrics(topic)
        assert metrics.pending_count == 0
        assert metrics.processing_count == 1
    
    def test_record_message_completed(self):
        """测试记录消息完成处理"""
        collector = MetricsCollector()
        topic = "test_topic"
        
        # 模拟消息处理流程
        collector.record_message_produced(topic)
        collector.record_message_consumed(topic)
        
        with patch('time.time', return_value=1640995200):
            collector.record_message_completed(topic, processing_time=1.5)
        
        metrics = collector.get_queue_metrics(topic)
        assert metrics.processing_count == 0
        assert metrics.completed_count == 1
        
        # 检查处理时间记录
        processing_metrics = collector.get_processing_metrics(topic)
        assert processing_metrics.total_processed == 1
        assert processing_metrics.success_count == 1
    
    def test_record_message_failed(self):
        """测试记录消息处理失败"""
        collector = MetricsCollector()
        topic = "test_topic"
        
        # 模拟消息处理失败
        collector.record_message_produced(topic)
        collector.record_message_consumed(topic)
        collector.record_message_failed(topic, "处理错误", processing_time=0.8)
        
        metrics = collector.get_queue_metrics(topic)
        assert metrics.processing_count == 0
        assert metrics.failed_count == 1
        
        processing_metrics = collector.get_processing_metrics(topic)
        assert processing_metrics.total_processed == 1
        assert processing_metrics.error_count == 1
    
    def test_record_message_dead_letter(self):
        """测试记录消息移入死信队列"""
        collector = MetricsCollector()
        topic = "test_topic"
        
        # 先进入处理状态
        collector.record_message_produced(topic)
        collector.record_message_consumed(topic)
        collector.record_message_dead_letter(topic)
        
        metrics = collector.get_queue_metrics(topic)
        assert metrics.processing_count == 0
        assert metrics.dead_letter_count == 1
    
    def test_record_message_retried(self):
        """测试记录消息重试"""
        collector = MetricsCollector()
        topic = "test_topic"
        
        collector.record_message_retried(topic)
        
        processing_metrics = collector.get_processing_metrics(topic)
        assert processing_metrics.retry_count == 1
    
    def test_record_delay_message(self):
        """测试记录延时消息"""
        collector = MetricsCollector()
        topic = "test_topic"
        
        collector.record_delay_message(topic)
        
        metrics = collector.get_queue_metrics(topic)
        assert metrics.delay_count == 1
    
    def test_start_end_processing_timing(self):
        """测试处理时间计算"""
        collector = MetricsCollector()
        message_id = "test-message-123"
        
        # 开始处理
        with patch('time.time', return_value=1640995200.0):
            collector.start_processing(message_id)
        
        # 结束处理
        with patch('time.time', return_value=1640995202.5):
            processing_time = collector.end_processing(message_id)
        
        assert processing_time == 2.5
    
    def test_thread_safety(self):
        """测试线程安全性"""
        collector = MetricsCollector()
        topic = "test_topic"
        
        # 验证锁的存在
        assert collector._lock is not None
        
        # 并发操作不应该引起异常（这是基本的烟雾测试）
        import threading
        
        def worker():
            for _ in range(10):
                collector.record_message_produced(topic)
                collector.record_message_consumed(topic)
                collector.record_message_completed(topic, processing_time=1.0)
        
        threads = []
        for _ in range(5):
            thread = threading.Thread(target=worker)
            threads.append(thread)
            thread.start()
        
        for thread in threads:
            thread.join()
        
        # 验证最终结果
        processing_metrics = collector.get_processing_metrics(topic)
        assert processing_metrics.total_processed == 50
    
    def test_get_all_queue_metrics(self):
        """测试获取所有队列指标"""
        collector = MetricsCollector()
        
        # 为多个topic生产消息
        topics = ["topic1", "topic2", "topic3"]
        
        for topic in topics:
            collector.record_message_produced(topic)
            collector.record_message_consumed(topic)
            collector.record_message_completed(topic, processing_time=1.0)
        
        all_metrics = collector.get_all_queue_metrics()
        
        assert len(all_metrics) == 3
        assert all(topic in all_metrics for topic in topics)
        
        for topic in topics:
            metrics = all_metrics[topic]
            assert metrics.completed_count == 1
    
    def test_get_all_processing_metrics(self):
        """测试获取所有处理指标"""
        collector = MetricsCollector()
        
        topics = ["topic1", "topic2"]
        
        for topic in topics:
            collector.record_message_completed(topic, processing_time=2.0)
            collector.record_message_failed(topic, "错误", processing_time=1.0)
        
        all_processing_metrics = collector.get_all_processing_metrics()
        
        assert len(all_processing_metrics) == 2
        
        for topic in topics:
            metrics = all_processing_metrics[topic]
            assert metrics.total_processed == 2
            assert metrics.success_count == 1
            assert metrics.error_count == 1
    
    def test_processing_time_statistics(self):
        """测试处理时间统计"""
        collector = MetricsCollector()
        topic = "test_topic"
        
        # 记录多个处理时间
        processing_times = [1.0, 2.0, 3.0, 4.0, 5.0]
        
        for processing_time in processing_times:
            collector.record_message_completed(topic, processing_time=processing_time)
        
        processing_metrics = collector.get_processing_metrics(topic)
        
        # 验证统计计算
        assert processing_metrics.total_processed == 5
        assert processing_metrics.success_count == 5
        assert processing_metrics.avg_processing_time == 3.0  # 平均值
        assert processing_metrics.max_processing_time == 5.0  # 最大值
        assert processing_metrics.min_processing_time == 1.0  # 最小值
    
    def test_processing_time_window_limit(self):
        """测试处理时间窗口限制"""
        collector = MetricsCollector()
        topic = "test_topic"
        
        # 记录超过窗口大小的处理时间
        for i in range(1200):  # 超过默认1000的窗口大小
            collector.record_message_completed(topic, processing_time=float(i))
        
        # 验证只保留最近的1000条记录
        processing_times = collector._processing_times[topic]
        assert len(processing_times) == 1000
        assert processing_times[0] == 200.0  # 最旧的应该是200
        assert processing_times[-1] == 1199.0  # 最新的应该是1199
    
    def test_metrics_summary(self):
        """测试指标摘要"""
        collector = MetricsCollector()
        topic = "test_topic"
        
        # 生成一些测试数据
        collector.record_message_produced(topic)  # pending +1
        collector.record_delay_message(topic)     # delay +1
        collector.record_message_consumed(topic)  # pending -1, processing +1
        collector.record_message_completed(topic, processing_time=2.5)  # processing -1, completed +1
        
        # 另一个失败消息
        collector.record_message_produced(topic)
        collector.record_message_consumed(topic)
        collector.record_message_failed(topic, "错误", processing_time=1.0)  # processing -1, failed +1
        
        collector.record_message_dead_letter(topic)  # dead_letter +1 
        collector.record_message_retried(topic)      # retry +1
        
        # 获取摘要
        queue_metrics = collector.get_queue_metrics(topic)
        processing_metrics = collector.get_processing_metrics(topic)
        
        # 验证队列指标
        assert queue_metrics.pending_count == 0
        assert queue_metrics.processing_count == 0  # 已完成/失败
        assert queue_metrics.completed_count == 1
        assert queue_metrics.failed_count == 1
        assert queue_metrics.dead_letter_count == 1
        assert queue_metrics.delay_count == 1
        
        # 验证处理指标
        assert processing_metrics.total_processed == 2  # 1成功 + 1失败
        assert processing_metrics.success_count == 1
        assert processing_metrics.error_count == 1
        assert processing_metrics.retry_count == 1