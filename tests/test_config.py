"""MQConfig 配置类的单元测试"""

import pytest
from mx_rmq.config import MQConfig


class TestMQConfig:
    """测试 MQConfig 配置类"""

    def test_default_config(self):
        """测试默认配置"""
        config = MQConfig()

        # 验证默认Redis配置
        assert config.redis_url == "redis://localhost:6379"
        assert config.redis_db == 0
        assert config.connection_pool_size == 20

        # 验证默认消费者配置
        assert config.max_workers == 5
        assert config.task_queue_size == 8

        # 验证默认消息生命周期配置
        assert config.message_ttl == 86400
        assert config.processing_timeout == 180

        # 验证默认重试配置
        assert config.max_retries == 3
        assert config.retry_delays == [60, 300, 1800]

        # 验证默认死信队列配置
        assert config.enable_dead_letter is True

        # 验证默认监控配置
        assert config.monitor_interval == 30
        assert config.expired_check_interval == 10
        assert config.processing_monitor_interval == 60
        assert config.batch_size == 100

        # 验证默认日志配置
        assert config.log_level == "INFO"

    def test_custom_config(self):
        """测试自定义配置"""
        config = MQConfig(
            redis_url="redis://custom:6380",
            redis_db=1,
            max_workers=20,
            max_retries=5,
            log_level="DEBUG",
        )

        assert config.redis_url == "redis://custom:6380"
        assert config.redis_db == 1
        assert config.max_workers == 20
        assert config.max_retries == 5
        assert config.log_level == "DEBUG"

        # 验证其他配置保持默认值
        assert config.connection_pool_size == 20
        assert config.task_queue_size == 8

    def test_redis_url_validation(self):
        """测试Redis URL验证"""
        # 有效的Redis URL
        valid_urls = [
            "redis://localhost:6379",
            "redis://user:pass@localhost:6379",
            "rediss://localhost:6380",
        ]

        for url in valid_urls:
            config = MQConfig(redis_url=url)
            assert config.redis_url == url

    def test_redis_db_validation(self):
        """测试Redis数据库编号验证"""
        # 有效值
        for db in [0, 1, 15]:
            config = MQConfig(redis_db=db)
            assert config.redis_db == db

        # 无效值
        with pytest.raises(ValueError):
            MQConfig(redis_db=-1)

        with pytest.raises(ValueError):
            MQConfig(redis_db=16)

    def test_connection_pool_validation(self):
        """测试连接池大小验证"""
        # 有效值
        config = MQConfig(connection_pool_size=10)
        assert config.connection_pool_size == 10

        # 边界值
        config = MQConfig(connection_pool_size=5)
        assert config.connection_pool_size == 5

        config = MQConfig(connection_pool_size=100)
        assert config.connection_pool_size == 100

        # 无效值
        with pytest.raises(ValueError):
            MQConfig(connection_pool_size=4)

        with pytest.raises(ValueError):
            MQConfig(connection_pool_size=101)

    def test_max_workers_validation(self):
        """测试最大工作协程数验证"""
        # 有效值
        config = MQConfig(max_workers=10)
        assert config.max_workers == 10

        # 边界值
        config = MQConfig(max_workers=1)
        assert config.max_workers == 1

        config = MQConfig(max_workers=50)
        assert config.max_workers == 50

        # 无效值
        with pytest.raises(ValueError):
            MQConfig(max_workers=0)

        with pytest.raises(ValueError):
            MQConfig(max_workers=51)

    def test_task_queue_size_validation(self):
        """测试任务队列大小验证"""
        # 有效值（必须大于max_workers）
        config = MQConfig(max_workers=5, task_queue_size=10)
        assert config.max_workers == 5
        assert config.task_queue_size == 10

        # 无效值（小于max_workers）
        with pytest.raises(ValueError):
            MQConfig(max_workers=10, task_queue_size=5)

        # 无效值（等于max_workers）
        with pytest.raises(ValueError):
            MQConfig(max_workers=10, task_queue_size=10)

    def test_message_ttl_validation(self):
        """测试消息TTL验证"""
        # 有效值
        config = MQConfig(message_ttl=3600)
        assert config.message_ttl == 3600

        # 边界值
        config = MQConfig(message_ttl=60)
        assert config.message_ttl == 60

        # 无效值
        with pytest.raises(ValueError):
            MQConfig(message_ttl=59)

    def test_processing_timeout_validation(self):
        """测试处理超时验证"""
        # 有效值
        config = MQConfig(processing_timeout=600)
        assert config.processing_timeout == 600

        # 边界值
        config = MQConfig(processing_timeout=30)
        assert config.processing_timeout == 30

        # 无效值
        with pytest.raises(ValueError):
            MQConfig(processing_timeout=29)

    def test_max_retries_validation(self):
        """测试最大重试次数验证"""
        # 有效值
        for retries in [0, 3, 10]:
            config = MQConfig(max_retries=retries)
            assert config.max_retries == retries

        # 无效值
        with pytest.raises(ValueError):
            MQConfig(max_retries=-1)

        with pytest.raises(ValueError):
            MQConfig(max_retries=11)

    def test_retry_delays_validation(self):
        """测试重试延迟验证"""
        # 有效值
        config = MQConfig(retry_delays=[30, 60, 120])
        assert config.retry_delays == [30, 60, 120]

        # 无效值（空列表）
        with pytest.raises(ValueError):
            MQConfig(retry_delays=[])

        # 无效值（包含非正数）
        with pytest.raises(ValueError):
            MQConfig(retry_delays=[30, 0, 120])

        with pytest.raises(ValueError):
            MQConfig(retry_delays=[30, -60, 120])

    def test_monitor_intervals_validation(self):
        """测试监控间隔验证"""
        # 有效值
        config = MQConfig(
            monitor_interval=60,
            expired_check_interval=30,
            processing_monitor_interval=120,
        )
        assert config.monitor_interval == 60
        assert config.expired_check_interval == 30
        assert config.processing_monitor_interval == 120

        # 边界值
        config = MQConfig(monitor_interval=5, expired_check_interval=5)
        assert config.monitor_interval == 5
        assert config.expired_check_interval == 5

        config = MQConfig(processing_monitor_interval=30)
        assert config.processing_monitor_interval == 30

        # 无效值
        with pytest.raises(ValueError):
            MQConfig(monitor_interval=4)

        with pytest.raises(ValueError):
            MQConfig(expired_check_interval=4)

        with pytest.raises(ValueError):
            MQConfig(processing_monitor_interval=29)

    def test_batch_size_validation(self):
        """测试批处理大小验证"""
        # 有效值
        config = MQConfig(batch_size=500)
        assert config.batch_size == 500

        # 边界值
        config = MQConfig(batch_size=10)
        assert config.batch_size == 10

        config = MQConfig(batch_size=1000)
        assert config.batch_size == 1000

        # 无效值
        with pytest.raises(ValueError):
            MQConfig(batch_size=9)

        with pytest.raises(ValueError):
            MQConfig(batch_size=1001)

    def test_log_level_validation(self):
        """测试日志级别验证"""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

        for level in valid_levels:
            config = MQConfig(log_level=level)
            assert config.log_level == level

        # 测试小写输入会被转换为大写
        config = MQConfig(log_level="debug")
        assert config.log_level == "DEBUG"

        # 测试无效日志级别
        with pytest.raises(ValueError):
            MQConfig(log_level="INVALID")

    def test_config_immutability(self):
        """测试配置对象的不可变性"""
        config = MQConfig()

        # 由于配置了frozen=True，尝试修改会抛出异常
        with pytest.raises(ValueError):
            config.redis_url = "redis://new:6379"

        with pytest.raises(ValueError):
            config.max_workers = 10

    def test_config_serialization(self):
        """测试配置序列化"""
        config = MQConfig(
            redis_url="redis://test:6379", redis_db=1, max_workers=15, log_level="DEBUG"
        )

        # 测试转换为字典
        config_dict = config.model_dump()
        assert config_dict["redis_url"] == "redis://test:6379"
        assert config_dict["redis_db"] == 1
        assert config_dict["max_workers"] == 15
        assert config_dict["log_level"] == "DEBUG"

        # 测试JSON序列化
        config_json = config.model_dump_json()
        assert isinstance(config_json, str)
        assert "redis://test:6379" in config_json

    def test_config_from_dict(self):
        """测试从字典创建配置"""
        config_data = {
            "redis_url": "redis://from_dict:6379",
            "redis_db": 2,
            "max_workers": 25,
            "max_retries": 7,
            "log_level": "WARNING",
        }

        config = MQConfig.model_validate(config_data)
        assert config.redis_url == "redis://from_dict:6379"
        assert config.redis_db == 2
        assert config.max_workers == 25
        assert config.max_retries == 7
        assert config.log_level == "WARNING"

        # 验证未指定的字段使用默认值
        assert config.connection_pool_size == 20
        assert config.retry_delays == [60, 300, 1800]

    def test_complex_validation_scenario(self):
        """测试复杂验证场景"""
        # 测试task_queue_size必须大于max_workers的复合验证
        config = MQConfig(max_workers=8, task_queue_size=15)
        assert config.max_workers == 8
        assert config.task_queue_size == 15

        # 测试自定义重试延迟配置
        custom_delays = [10, 30, 90, 270]
        config = MQConfig(max_retries=4, retry_delays=custom_delays)
        assert config.max_retries == 4
        assert config.retry_delays == custom_delays
