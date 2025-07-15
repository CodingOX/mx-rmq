-- handle_parse_error.lua
-- 处理消息序列化失败，将原始数据转移到专用错误存储
-- KEYS[1]: error:parse:payload:map    (解析错误信息存储)
-- KEYS[2]: error:parse:queue          (解析错误消息队列)
-- KEYS[3]: {topic}:processing         (处理中队列)
-- KEYS[4]: expire:monitor             (过期监控)
-- KEYS[5]: payload:map                (原始消息存储)
-- ARGV[1]: message_id                 (消息ID)
-- ARGV[2]: original_payload           (原始损坏的JSON)
-- ARGV[3]: topic                      (消息主题)
-- ARGV[4]: error_message              (错误信息，最大20字符)
-- ARGV[5]: timestamp                  (发生时间戳)

local error_payload_map = KEYS[1]
local error_queue = KEYS[2]
local processing_key = KEYS[3]
local expire_monitor = KEYS[4]
local payload_map = KEYS[5]

local message_id = ARGV[1]
local original_payload = ARGV[2]
local topic = ARGV[3]
local error_message = ARGV[4]
local timestamp = ARGV[5]

-- 限制错误信息长度为20字符
if string.len(error_message) > 20 then
    error_message = string.sub(error_message, 1, 17) .. "..."
end

-- 构造错误信息对象 (JSON格式)
local error_info = string.format([[{
    "original_payload": %s,
    "error_type": "parse_error",
    "error_message": "%s",
    "topic": "%s",
    "timestamp": "%s",
    "message_id": "%s"
}]], 
    -- 对原始payload进行JSON转义
    original_payload and string.format('"%s"', string.gsub(original_payload, '"', '\\"')) or 'null',
    error_message,
    topic,
    timestamp,
    message_id
)

-- 原子性操作：存储错误信息并清理相关数据
-- 1. 存储到专用解析错误存储
redis.call('HSET', error_payload_map, message_id, error_info)
redis.call('LPUSH', error_queue, message_id)

-- 2. 清理相关数据
redis.call('LREM', processing_key, 1, message_id)
redis.call('ZREM', expire_monitor, message_id)
redis.call('HDEL', payload_map, message_id, message_id..':queue')

return 'OK' 