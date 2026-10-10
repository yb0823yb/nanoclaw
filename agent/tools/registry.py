"""
工具注册表模块

负责统一管理所有工具的注册、查询和调用。
Agent 在初始化阶段将所有工具注册到 ToolRegistry，
运行时由 Agent 循环通过 registry 查找并执行工具。
"""

import logging
from typing import Any

from agent.tools.base import Tool

logger = logging.getLogger(__name__)


class ToolRegistry:
    """
    工具注册表。

    内部维护一个 {工具名: 工具实例} 的字典，提供以下能力：
      - register:        注册一个新工具
      - get_definitions: 批量输出 OpenAI function calling 格式的 JSON 列表
      - execute:         按名称查找并异步执行工具，带完整错误处理
      - list_tools:      列出所有已注册工具名称
    """

    def __init__(self) -> None:
        # 存储已注册的工具，key 为工具名，value 为工具实例
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """
        注册一个工具。

        若同名工具已存在，会打印警告并覆盖。
        """
        if tool.name in self._tools:
            logger.warning("工具 '%s' 已存在，将被覆盖", tool.name)
        self._tools[tool.name] = tool
        logger.info("已注册工具: %s", tool.name)

    def get_definitions(self) -> list[dict]:
        """
        获取所有工具的 OpenAI function calling 格式定义列表。

        返回格式示例：
        [
            {
                "type": "function",
                "function": {"name": "...", "description": "...", "parameters": {...}}
            },
            ...
        ]

        该列表可直接作为 LLM 请求的 tools 参数。
        """
        return [tool.to_function_definition() for tool in self._tools.values()]

    async def execute(self, name: str, arguments: dict[str, Any]) -> str:
        """
        根据工具名称查找并执行。

        参数:
            name:      工具名称
            arguments: 传给工具 execute 方法的 keyword 参数

        返回:
            工具执行的字符串结果，或错误信息
        """
        if name not in self._tools:
            available = ", ".join(self._tools.keys()) or "（无）"
            return f"错误：工具 '{name}' 不存在。可用工具：{available}"

        tool = self._tools[name]
        try:
            result = await tool.execute(**arguments)
            return result
        except Exception as e:
            logger.exception("工具 '%s' 执行失败", name)
            return f"错误：工具 '{name}' 执行失败 - {e}"

    def list_tools(self) -> list[str]:
        """返回所有已注册的工具名称列表"""
        return list(self._tools.keys())
