-- handle_timeout_messages.lua
-- 处理过期消息，检测超时任务
-- KEYS[1]: all_expire_monitor
-- KEYS[2]: payload_map
-- ARGV[1]: current_time
-- ARGV[2]: batch_size

local expire_monitor = KEYS[1]
local payload_map = KEYS[2]

local current_time = ARGV[1]
local batch_size = ARGV[2]

-- 获取过期的消息ID
local expired_ids = redis.call('ZRANGE', expire_monitor, 0, current_time, 'BYSCORE', 'LIMIT', 0, batch_size)

local results = {}

for i = 1, #expired_ids do
    local msg_id = expired_ids[i]
    
    -- 获取消息和队列信息
    local payload = redis.call('HGET', payload_map, msg_id)
    local queue_name = redis.call('HGET', payload_map, msg_id..':queue')
    
    if payload and queue_name then
        local processing_key = queue_name..':processing'
        
        -- 检查是否在processing队列中
        local in_processing = redis.call('LPOS', processing_key, msg_id)
        
        if in_processing then
            -- 从processing队列中移除
            redis.call('LREM', processing_key, 1, msg_id)
        end
        
        -- 从过期监控中移除
        redis.call('ZREM', expire_monitor, msg_id)
        
        -- 返回超时的消息信息供后续处理
        results[#results + 1] = {msg_id, payload, queue_name}
    else
        -- 消息已被清理，直接从监控中移除
        redis.call('ZREM', expire_monitor, msg_id)
    end
end

return results 