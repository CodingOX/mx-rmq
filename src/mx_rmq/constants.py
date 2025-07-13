"""
Redis键名常量定义
提供类型安全的键名管理，避免字符串魔数分散在代码中
"""

from enum import Enum


class GlobalKeys(str, Enum):
    """全局Redis键名枚举 - 适用于整个系统的全局数据结构"""

    # 消息存储相关
    PAYLOAD_MAP = "payload:map"  # Hash: 存储消息内容和队列映射

    # 过期监控相关
    EXPIRE_MONITOR = "expire:monitor"  # ZSet: 全局过期任务监控

    # 延时任务相关
    DELAY_TASKS = "delay:tasks"  # ZSet: 全局延时任务队列

    # 死信队列相关
    DLQ_QUEUE = "dlq:queue"  # List: 死信队列
    DLQ_PAYLOAD_MAP = "dlq:payload:map"  # Hash: 死信队列消息存储

    # 监控指标相关
    METRICS = "metrics"  # Hash: 系统监控指标


class TopicKeys(str, Enum):
    """主题相关键名枚举 - 每个topic都会有这些队列"""

    PENDING = "pending"  # List: 待处理消息队列
    PROCESSING = "processing"  # List: 处理中消息队列


class KeyNamespace:
    """键名命名空间工具类 - 提供便捷的键名生成方法"""

    @staticmethod
    def get_topic_key_description(topic: str, key_type: TopicKeys) -> str:
        """
        获取主题键的描述信息

        Args:
            topic: 主题名称
            key_type: 键类型

        Returns:
            键的完整描述
        """
        descriptions = {
            TopicKeys.PENDING: f"主题 {topic} 的待处理消息队列",
            TopicKeys.PROCESSING: f"主题 {topic} 的处理中消息队列",
        }
        return descriptions.get(key_type, f"主题 {topic} 的 {key_type.value} 队列")

    @staticmethod
    def get_global_key_description(key_type: GlobalKeys) -> str:
        """
        获取全局键的描述信息

        Args:
            key_type: 全局键类型

        Returns:
            键的描述信息
        """
        descriptions = {
            GlobalKeys.PAYLOAD_MAP: "全局消息内容存储Hash",
            GlobalKeys.EXPIRE_MONITOR: "全局过期监控ZSet",
            GlobalKeys.DELAY_TASKS: "全局延时任务ZSet",
            GlobalKeys.DLQ_QUEUE: "死信队列List",
            GlobalKeys.DLQ_PAYLOAD_MAP: "死信队列消息存储Hash",
            GlobalKeys.METRICS: "系统监控指标Hash",
        }
        return descriptions.get(key_type, f"全局键: {key_type.value}")
