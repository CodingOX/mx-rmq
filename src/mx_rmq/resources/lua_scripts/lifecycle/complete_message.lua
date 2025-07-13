-- complete_message.lua
-- 原子性完成消息处理，清理相关数据
-- KEYS[1]: payload_map
-- KEYS[2]: {topic}:processing
-- KEYS[3]: all_expire_monitor
-- ARGV[1]: message_id

local payload_map = KEYS[1]
local processing_queue = KEYS[2]
local expire_monitor = KEYS[3]

local message_id = ARGV[1]

-- 原子性清理所有相关数据
-- 从processing队列中移除
redis.call('LREM', processing_queue, 1, message_id)

-- 从过期监控中移除
redis.call('ZREM', expire_monitor, message_id)

-- 从payload存储中删除消息数据和队列信息
redis.call('HDEL', payload_map, message_id, message_id..':queue')

return 'OK' 