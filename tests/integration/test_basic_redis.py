"""
简化的Redis集成测试
"""

import asyncio
import pytest
import redis.asyncio as aioredis
import time
from mx_rmq.config import MQConfig


@pytest.mark.integration
class TestBasicRedisIntegration:
    """基础Redis集成测试"""
    
    @pytest.mark.asyncio
    async def test_redis8_connection(self):
        """测试Redis 8.x连接"""
        client = aioredis.Redis(host="localhost", port=6378, db=1, decode_responses=True)
        
        try:
            # 测试连接
            result = await client.ping()
            assert result is True
            
            # 测试基础操作
            await client.set("test_key", "test_value")
            value = await client.get("test_key")
            assert value == "test_value"
            
            # 测试列表操作
            await client.lpush("test_list", "item1", "item2", "item3") # type: ignore
            length = await client.llen("test_list") # type: ignore
            assert length == 3
            
            items = await client.lrange("test_list", 0, -1) # type: ignore
            assert "item1" in items
            assert "item2" in items
            assert "item3" in items
            
        finally:
            await client.flushdb()
            await client.aclose()
    
    @pytest.mark.asyncio
    async def test_redis6_connection(self):
        """测试Redis 6.x连接"""
        client = aioredis.Redis(host="localhost", port=6376, db=1, decode_responses=True)
        
        try:
            # 测试连接
            result = await client.ping()
            assert result is True
            
            # 测试基础操作
            await client.set("test_key", "test_value")
            value = await client.get("test_key")
            assert value == "test_value"
            
            # 测试有序集合操作
            await client.zadd("test_zset", {"member1": 1, "member2": 2, "member3": 3})
            count = await client.zcard("test_zset")
            assert count == 3
            
            members = await client.zrange("test_zset", 0, -1)
            assert "member1" in members
            assert "member2" in members
            assert "member3" in members
            
        finally:
            await client.flushdb()
            await client.aclose()
    
    @pytest.mark.asyncio
    async def test_config_validation(self):
        """测试配置验证"""
        # Redis 8.x配置
        config8 = MQConfig(
            redis_host="localhost",
            redis_port=6378,
            redis_db=1,
            queue_prefix="test_v8"
        )
        
        assert config8.redis_host == "localhost"
        assert config8.redis_port == 6378
        assert config8.redis_db == 1
        
        # Redis 6.x配置
        config6 = MQConfig(
            redis_host="localhost",
            redis_port=6376,
            redis_db=1,
            queue_prefix="test_v6"
        )
        
        assert config6.redis_host == "localhost"
        assert config6.redis_port == 6376
        assert config6.redis_db == 1
    
    @pytest.mark.asyncio
    async def test_concurrent_redis_operations(self):
        """测试并发Redis操作"""
        client = aioredis.Redis(host="localhost", port=6378, db=1, decode_responses=True)
        
        try:
            # 并发写入操作
            async def write_operation(key_suffix: int):
                await client.set(f"concurrent_key_{key_suffix}", f"value_{key_suffix}")
                await client.lpush(f"concurrent_list_{key_suffix}", f"item_{key_suffix}") # type: ignore
                return key_suffix
            
            # 创建并发任务
            tasks = [write_operation(i) for i in range(10)]
            results = await asyncio.gather(*tasks)
            
            assert len(results) == 10
            assert results == list(range(10))
            
            # 验证所有键都存在
            for i in range(10):
                value = await client.get(f"concurrent_key_{i}")
                assert value == f"value_{i}"
                
                list_items = await client.lrange(f"concurrent_list_{i}", 0, -1) # type: ignore
                assert f"item_{i}" in list_items
            
        finally:
            await client.flushdb()
            await client.aclose()
    
    @pytest.mark.asyncio
    async def test_redis_performance_baseline(self):
        """测试Redis性能基线"""
        client = aioredis.Redis(host="localhost", port=6378, db=1, decode_responses=True)
        
        try:
            # 测试批量写入性能
            start_time = time.time()
            
            pipe = client.pipeline()
            for i in range(1000):
                pipe.set(f"perf_key_{i}", f"value_{i}")
            
            await pipe.execute()
            
            write_time = time.time() - start_time
            assert write_time < 2.0  # 应该在2秒内完成1000个写入
            
            # 测试批量读取性能
            start_time = time.time()
            
            pipe = client.pipeline()
            for i in range(1000):
                pipe.get(f"perf_key_{i}")
            
            results = await pipe.execute()
            
            read_time = time.time() - start_time
            assert read_time < 1.0  # 应该在1秒内完成1000个读取
            
            # 验证读取结果
            assert len(results) == 1000
            assert results[0] == "value_0"
            assert results[999] == "value_999"
            
        finally:
            await client.flushdb()
            await client.aclose()


@pytest.mark.integration
class TestMessageQueueBasics:
    """消息队列基础功能测试"""
    
    @pytest.mark.asyncio
    async def test_message_queue_initialization(self):
        """测试消息队列初始化""" 
        from mx_rmq import RedisMessageQueue
        
        # Redis 8.x测试
        config8 = MQConfig(
            redis_host="localhost",
            redis_port=6378,
            redis_db=1,
            queue_prefix="init_test_v8"
        )
        
        queue8 = RedisMessageQueue(config8)
        assert queue8.config.redis_port == 6378
        assert queue8.is_running() is False
        
        # Redis 6.x测试
        config6 = MQConfig(
            redis_host="localhost", 
            redis_port=6376,
            redis_db=1,
            queue_prefix="init_test_v6"
        )
        
        queue6 = RedisMessageQueue(config6)
        assert queue6.config.redis_port == 6376
        assert queue6.is_running() is False
    
    @pytest.mark.asyncio
    async def test_handler_registration(self):
        """测试处理器注册"""
        from mx_rmq import RedisMessageQueue
        
        config = MQConfig(
            redis_host="localhost",
            redis_port=6378,
            redis_db=1,
            queue_prefix="handler_test"
        )
        
        queue = RedisMessageQueue(config)
        
        # 注册测试处理器
        def test_handler(payload):
            return {"processed": True, "data": payload}
        
        queue.register_handler("test_topic", test_handler)
        
        # 验证处理器注册
        if queue._context:
            assert "test_topic" in queue._context.handlers
            assert queue._context.handlers["test_topic"] == test_handler


@pytest.mark.integration 
class TestRedisVersionCompatibility:
    """Redis版本兼容性测试"""
    
    @pytest.mark.asyncio
    async def test_redis8_specific_features(self):
        """测试Redis 8.x特有功能"""
        client = aioredis.Redis(host="localhost", port=6378, db=1, decode_responses=True)
        
        try:
            # 测试Redis 8.x的改进功能
            info = await client.info("server")
            redis_version = info.get("redis_version", "")
            
            # 验证版本
            assert redis_version.startswith("8.") or redis_version.startswith("7.")
            
            # 测试基础数据结构操作
            await client.hset("test_hash", mapping={"field1": "value1", "field2": "value2"}) # type: ignore
            hash_len = await client.hlen("test_hash") # type: ignore
            assert hash_len == 2
            
        finally:
            await client.flushdb()
            await client.aclose()
    
    @pytest.mark.asyncio
    async def test_redis6_compatibility(self):
        """测试Redis 6.x兼容性"""
        client = aioredis.Redis(host="localhost", port=6376, db=1, decode_responses=True)
        
        try:
            # 测试Redis 6.x功能
            info = await client.info("server")
            redis_version = info.get("redis_version", "")
            
            # 验证版本
            assert redis_version.startswith("6.") or redis_version.startswith("7.")
            
            # 测试流数据结构（Redis 6.x特性）
            stream_id = await client.xadd("test_stream", {"message": "hello", "timestamp": time.time()})
            assert stream_id is not None
            
            stream_length = await client.xlen("test_stream")
            assert stream_length == 1
            
        finally:
            await client.flushdb()
            await client.aclose()
    
    @pytest.mark.asyncio
    async def test_cross_version_data_compatibility(self):
        """测试跨版本数据兼容性"""
        client8 = aioredis.Redis(host="localhost", port=6378, db=1, decode_responses=True)
        client6 = aioredis.Redis(host="localhost", port=6376, db=1, decode_responses=True)
        
        try:
            # 在Redis 8.x中写入数据
            await client8.set("compat_test", "data_from_redis8")
            await client8.lpush("compat_list", "item1", "item2", "item3") # type: ignore
            await client8.hset("compat_hash", mapping={"key1": "value1", "key2": "value2"}) # type: ignore
            
            # 验证数据格式一致性（两个Redis实例独立，这里主要测试操作兼容性）
            value8 = await client8.get("compat_test")
            assert value8 == "data_from_redis8"
            
            # 在Redis 6.x中执行相同操作
            await client6.set("compat_test", "data_from_redis6")
            await client6.lpush("compat_list", "item1", "item2", "item3") # type: ignore    
            await client6.hset("compat_hash", mapping={"key1": "value1", "key2": "value2"}) # type: ignore  
            
            value6 = await client6.get("compat_test")
            assert value6 == "data_from_redis6"
            
            # 验证数据结构操作一致性
            list_len_8 = await client8.llen("compat_list") # type: ignore
            list_len_6 = await client6.llen("compat_list") # type: ignore
            
            assert list_len_8 == list_len_6 == 3
            
            hash_len_8 = await client8.hlen("compat_hash") # type: ignore
            hash_len_6 = await client6.hlen("compat_hash") # type: ignore
            
            assert hash_len_8 == hash_len_6 == 2
            
        finally:
            await client8.flushdb()
            await client6.flushdb()
            await client8.aclose()
            await client6.aclose()