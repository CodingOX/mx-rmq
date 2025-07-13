-- produce_delay_message.lua
-- 原子性生产延时消息
-- KEYS[1]: payload_map
-- KEYS[2]: delay_tasks
-- ARGV[1]: message_id
-- ARGV[2]: payload (JSON string)
-- ARGV[3]: topic
-- ARGV[4]: execute_time

local payload_map = KEYS[1]
local delay_tasks = KEYS[2]

local id = ARGV[1]
local payload = ARGV[2]
local topic = ARGV[3]
local execute_time = ARGV[4]

-- 原子性插入消息数据
redis.call('HSET', payload_map, id, payload)
redis.call('HSET', payload_map, id..':queue', topic)

-- 添加到延时任务队列
redis.call('ZADD', delay_tasks, execute_time, id)

return 'OK' 