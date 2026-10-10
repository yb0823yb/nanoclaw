"""
LLM Provider 基础模块

定义 LLM 交互的核心数据结构：
  - ToolCallRequest: 工具调用请求
  - LLMResponse:     LLM 响应的标准化封装
  - LLMProvider:     Provider 抽象基类（所有 LLM 接入的"模具"）
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ToolCallRequest:
    """
    工具调用请求。

    当 LLM 决定调用某个工具时，会返回一个或多个此类对象。
    reasoning_content 字段用于保存支持"思考"功能的模型（如 Kimi-K2.5、DeepSeek-R1）
    在返回 tool_calls 时附带的推理过程。
    """

    id: str
    name: str
    arguments: dict[str, Any]
    reasoning_content: Optional[str] = None


@dataclass
class LLMResponse:
    """
    LLM 响应的标准化封装。

    统一不同 Provider 的返回格式，供 Agent 循环统一处理。
    """

    content: Optional[str]
    tool_calls: list[ToolCallRequest] = field(default_factory=list)
    finish_reason: str = "stop"
    usage: dict[str, Any] = field(default_factory=dict)

    @property
    def has_tool_calls(self) -> bool:
        """判断本次响应是否包含工具调用"""
        return len(self.tool_calls) > 0


class LLMProvider(ABC):
    """
    LLM Provider 抽象基类。

    所有 LLM 接入（OpenAI 兼容、Anthropic 等）都必须继承此类，
    并实现 chat() 方法。
    """

    @abstractmethod
    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        model: str | None = None,
        return_reasoning: bool = True,  # 关键！开启返回思考
    ) -> LLMResponse:
        """
        发送聊天请求并返回标准化响应。

        参数:
            messages: OpenAI 格式的消息列表
            tools:    可选，OpenAI 格式的 tools JSON 列表
            model:    可选，覆盖默认模型
        """
        ...
