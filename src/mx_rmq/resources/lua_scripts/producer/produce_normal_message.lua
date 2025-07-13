-- produce_normal_message.lua
-- 原子性生产普通消息
-- KEYS[1]: payload_map
-- KEYS[2]: {topic}:pending
-- KEYS[3]: all_expire_monitor
-- ARGV[1]: message_id
-- ARGV[2]: payload (JSON string)
-- ARGV[3]: topic
-- ARGV[4]: expire_time
-- ARGV[5]: is_urgent ("1" for high priority, "0" for normal/low)

local payload_map = KEYS[1]
local pending_queue = KEYS[2] 
local expire_monitor = KEYS[3]

local id = ARGV[1]
local payload = ARGV[2]
local topic = ARGV[3]
local expire_time = ARGV[4]
local is_urgent = ARGV[5]

-- 原子性插入消息数据
redis.call('HSET', payload_map, id, payload)
redis.call('HSET', payload_map, id..':queue', topic)

-- 添加到过期监控
redis.call('ZADD', expire_monitor, expire_time, id)

-- 根据优先级插入队列
if is_urgent == '1' then
    -- 高优先级消息插入队列右边（优先被处理）
    redis.call('RPUSH', pending_queue, id)
else
    -- 普通/低优先级消息插入队列左边
    redis.call('LPUSH', pending_queue, id)
end

return 'OK' 