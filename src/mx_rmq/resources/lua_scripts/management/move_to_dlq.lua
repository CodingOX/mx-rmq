-- move_to_dlq.lua
-- 将消息移入死信队列
-- KEYS[1]: dlq_payload_map
-- KEYS[2]: dlq (死信队列)
-- KEYS[3]: all_expire_monitor
-- KEYS[4]: payload_map
-- ARGV[1]: message_id
-- ARGV[2]: updated_payload (JSON string)

local dlq_payload_map = KEYS[1]
local dlq = KEYS[2]
local expire_monitor = KEYS[3]
local payload_map = KEYS[4]

local msg_id = ARGV[1]
local updated_payload = ARGV[2]

-- 将消息移入死信队列存储
redis.call('HSET', dlq_payload_map, msg_id, updated_payload)

-- 从原始队列信息复制到死信队列
local queue_name = redis.call('HGET', payload_map, msg_id..':queue')
if queue_name then
    redis.call('HSET', dlq_payload_map, msg_id..':queue', queue_name)
end

-- 添加到死信队列列表
redis.call('LPUSH', dlq, msg_id)

-- 从过期监控中移除（死信队列消息不再监控过期）
redis.call('ZREM', expire_monitor, msg_id)

-- 从原始payload存储中删除
redis.call('HDEL', payload_map, msg_id, msg_id..':queue')

return 'OK' 