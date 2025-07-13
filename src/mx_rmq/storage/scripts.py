"""
Lua脚本管理模块
负责加载和管理Redis Lua脚本
"""

import importlib.resources as pkg_resources
from pathlib import Path

import redis.asyncio as aioredis
from redis.commands.core import AsyncScript

from ..logging import LoggerService


class LuaScriptManager:
    """Lua脚本管理器"""

    def __init__(self, redis: aioredis.Redis, logger_service: LoggerService) -> None:
        """
        初始化脚本管理器

        Args:
            redis: Redis连接实例
            logger_service: 日志服务实例
        """
        self.redis = redis
        self.logger_service = logger_service

    async def load_scripts(self) -> dict[str, AsyncScript]:
        """
        加载所有Lua脚本

        Returns:
            脚本名称到注册后脚本对象的映射
        """
        script_files = {
            "produce_normal": "producer/produce_normal_message.lua",
            "produce_delay": "producer/produce_delay_message.lua",
            "process_delay": "consumer/process_delay_message.lua",
            "complete_message": "lifecycle/complete_message.lua",
            "handle_timeout": "management/handle_timeout_message.lua",
            "retry_message": "lifecycle/retry_message.lua",
            "move_to_dlq": "management/move_to_dlq.lua",
        }

        lua_scripts = {}
        for script_name, filename in script_files.items():
            script_content = await self._load_script_content(filename)
            # 注册脚本到Redis
            lua_scripts[script_name] = self.redis.register_script(script_content)

        self.logger_service.logger.info("Lua脚本加载完成", count=len(lua_scripts))
        return lua_scripts

    async def _load_script_content(self, filename: str) -> str:
        """
        加载单个Lua脚本内容

        Args:
            filename: 脚本文件相对路径（如: "producer/produce_normal_message.lua"）

        Returns:
            脚本内容

        Raises:
            FileNotFoundError: 当脚本文件不存在时
        """
        # 使用现代化的importlib.resources方式加载包内资源
        try:
            # 构建资源路径：mx_rmq.resources.lua_scripts
            script_parts = filename.split("/")
            if len(script_parts) != 2:
                raise ValueError(
                    f"脚本路径格式错误，应为 'category/script.lua': {filename}"
                )

            category, script_name = script_parts
            resource_package = f"mx_rmq.resources.lua_scripts.{category}"

            # 使用importlib.resources读取资源文件
            try:
                with (
                    pkg_resources.files(resource_package)
                    .joinpath(script_name)
                    .open("r", encoding="utf-8") as f
                ):
                    return f.read()
            except (FileNotFoundError, ModuleNotFoundError):
                # 如果importlib.resources失败，回退到文件路径方式
                script_path = (
                    Path(__file__).parent.parent
                    / "resources"
                    / "lua_scripts"
                    / filename
                )
                if script_path.exists():
                    with open(script_path, encoding="utf-8") as f:
                        return f.read()
                raise

        except Exception as e:
            # 开发环境回退：尝试从项目根目录加载（用于开发时的向后兼容）
            try:
                script_dir = Path(__file__).parent.parent.parent.parent / "lua_scripts"
                script_path = script_dir / filename

                if script_path.exists():
                    self.logger_service.logger.warning(
                        "使用开发环境回退路径加载Lua脚本",
                        script=filename,
                        path=str(script_path),
                    )
                    with open(script_path, encoding="utf-8") as f:
                        return f.read()
            except Exception:
                pass

            raise FileNotFoundError(  # noqa: B904
                f"无法加载Lua脚本文件: {filename}. "
                f"请确保脚本存在于 mx_rmq/resources/lua_scripts/ 目录中。原始错误: {e}"
            )
