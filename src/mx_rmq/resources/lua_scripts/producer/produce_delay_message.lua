-- produce_delay_message.lua
-- 原子性生产延时消息 + 智能pubsub通知
-- KEYS[1]: payload_map
-- KEYS[2]: delay_tasks
-- KEYS[3]: pubsub_channel (可选，如果提供则发送通知)
-- ARGV[1]: message_id
-- ARGV[2]: payload (JSON string)
-- ARGV[3]: topic
-- ARGV[4]: execute_time

local payload_map = KEYS[1]
local delay_tasks = KEYS[2]
local pubsub_channel = KEYS[3]

local id = ARGV[1]
local payload = ARGV[2]
local topic = ARGV[3]
local execute_time = tonumber(ARGV[4])

-- 获取Redis服务器当前时间（毫秒）
local redis_time = redis.call('TIME')
local current_time = tonumber(redis_time[1]) * 1000 + math.floor(tonumber(redis_time[2]) / 1000)

-- 获取当前最早的任务（在插入新任务之前）
-- 索引1: "task_id_123" (任务ID)  索引2: "1672531200000" (执行时间戳)
local current_earliest = redis.call('ZRANGE', delay_tasks, 0, 0, 'WITHSCORES')

-- 原子性插入消息数据
redis.call('HSET', payload_map, id, payload)
redis.call('HSET', payload_map, id..':queue', topic)

-- 添加到延时任务队列
redis.call('ZADD', delay_tasks, execute_time, id)

-- 智能通知：发送通知的条件
if pubsub_channel and pubsub_channel ~= '' then
    local should_notify = false
    local notify_time = execute_time
    
    -- 条件1：第一个延时任务，冷启动，所以必须启动
    if #current_earliest == 0 then
        should_notify = true
    -- 条件2：新任务比当前最早任务更早，需要通知  
    elseif execute_time < tonumber(current_earliest[2]) then
        should_notify = true
    -- 条件3：检查是否有任务已到期（包括新插入的任务）
    else
        -- 获取所有到期的任务
        local expired_tasks = redis.call('ZRANGE', delay_tasks, 0, current_time, 'BYSCORE', 'LIMIT', 0, 1)
        if #expired_tasks > 0 then
            should_notify = true
            notify_time = current_time  -- 立即处理到期任务
        end
    end
    
    -- 这个才是关键
    if should_notify then
        redis.call('PUBLISH', pubsub_channel, notify_time)
    end
end

return 'OK' 