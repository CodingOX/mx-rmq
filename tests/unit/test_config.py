"""
配置模块单元测试
"""

import pytest
from pydantic import ValidationError

from mx_rmq.config import MQConfig


class TestMQConfig:
    """MQConfig配置类测试"""

    def test_default_config(self):
        """测试默认配置创建"""
        config = MQConfig()
        
        # 验证默认值
        assert config.redis_host == "localhost"
        assert config.redis_port == 6379
        assert config.redis_db == 0
        assert config.redis_password is None
        assert config.redis_ssl is False
        assert config.queue_prefix == ""
        assert config.max_workers == 5
        assert config.task_queue_size == 8
        assert config.max_retries == 3
        assert config.retry_delays == [60, 300, 1800]
        assert config.log_level == "INFO"
        assert config.handler_timeout == 60.0
        assert config.enable_handler_timeout is True

    def test_custom_config(self):
        """测试自定义配置"""
        config = MQConfig(
            redis_host="192.168.1.100",
            redis_port=6380,
            redis_db=5,
            redis_password="secret",
            redis_ssl=True,
            queue_prefix="test_mq",
            max_workers=10,
            task_queue_size=20,
            max_retries=5,
            retry_delays=[30, 60, 120],
            log_level="DEBUG",
            handler_timeout=120.0
        )
        
        assert config.redis_host == "192.168.1.100"
        assert config.redis_port == 6380
        assert config.redis_db == 5
        assert config.redis_password == "secret"
        assert config.redis_ssl is True
        assert config.queue_prefix == "test_mq"
        assert config.max_workers == 10
        assert config.task_queue_size == 20
        assert config.max_retries == 5
        assert config.retry_delays == [30, 60, 120]
        assert config.log_level == "DEBUG"
        assert config.handler_timeout == 120.0

    def test_config_immutable(self):
        """测试配置对象不可变性"""
        config = MQConfig()
        
        with pytest.raises(ValidationError):
            config.redis_host = "new_host"

    def test_redis_db_validation(self):
        """测试Redis数据库编号验证"""
        # 有效范围
        for db in [0, 5, 15]:
            config = MQConfig(redis_db=db)
            assert config.redis_db == db
        
        # 无效范围
        with pytest.raises(ValidationError):
            MQConfig(redis_db=-1)
        
        with pytest.raises(ValidationError):
            MQConfig(redis_db=16)

    def test_connection_pool_size_validation(self):
        """测试连接池大小验证"""
        # 有效范围
        config = MQConfig(redis_max_connections=20)
        assert config.redis_max_connections == 20
        
        # 边界值
        config = MQConfig(redis_max_connections=5)
        assert config.redis_max_connections == 5
        
        config = MQConfig(redis_max_connections=100)
        assert config.redis_max_connections == 100
        
        # 无效范围
        with pytest.raises(ValidationError):
            MQConfig(redis_max_connections=4)
        
        with pytest.raises(ValidationError):
            MQConfig(redis_max_connections=101)

    def test_max_workers_validation(self):
        """测试最大工作协程数验证"""
        # 有效范围
        config = MQConfig(max_workers=1)
        assert config.max_workers == 1
        
        config = MQConfig(max_workers=50)
        assert config.max_workers == 50
        
        # 无效范围
        with pytest.raises(ValidationError):
            MQConfig(max_workers=0)
        
        with pytest.raises(ValidationError):
            MQConfig(max_workers=51)

    def test_task_queue_size_validation(self):
        """测试任务队列大小验证"""
        # 任务队列大小必须大于最大工作数
        config = MQConfig(max_workers=5, task_queue_size=10)
        assert config.task_queue_size == 10
        
        # 无效：任务队列大小小于等于最大工作数
        with pytest.raises(ValidationError) as exc_info:
            MQConfig(max_workers=5, task_queue_size=5)
        assert "必须大于 max_workers" in str(exc_info.value)
        
        # 这个测试会触发Field的ge=5约束，而不是我们的自定义验证器
        with pytest.raises(ValidationError) as exc_info:
            MQConfig(max_workers=5, task_queue_size=3)
        # 验证触发了基本的数值范围检查
        assert "Input should be greater than or equal to 5" in str(exc_info.value)

    def test_max_retries_validation(self):
        """测试最大重试次数验证"""
        # 有效范围
        config = MQConfig(max_retries=0)
        assert config.max_retries == 0
        
        config = MQConfig(max_retries=10)
        assert config.max_retries == 10
        
        # 无效范围
        with pytest.raises(ValidationError):
            MQConfig(max_retries=-1)
        
        with pytest.raises(ValidationError):
            MQConfig(max_retries=11)

    def test_retry_delays_validation(self):
        """测试重试延迟配置验证"""
        # 有效配置
        config = MQConfig(retry_delays=[30, 60, 120])
        assert config.retry_delays == [30, 60, 120]
        
        # 空列表无效
        with pytest.raises(ValidationError) as exc_info:
            MQConfig(retry_delays=[])
        assert "重试延迟列表不能为空" in str(exc_info.value)
        
        # 包含非正数无效
        with pytest.raises(ValidationError) as exc_info:
            MQConfig(retry_delays=[30, 0, 120])
        assert "重试延迟必须大于0" in str(exc_info.value)
        
        with pytest.raises(ValidationError) as exc_info:
            MQConfig(retry_delays=[30, -60, 120])
        assert "重试延迟必须大于0" in str(exc_info.value)

    def test_log_level_validation(self):
        """测试日志级别验证"""
        # 有效日志级别
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        for level in valid_levels:
            config = MQConfig(log_level=level)
            assert config.log_level == level
            
            # 测试小写输入自动转换为大写
            config = MQConfig(log_level=level.lower())
            assert config.log_level == level
        
        # 无效日志级别
        with pytest.raises(ValidationError) as exc_info:
            MQConfig(log_level="INVALID")
        assert "日志级别必须是:" in str(exc_info.value)

    def test_queue_prefix_validation(self):
        """测试队列前缀验证"""
        # 有效前缀
        valid_prefixes = ["", "test", "my_queue", "queue-1", "app_v1", "prod-env"]
        for prefix in valid_prefixes:
            config = MQConfig(queue_prefix=prefix)
            assert config.queue_prefix == prefix
        
        # 无效前缀：包含特殊字符
        with pytest.raises(ValidationError) as exc_info:
            MQConfig(queue_prefix="test@queue")
        assert "只能包含字母、数字、下划线和连字符" in str(exc_info.value)
        
        # 无效前缀：以连字符开头
        with pytest.raises(ValidationError) as exc_info:
            MQConfig(queue_prefix="-test")
        assert "不能以连字符开头或结尾" in str(exc_info.value)
        
        # 无效前缀：以连字符结尾
        with pytest.raises(ValidationError) as exc_info:
            MQConfig(queue_prefix="test-")
        assert "不能以连字符开头或结尾" in str(exc_info.value)

    def test_handler_timeout_validation(self):
        """测试处理器超时配置验证"""
        # 有效超时配置
        config = MQConfig(handler_timeout=30.5)
        assert config.handler_timeout == 30.5
        
        # 边界值
        config = MQConfig(handler_timeout=1.0)
        assert config.handler_timeout == 1.0
        
        # 无效：小于最小值
        with pytest.raises(ValidationError):
            MQConfig(handler_timeout=0.5)

    def test_handler_timeouts_dict(self):
        """测试主题级别超时配置"""
        timeouts = {"heavy_task": 300.0, "light_task": 10.0}
        config = MQConfig(handler_timeouts=timeouts)
        assert config.handler_timeouts == timeouts

    def test_parse_error_config_validation(self):
        """测试解析错误配置验证"""
        # 有效配置
        config = MQConfig(parse_error_ttl_days=7, parse_error_max_count=5000)
        assert config.parse_error_ttl_days == 7
        assert config.parse_error_max_count == 5000
        
        # 边界值测试
        config = MQConfig(parse_error_ttl_days=1, parse_error_max_count=100)
        assert config.parse_error_ttl_days == 1
        assert config.parse_error_max_count == 100
        
        config = MQConfig(parse_error_ttl_days=30, parse_error_max_count=100000)
        assert config.parse_error_ttl_days == 30
        assert config.parse_error_max_count == 100000
        
        # 无效范围
        with pytest.raises(ValidationError):
            MQConfig(parse_error_ttl_days=0)
        
        with pytest.raises(ValidationError):
            MQConfig(parse_error_ttl_days=31)
        
        with pytest.raises(ValidationError):
            MQConfig(parse_error_max_count=99)
        
        with pytest.raises(ValidationError):
            MQConfig(parse_error_max_count=100001)

    def test_batch_size_validation(self):
        """测试批处理大小验证"""
        # 有效范围
        config = MQConfig(batch_size=50)
        assert config.batch_size == 50
        
        # 边界值
        config = MQConfig(batch_size=10)
        assert config.batch_size == 10
        
        config = MQConfig(batch_size=1000)
        assert config.batch_size == 1000
        
        # 无效范围
        with pytest.raises(ValidationError):
            MQConfig(batch_size=9)
        
        with pytest.raises(ValidationError):
            MQConfig(batch_size=1001)

    def test_config_from_dict(self):
        """测试从字典创建配置"""
        config_dict = {
            "redis_host": "test.redis.com",
            "redis_port": 6379,
            "queue_prefix": "production",
            "max_workers": 10,
            "task_queue_size": 20,
            "handler_timeout": 90.0
        }
        
        config = MQConfig(**config_dict)
        assert config.redis_host == "test.redis.com"
        assert config.queue_prefix == "production"
        assert config.max_workers == 10
        assert config.task_queue_size == 20
        assert config.handler_timeout == 90.0