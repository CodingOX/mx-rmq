-- retry_message.lua
-- 重试消息，重新调度到延时队列
-- KEYS[1]: payload_map
-- KEYS[2]: delay_tasks
-- KEYS[3]: all_expire_monitor
-- KEYS[4]: {topic}:processing (可选，用于清理processing队列)
-- ARGV[1]: message_id
-- ARGV[2]: updated_payload (JSON string)
-- ARGV[3]: retry_delay (seconds)
-- ARGV[4]: topic (可选，用于构建processing队列key)

local payload_map = KEYS[1]
local delay_tasks = KEYS[2]
local expire_monitor = KEYS[3]
local processing_queue = KEYS[4]  -- 新增：processing队列

local message_id = ARGV[1]
local updated_payload = ARGV[2]
local retry_delay = ARGV[3]
local topic = ARGV[4]  -- 新增：topic参数

-- 获取Redis服务端当前时间（毫秒时间戳）- 与其他脚本保持一致
local time_result = redis.call('TIME')
local current_time = tonumber(time_result[1]) * 1000 + math.floor(tonumber(time_result[2]) / 1000)

-- 计算执行时间（retry_delay是秒数，需要转换为毫秒）
local execute_time = current_time + tonumber(retry_delay) * 1000

-- 更新消息内容
redis.call('HSET', payload_map, message_id, updated_payload)

-- 添加到延时队列进行重试
redis.call('ZADD', delay_tasks, execute_time, message_id)
redis.call('ZREM', expire_monitor, message_id)

-- 重要：从processing队列中移除消息ID
-- 因为消息已经重新调度到延时队列，不应该继续在processing队列中
if processing_queue and processing_queue ~= '' then
    redis.call('LREM', processing_queue, 1, message_id)
end

return 'OK'