"""
存储层单元测试
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
import redis.asyncio as aioredis

from mx_rmq.config import MQConfig
from mx_rmq.storage.connection_manager import RedisConnectionManager


class TestRedisConnectionManager:
    """Redis连接管理器测试"""

    def test_connection_manager_initialization(self):
        """测试连接管理器初始化"""
        config = MQConfig(
            redis_host="test.redis.com",
            redis_port=6380,
            redis_db=2,
            redis_max_connections=30
        )
        
        manager = RedisConnectionManager(config)
        
        assert manager.config == config
        assert manager.redis_pool is None
        assert manager.redis is None
        assert manager._initialized is False
        assert manager.redis_version is None
        assert manager.supports_hexpire is False

    @pytest.mark.asyncio
    async def test_initialize_connection_success(self):
        """测试成功初始化连接"""
        config = MQConfig(redis_host="localhost", redis_port=6379)
        manager = RedisConnectionManager(config)
        
        # 模拟Redis连接和响应
        mock_redis = AsyncMock()
        mock_redis.ping.return_value = True
        mock_redis.info.return_value = {"redis_version": "7.2.0"}
        
        with patch('redis.asyncio.ConnectionPool') as mock_pool_class:
            with patch('redis.asyncio.Redis') as mock_redis_class:
                mock_pool_class.return_value = MagicMock()
                mock_redis_class.return_value = mock_redis
                
                result = await manager.initialize_connection()
                
                # 验证连接池创建（只检查关键参数）
                mock_pool_class.assert_called_once()
                call_kwargs = mock_pool_class.call_args[1]
                assert call_kwargs['host'] == "localhost"
                assert call_kwargs['port'] == 6379
                assert call_kwargs['password'] is None
                assert call_kwargs['max_connections'] == 20
                assert call_kwargs['db'] == 0
                assert call_kwargs['decode_responses'] is True
                
                # 验证Redis客户端创建
                mock_redis_class.assert_called_once()
                
                # 验证连接测试
                mock_redis.ping.assert_called_once()
                mock_redis.info.assert_called_once_with("server")
                
                # 验证状态
                assert manager._initialized is True
                assert manager.redis == mock_redis
                assert result == mock_redis

    @pytest.mark.asyncio
    async def test_initialize_connection_idempotent(self):
        """测试重复初始化连接的幂等性"""
        config = MQConfig()
        manager = RedisConnectionManager(config)
        
        mock_redis = AsyncMock()
        mock_redis.ping.return_value = True
        mock_redis.info.return_value = {"redis_version": "6.2.0"}
        
        with patch('redis.asyncio.ConnectionPool'):
            with patch('redis.asyncio.Redis', return_value=mock_redis):
                # 第一次初始化
                result1 = await manager.initialize_connection()
                
                # 第二次初始化应该返回同一个实例
                result2 = await manager.initialize_connection()
                
                assert result1 == result2
                assert manager.redis == mock_redis
                # ping只应该被调用一次（第一次初始化时）
                mock_redis.ping.assert_called_once()

    @pytest.mark.asyncio
    async def test_redis_version_detection(self):
        """测试Redis版本检测"""
        config = MQConfig()
        manager = RedisConnectionManager(config)
        
        # 测试不同版本的检测
        version_tests = [
            ("7.4.0", (7, 4, 0), True),   # 支持HEXPIRE
            ("7.0.0", (7, 0, 0), False),  # 不支持HEXPIRE  
            ("6.2.0", (6, 2, 0), False),  # 不支持HEXPIRE
            ("5.0.0", (5, 0, 0), False),  # 不支持HEXPIRE
        ]
        
        for version_str, expected_tuple, expected_hexpire in version_tests:
            mock_redis = AsyncMock()
            mock_redis.ping.return_value = True
            mock_redis.info.return_value = {"redis_version": version_str}
            
            # 重置管理器状态
            manager._initialized = False
            manager.redis = None
            manager.redis_version = None
            manager.supports_hexpire = False
            
            with patch('redis.asyncio.ConnectionPool'):
                with patch('redis.asyncio.Redis', return_value=mock_redis):
                    await manager.initialize_connection()
                    
                    assert manager.redis_version == expected_tuple
                    assert manager.supports_hexpire == expected_hexpire

    @pytest.mark.asyncio
    async def test_connection_failure(self):
        """测试连接失败处理"""
        config = MQConfig()
        manager = RedisConnectionManager(config)
        
        mock_redis = AsyncMock()
        mock_redis.ping.side_effect = Exception("连接失败")
        
        with patch('redis.asyncio.ConnectionPool'):
            with patch('redis.asyncio.Redis', return_value=mock_redis):
                with pytest.raises(Exception, match="连接失败"):
                    await manager.initialize_connection()
                
                # 验证初始化失败时状态
                assert manager._initialized is False
                # 注意：连接失败时，self.redis 实际上已经被赋值了，只是连接测试失败

    @pytest.mark.asyncio
    async def test_connection_configuration(self):
        """测试连接配置参数传递"""
        config = MQConfig(
            redis_host="custom.redis.com",
            redis_port=6380,
            redis_password="custom_password",
            redis_max_connections=50
        )
        manager = RedisConnectionManager(config)
        
        mock_redis = AsyncMock()
        mock_redis.ping.return_value = True
        mock_redis.info.return_value = {"redis_version": "7.0.0"}
        
        with patch('redis.asyncio.ConnectionPool') as mock_pool_class:
            with patch('redis.asyncio.Redis', return_value=mock_redis):
                await manager.initialize_connection()
                
                # 验证连接配置被正确传递
                mock_pool_class.assert_called_once()
                call_kwargs = mock_pool_class.call_args[1]
                assert call_kwargs['host'] == "custom.redis.com"
                assert call_kwargs['port'] == 6380
                assert call_kwargs['password'] == "custom_password"
                assert call_kwargs['max_connections'] == 50

    @pytest.mark.asyncio
    async def test_version_parsing_edge_cases(self):
        """测试版本解析的边界情况"""
        config = MQConfig()
        manager = RedisConnectionManager(config)
        
        # 测试异常版本字符串
        edge_cases = [
            ("7.4.0-rc1", None),     # 包含后缀会解析失败
            ("6.2", (6, 2, 0)),      # 缺少补丁版本
            ("unstable", None),      # 无效版本
            ("", None),              # 空版本
        ]
        
        for version_str, expected_tuple in edge_cases:
            mock_redis = AsyncMock()
            mock_redis.ping.return_value = True
            mock_redis.info.return_value = {"redis_version": version_str}
            
            # 重置状态
            manager._initialized = False
            manager.redis = None
            manager.redis_version = None
            
            with patch('redis.asyncio.ConnectionPool'):
                with patch('redis.asyncio.Redis', return_value=mock_redis):
                    await manager.initialize_connection()
                    
                    assert manager.redis_version == expected_tuple

    @pytest.mark.asyncio
    async def test_concurrent_initialization(self):
        """测试并发初始化的线程安全性"""
        config = MQConfig()
        manager = RedisConnectionManager(config)
        
        mock_redis = AsyncMock()
        mock_redis.ping.return_value = True
        mock_redis.info.return_value = {"redis_version": "7.0.0"}
        
        call_count = 0
        
        def create_redis(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return mock_redis
        
        with patch('redis.asyncio.ConnectionPool'):
            with patch('redis.asyncio.Redis', side_effect=create_redis):
                # 并发初始化
                results = await asyncio.gather(
                    manager.initialize_connection(),
                    manager.initialize_connection(),
                    manager.initialize_connection()
                )
                
                # 验证所有结果都是同一个实例
                assert all(result == results[0] for result in results)
                # 验证Redis客户端只被创建一次
                assert call_count == 1
                # 验证ping只被调用一次
                mock_redis.ping.assert_called_once()

    def test_config_propagation(self):
        """测试配置参数传播"""
        config = MQConfig(
            redis_host="custom.host",
            redis_port=6380,
            redis_db=5,
            redis_password="test_password",
            redis_max_connections=50,
            redis_ssl=True
        )
        
        manager = RedisConnectionManager(config)
        
        assert manager.config.redis_host == "custom.host"
        assert manager.config.redis_port == 6380
        assert manager.config.redis_db == 5
        assert manager.config.redis_password == "test_password"
        assert manager.config.redis_max_connections == 50
        assert manager.config.redis_ssl is True