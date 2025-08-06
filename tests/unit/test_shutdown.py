"""测试优雅停机功能"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.mx_rmq import RedisMessageQueue, MQConfig
from src.mx_rmq.core import QueueContext


class TestShutdown:
    """停机功能测试类"""

    @pytest.mark.asyncio
    async def test_stop_basic_functionality(self):
        """测试stop()方法的基本功能"""
        config = MQConfig()
        queue = RedisMessageQueue(config)
        
        # 模拟队列正在运行
        queue._background_task = AsyncMock()
        queue._background_task.done.return_value = False
        queue._context = MagicMock(spec=QueueContext)
        queue._context.running = True
        
        # 模拟is_running()返回True，这样才会执行停机逻辑
        with patch.object(queue, 'is_running', return_value=True):
            with patch.object(queue, '_graceful_shutdown', new_callable=AsyncMock) as mock_graceful:
                with patch.object(queue, 'cleanup', new_callable=AsyncMock) as mock_cleanup:
                    await queue.stop()
                    
                    # 验证调用了优雅停机
                    mock_graceful.assert_called_once()
                    # 验证清理了资源
                    mock_cleanup.assert_called_once()
                    # 验证重置了状态
                    assert queue._background_task is None
                    assert queue._start_time is None

    @pytest.mark.asyncio
    async def test_graceful_shutdown_process(self):
        """测试_graceful_shutdown()方法"""
        config = MQConfig()
        queue = RedisMessageQueue(config)
        
        # 创建模拟的上下文
        mock_context = MagicMock(spec=QueueContext)
        mock_context.shutting_down = False
        mock_context.shutdown_event = AsyncMock()
        queue._context = mock_context
        
        # 创建模拟的监控服务
        mock_monitor_service = AsyncMock()
        queue._monitor_service = mock_monitor_service
        
        with patch.object(queue, '_cleanup_tasks', new_callable=AsyncMock) as mock_cleanup_tasks:
            with patch.object(queue, '_wait_for_local_queue_empty', new_callable=AsyncMock) as mock_wait_queue:
                with patch.object(queue, '_wait_for_consumers_finish', new_callable=AsyncMock) as mock_wait_consumers:
                    await queue._graceful_shutdown()
                    
                    # 验证设置了停机状态
                    assert mock_context.shutting_down is True
                    # 验证设置了关闭事件
                    mock_context.shutdown_event.set.assert_called_once()
                    # 验证调用了各个清理步骤
                    mock_cleanup_tasks.assert_called_once()
                    mock_wait_queue.assert_called_once()
                    mock_wait_consumers.assert_called_once()

    @pytest.mark.asyncio
    async def test_is_running_status_check(self):
        """测试is_running()状态检查"""
        config = MQConfig()
        queue = RedisMessageQueue(config)
        
        # 测试未运行状态
        assert queue.is_running() is False
        
        # 模拟运行状态
        queue._background_task = MagicMock()
        queue._background_task.done.return_value = False
        queue._context = MagicMock(spec=QueueContext)
        queue._context.running = True
        
        assert queue.is_running() is True
        
        # 测试任务完成状态
        queue._background_task.done.return_value = True
        assert queue.is_running() is False
        
        # 测试上下文未运行状态
        queue._background_task.done.return_value = False
        queue._context.running = False
        assert queue.is_running() is False

    @pytest.mark.asyncio
    async def test_shutdown_status_changes(self):
        """测试优雅停机过程中的状态变化"""
        config = MQConfig()
        queue = RedisMessageQueue(config)
        
        # 创建模拟的上下文
        mock_context = MagicMock(spec=QueueContext)
        mock_context.shutting_down = False
        mock_context.shutdown_event = AsyncMock()
        queue._context = mock_context
        
        # 模拟监控服务
        queue._monitor_service = AsyncMock()
        
        # 模拟其他方法
        with patch.object(queue, '_cleanup_tasks', new_callable=AsyncMock):
            with patch.object(queue, '_wait_for_local_queue_empty', new_callable=AsyncMock):
                with patch.object(queue, '_wait_for_consumers_finish', new_callable=AsyncMock):
                    # 验证停机前状态
                    assert mock_context.shutting_down is False
                    
                    await queue._graceful_shutdown()
                    
                    # 验证停机后状态
                    assert mock_context.shutting_down is True

    @pytest.mark.asyncio
    async def test_shutdown_timeout_handling(self):
        """测试停机超时处理"""
        config = MQConfig()
        queue = RedisMessageQueue(config)
        
        # 创建模拟的上下文
        mock_context = MagicMock(spec=QueueContext)
        mock_context.shutting_down = False
        mock_context.shutdown_event = AsyncMock()
        queue._context = mock_context
        
        # 模拟监控服务超时
        mock_monitor_service = AsyncMock()
        mock_monitor_service.stop_delay_processing.side_effect = asyncio.TimeoutError()
        queue._monitor_service = mock_monitor_service
        
        with patch.object(queue, '_cleanup_tasks', new_callable=AsyncMock):
            with patch.object(queue, '_wait_for_local_queue_empty', new_callable=AsyncMock):
                with patch.object(queue, '_wait_for_consumers_finish', new_callable=AsyncMock):
                    # 应该能正常完成，即使有超时
                    await queue._graceful_shutdown()
                    
                    # 验证仍然设置了停机状态
                    assert mock_context.shutting_down is True

    @pytest.mark.asyncio
    async def test_async_context_manager_shutdown(self):
        """测试异步上下文管理器的停机"""
        config = MQConfig()
        
        with patch('src.mx_rmq.queue.RedisConnectionManager') as mock_conn_mgr:
            mock_conn_mgr.return_value.initialize_connection = AsyncMock()
            
            with patch('src.mx_rmq.storage.LuaScriptManager') as mock_script_mgr:
                mock_script_mgr.return_value.load_scripts = AsyncMock(return_value={})
                
                with patch.object(RedisMessageQueue, 'stop', new_callable=AsyncMock) as mock_stop:
                    async with RedisMessageQueue(config) as queue:
                        # 模拟运行状态
                        queue._background_task = MagicMock()
                        queue._background_task.done.return_value = False
                        queue._context = MagicMock(spec=QueueContext)
                        queue._context.running = True
                    
                    # 验证调用了stop方法
                    mock_stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_background_task_cancellation(self):
        """测试后台任务的取消和清理"""
        config = MQConfig()
        queue = RedisMessageQueue(config)
        
        # 创建模拟的后台任务
        mock_task = MagicMock()
        mock_task.done.return_value = False
        mock_task.cancel = MagicMock()
        # 模拟await操作
        mock_task.__await__ = MagicMock(return_value=iter([]))
        queue._background_task = mock_task
        
        # 模拟上下文
        queue._context = MagicMock(spec=QueueContext)
        queue._context.running = True
        
        # 模拟is_running()返回True，这样才会执行停机逻辑
        with patch.object(queue, 'is_running', return_value=True):
            with patch.object(queue, '_graceful_shutdown', new_callable=AsyncMock):
                with patch.object(queue, 'cleanup', new_callable=AsyncMock):
                    await queue.stop()
                    
                    # 验证取消了后台任务
                    mock_task.cancel.assert_called_once()

    @pytest.mark.asyncio
    async def test_wait_for_local_queue_empty(self):
        """测试本地队列清空等待"""
        config = MQConfig()
        queue = RedisMessageQueue(config)
        
        # 模拟队列从非空到空的过程
        queue._task_queue = MagicMock()
        empty_states = [False, False, True]  # 前两次非空，第三次为空
        queue._task_queue.empty.side_effect = empty_states
        
        with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
            await queue._wait_for_local_queue_empty()
            
            # 验证等待了适当的次数
            assert mock_sleep.call_count == 2  # 前两次非空时会sleep

    @pytest.mark.asyncio
    async def test_wait_for_consumers_finish(self):
        """测试消费者完成等待"""
        config = MQConfig()
        queue = RedisMessageQueue(config)
        
        # 创建模拟的上下文和Redis
        mock_context = MagicMock(spec=QueueContext)
        mock_context.handlers = {'topic1': MagicMock(), 'topic2': MagicMock()}
        mock_redis = AsyncMock()
        mock_context.redis = mock_redis
        queue._context = mock_context
        
        # 模拟processing队列长度从非零到零
        mock_redis.llen.side_effect = [2, 1, 0, 0]  # topic1: 2->0, topic2: 1->0
        
        with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
            await queue._wait_for_consumers_finish(10)
            
            # 验证检查了processing队列
            assert mock_redis.llen.call_count >= 2

    @pytest.mark.asyncio
    async def test_shutdown_exception_handling(self):
        """测试停机过程中的异常处理"""
        config = MQConfig()
        queue = RedisMessageQueue(config)
        
        # 模拟上下文
        mock_context = MagicMock(spec=QueueContext)
        mock_context.shutting_down = False
        mock_context.shutdown_event = AsyncMock()
        queue._context = mock_context
        
        # 模拟监控服务抛出异常
        mock_monitor_service = AsyncMock()
        mock_monitor_service.stop_delay_processing.side_effect = Exception("测试异常")
        queue._monitor_service = mock_monitor_service
        
        with patch.object(queue, '_cleanup_tasks', new_callable=AsyncMock):
            with patch.object(queue, '_wait_for_local_queue_empty', new_callable=AsyncMock):
                with patch.object(queue, '_wait_for_consumers_finish', new_callable=AsyncMock):
                    # 应该能正常完成，即使有异常
                    await queue._graceful_shutdown()
                    
                    # 验证仍然设置了停机状态
                    assert mock_context.shutting_down is True

    @pytest.mark.asyncio
    async def test_duplicate_stop_calls(self):
        """测试重复停机调用的处理"""
        config = MQConfig()
        queue = RedisMessageQueue(config)
        
        # 第一次调用：队列未运行
        with patch.object(queue, 'is_running', return_value=False):
            await queue.stop()
            # 应该正常返回，不抛出异常
        
        # 第二次调用：模拟正在运行然后停止
        queue._background_task = AsyncMock()
        queue._background_task.done.return_value = False
        queue._context = MagicMock(spec=QueueContext)
        queue._context.running = True
        
        with patch.object(queue, '_graceful_shutdown', new_callable=AsyncMock):
            with patch.object(queue, 'cleanup', new_callable=AsyncMock):
                await queue.stop()
                
                # 第三次调用：队列已经停止
                queue._background_task = None
                queue._context.running = False
                
                await queue.stop()
                # 应该正常返回，不抛出异常