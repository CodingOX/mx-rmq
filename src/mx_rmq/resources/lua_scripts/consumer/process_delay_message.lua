-- process_delay_messages.lua
-- 处理到期的延时消息，将其移动到对应的pending队列
-- KEYS[1]: delay_tasks
-- KEYS[2]: payload_map  
-- ARGV[1]: current_time
-- ARGV[2]: batch_size

local delay_tasks = KEYS[1]
local payload_map = KEYS[2]

local current_time = ARGV[1]
local batch_size = ARGV[2]

-- 获取到期的延时任务
local ready_tasks = redis.call('ZRANGE', delay_tasks, 0, current_time, 'BYSCORE', 'LIMIT', 0, batch_size)

local results = {}

for i = 1, #ready_tasks do
    local task_id = ready_tasks[i]
    
    -- 获取队列名称
    local queue_name = redis.call('HGET', payload_map, task_id..':queue')
    
    if queue_name then
        -- 移动到对应的pending队列
        local pending_key = queue_name..':pending'
        redis.call('LPUSH', pending_key, task_id)
        
        -- 从延时队列中移除
        redis.call('ZREM', delay_tasks, task_id)
        
        -- 记录处理结果
        results[#results + 1] = {task_id, queue_name}
    else
        -- 如果找不到队列名，说明消息已被清理，直接移除
        redis.call('ZREM', delay_tasks, task_id)
    end
end

return results 