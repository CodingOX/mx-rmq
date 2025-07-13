-- retry_message.lua
-- 重试消息，重新调度到延时队列
-- KEYS[1]: payload_map
-- KEYS[2]: delay_tasks
-- ARGV[1]: message_id
-- ARGV[2]: updated_payload (JSON string)
-- ARGV[3]: retry_delay (seconds)
-- ARGV[4]: current_time

local payload_map = KEYS[1]
local delay_tasks = KEYS[2]

local message_id = ARGV[1]
local updated_payload = ARGV[2]
local retry_delay = ARGV[3]
local current_time = ARGV[4]

-- 计算执行时间
local execute_time = current_time + retry_delay

-- 更新消息内容
redis.call('HSET', payload_map, message_id, updated_payload)

-- 添加到延时队列进行重试
redis.call('ZADD', delay_tasks, execute_time, message_id)

return 'OK' 