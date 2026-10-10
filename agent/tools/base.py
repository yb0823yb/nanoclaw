"""
Tool 抽象基类模块

定义所有 Agent 工具的通用接口，兼容 OpenAI Function Calling 格式。
"""

from abc import ABC, abstractmethod
from typing import Any

class Tool(ABC):
    """
    Agent 工具的抽象基类。

    所有具体工具必须继承此类，并实现 name、description、parameters 三个属性
    以及 execute 方法。to_function_definition() 方法会自动生成符合 OpenAI
    Function Calling 规范的 JSON 格式定义。

    使用示例:
        class GetWeatherTool(Tool):
            @property
            def name(self) -> str:
                return "get_weather"

            @property
            def description(self) -> str:
                return "获取指定城市的天气信息"

            @property
            def parameters(self) -> dict:
                return {
                    "type": "object",
                    "properties": {
                        "city": {"type": "string", "description": "城市名称"}
                    },
                    "required": ["city"]
                }

            async def execute(self, **kwargs) -> str:
                city = kwargs.get("city")
                return f"{city} 的天气是晴天"
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """工具名称，用于标识和调用此工具。"""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """工具功能描述，帮助 LLM 理解何时使用该工具。"""
        pass

    @property
    @abstractmethod
    def parameters(self) -> dict:
        """
        工具参数定义，遵循 JSON Schema 格式。

        用于描述工具所需的输入参数及其类型、约束等信息。
        格式示例:
            {
                "type": "object",
                "properties": {
                    "param1": {"type": "string", "description": "参数说明"}
                },
                "required": ["param1"]
            }
        """
        pass

    @abstractmethod
    async def execute(self, **kwargs: Any) -> str:
        """
        执行工具的核心逻辑。

        Args:
            **kwargs: 由 LLM 根据 parameters 定义生成的参数。

        Returns:
            工具执行结果的字符串表示，将返回给 LLM。
        """
        pass

    def to_function_definition(self) -> dict:
        """
        生成 OpenAI Function Calling 格式的工具定义。

        将 name、description、parameters 组装成 OpenAI API 所需的 JSON 格式。

        Returns:
            符合 OpenAI Function Calling 规范的字典，格式如下:
            {
                "type": "function",
                "function": {
                    "name": "工具名",
                    "description": "工具描述",
                    "parameters": {参数定义}
                }
            }
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters
            }
        }
