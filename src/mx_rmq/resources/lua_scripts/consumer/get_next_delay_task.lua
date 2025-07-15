-- get_next_delay_task.lua
-- 获取下一个延时任务的状态和等待时间
-- 使用Redis服务器时间避免客户端时钟不一致问题
-- KEYS[1]: delay_tasks (延时任务ZSet)
-- 返回值：
--   NO_TASK: 没有延时任务
--   EXPIRED: 有任务且已过期，需要立即处理
--   WAITING: 有任务但未到期，返回等待毫秒数

local delay_tasks = KEYS[1]

-- 获取Redis服务器当前时间（毫秒）
local redis_time = redis.call('TIME')
local redis_current_time = tonumber(redis_time[1]) * 1000 + math.floor(tonumber(redis_time[2]) / 1000)

-- 获取最近的延时任务（按时间戳排序的第一个）
-- 返回值为 元素和 score
local earliest_task = redis.call('ZRANGE', delay_tasks, 0, 0, 'WITHSCORES')

-- 没有延时任务
if #earliest_task == 0 then
    return {'NO_TASK'}
end

-- lua 通过 1 开始
local task_id = earliest_task[1]
local earliest_time = tonumber(earliest_task[2])

-- 计算等待时间（毫秒）- 保持原生精度
local wait_milliseconds = earliest_time - redis_current_time

if wait_milliseconds <= 0 then
    -- 任务已过期，需要立即处理
    return {'EXPIRED', earliest_time, task_id}
else
    -- 任务未到期，返回等待毫秒数
    return {'WAITING', wait_milliseconds, earliest_time, task_id}
end 