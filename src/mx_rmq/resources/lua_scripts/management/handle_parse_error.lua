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
-- ARGV[6]: expire_days                (过期天数，可选)
-- ARGV[7]: max_count                  (最大记录数，可选)
-- ARGV[8]: supports_hexpire           (是否支持HEXPIRE命令，"1"或"0"，可选)

-- 常量定义
local MAX_ERROR_MESSAGE_LENGTH = 20
local MAX_PAYLOAD_LENGTH = 4096  -- 限制payload长度避免内存问题
local CLEANUP_BATCH_SIZE = 100
local CLEANUP_EXTRA_COUNT = 50

-- 性能优化的JSON转义函数
local function json_escape_optimized(str)
    if not str then return 'null' end
    
    -- 截断过长的payload
    if #str > MAX_PAYLOAD_LENGTH then
        str = string.sub(str, 1, MAX_PAYLOAD_LENGTH) .. "...[truncated]"
    end
    
    -- 快速检查是否需要转义
    if not string.find(str, '["\\\n\r\t]') then
        return '"' .. str .. '"'
    end
    
    -- 只在需要时进行转义
    str = string.gsub(str, '\\', '\\\\')
    str = string.gsub(str, '"', '\\"')
    str = string.gsub(str, '\n', '\\n')
    str = string.gsub(str, '\r', '\\r')
    str = string.gsub(str, '\t', '\\t')
    
    return '"' .. str .. '"'
end

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
local expire_days = ARGV[6]
local max_count = ARGV[7]
local supports_hexpire = ARGV[8] == "1"

-- 限制错误信息长度（使用#操作符优化性能）
if #error_message > MAX_ERROR_MESSAGE_LENGTH then
    error_message = string.sub(error_message, 1, MAX_ERROR_MESSAGE_LENGTH - 3) .. "..."
end

-- 构造错误信息对象 (JSON格式，使用优化的转义函数)
local error_info = string.format([[{
    "original_payload": %s,
    "error_type": "parse_error",
    "error_message": "%s",
    "topic": "%s",
    "timestamp": "%s",
    "message_id": "%s"
}]], 
    json_escape_optimized(original_payload),
    error_message,
    topic,
    timestamp,
    message_id
)

-- 原子性操作：存储错误信息并清理相关数据
-- 1. 存储到专用解析错误存储
redis.call('HSET', error_payload_map, message_id, error_info)
redis.call('LPUSH', error_queue, message_id)

-- 2. 设置字段TTL（如果提供过期天数）
if expire_days and expire_days ~= "" then
    local ttl_seconds = tonumber(expire_days) * 24 * 3600
    
    if supports_hexpire then
        -- 直接调用HEXPIRE（Redis 7.4+支持）
        redis.call('HEXPIRE', error_payload_map, ttl_seconds, message_id)
    else
        -- 降级方案：为整个Hash设置过期时间
        -- 注意：这会影响所有错误记录，但至少保证了数据不会永久存在
        local existing_ttl = redis.call('TTL', error_payload_map)
        if existing_ttl == -1 then  -- 如果Hash没有设置过期时间
            redis.call('EXPIRE', error_payload_map, ttl_seconds)
        end
    end
end

-- 3. 数量限制清理（优化批量处理）
if max_count and max_count ~= "" then
    local queue_len = redis.call('LLEN', error_queue)
    local max_count_num = tonumber(max_count)
    
    -- 早期返回：如果不需要清理则直接跳过
    if queue_len <= max_count_num then
        goto cleanup_done
    end
    
    -- 批量清理：当队列长度超过限制且是批次大小的倍数时进行清理
    if queue_len % CLEANUP_BATCH_SIZE == 0 then
        local cleanup_count = queue_len - max_count_num + CLEANUP_EXTRA_COUNT
        
        -- 批量获取要删除的ID（减少Redis调用次数）
        local ids_to_delete = {}
        for i = 1, cleanup_count do
            local old_id = redis.call('RPOP', error_queue)
            if old_id then
                table.insert(ids_to_delete, old_id)
            else
                break  -- 队列已空
            end
        end
        
        -- 批量删除hash字段
        if #ids_to_delete > 0 then
            -- 兼容Lua 5.1/LuaJIT和Lua 5.4+
            local unpack_func = table.unpack or unpack
            redis.call('HDEL', error_payload_map, unpack_func(ids_to_delete))
        end
    end
    
    ::cleanup_done::
end

-- 4. 清理相关数据
redis.call('LREM', processing_key, 1, message_id)
redis.call('ZREM', expire_monitor, message_id)
redis.call('HDEL', payload_map, message_id, message_id..':queue')

return 'OK'