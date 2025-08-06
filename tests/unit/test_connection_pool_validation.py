"""Redis连接池大小验证测试"""

import pytest
from mx_rmq import RedisMessageQueue, MQConfig


class TestConnectionPoolValidation:
    """Redis连接池大小验证测试类"""

    def test_sufficient_connections(self):
        """测试连接数足够的情况"""
        # 配置足够的连接数
        config = MQConfig(redis_max_connections=20)
        queue = RedisMessageQueue(config)
        
        # 注册少量处理器
        def handler1(payload):
            return payload
        
        def handler2(payload):
            return payload
        
        queue.register_handler("topic1", handler1)
        queue.register_handler("topic2", handler2)
        
        # 验证不应该抛出异常
        try:
            queue._validate_connection_pool_size()
        except ValueError:
            pytest.fail("连接数足够时不应该抛出异常")

    def test_insufficient_connections(self):
        """测试连接数不足的情况"""
        # 配置较少的连接数
        config = MQConfig(redis_max_connections=10)
        queue = RedisMessageQueue(config)
        
        # 注册多个处理器，使得需要的连接数超过配置
        handlers = {}
        for i in range(5):  # 5个topic + 8个预留 = 13个连接，超过配置的10个
            def handler(payload):
                return payload
            handlers[f"topic{i}"] = handler
            queue.register_handler(f"topic{i}", handler)
        
        # 模拟初始化context
        queue._context = type('MockContext', (), {'handlers': handlers})() # type:ignore
        
        # 验证应该抛出异常
        with pytest.raises(ValueError) as exc_info:
            queue._validate_connection_pool_size()
        
        error_msg = str(exc_info.value)
        assert "Redis连接池大小不足" in error_msg
        assert "当前配置10个连接" in error_msg
        assert "需要至少13个连接" in error_msg
        assert "5个topic + 8个预留" in error_msg
        assert "建议配置" in error_msg

    def test_no_handlers_registered(self):
        """测试未注册处理器的情况"""
        config = MQConfig(redis_max_connections=10)  # 使用足够的连接数
        queue = RedisMessageQueue(config)
        
        # 模拟空的context
        queue._context = type('MockContext', (), {'handlers': {}})() #type:ignore
        
        # 验证不应该抛出异常（0个topic + 8个预留 = 8个连接，小于10个）
        try:
            queue._validate_connection_pool_size()
        except ValueError:
            pytest.fail("未注册处理器时不应该抛出异常")

    def test_no_context(self):
        """测试context不存在的情况"""
        config = MQConfig(redis_max_connections=10)  # 使用足够的连接数
        queue = RedisMessageQueue(config)
        
        # context为None
        queue._context = None
        
        # 验证不应该抛出异常
        try:
            queue._validate_connection_pool_size()
        except ValueError:
            pytest.fail("context不存在时不应该抛出异常")

    def test_edge_case_exact_connections(self):
        """测试边界情况：连接数刚好够用"""
        # 1个topic + 8个预留 = 9个连接
        config = MQConfig(redis_max_connections=9)
        queue = RedisMessageQueue(config)
        
        def handler(payload):
            return payload
        
        queue.register_handler("topic1", handler)
        
        # 模拟初始化context
        queue._context = type('MockContext', (), {'handlers': {'topic1': handler}})() # type: ignore
        
        # 验证不应该抛出异常
        try:
            queue._validate_connection_pool_size()
        except ValueError:
            pytest.fail("连接数刚好够用时不应该抛出异常")

    def test_error_message_format(self):
        """测试错误信息格式"""
        config = MQConfig(redis_max_connections=5)
        queue = RedisMessageQueue(config)
        
        # 注册3个处理器，需要11个连接（3+8），超过配置的5个
        handlers = {}
        for i in range(3):
            def handler(payload):
                return payload
            handlers[f"topic{i}"] = handler
            queue.register_handler(f"topic{i}", handler)
        
        queue._context = type('MockContext', (), {'handlers': handlers})() # type: ignore
        
        with pytest.raises(ValueError) as exc_info:
            queue._validate_connection_pool_size()
        
        error_msg = str(exc_info.value)
        
        # 验证错误信息包含所有必要信息
        assert "当前配置5个连接" in error_msg
        assert "需要至少11个连接" in error_msg
        assert "3个topic + 8个预留" in error_msg
        assert "redis_max_connections配置至11或更高" in error_msg
        assert "建议配置：redis_max_connections = 16" in error_msg