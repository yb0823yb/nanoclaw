"""
OpenAI 兼容 Provider 实现

通过 OpenAI SDK（AsyncOpenAI）接入所有兼容 OpenAI Chat Completions API 的服务，
包括 OpenAI 官方、硅基流动、DeepSeek 等。
"""

import json
from typing import Any, Optional

from openai import AsyncOpenAI

from .base import LLMProvider, LLMResponse, ToolCallRequest


class OpenAICompatProvider(LLMProvider):
    """
    OpenAI 兼容 Provider。

    使用 AsyncOpenAI 客户端调用 Chat Completions API，
    并将返回结果统一转换为 LLMResponse 格式。
    """

    def __init__(self, api_key: str, base_url: str, model: str) -> None:
        """
        初始化 OpenAI 兼容 Provider。

        参数:
            api_key:  API 密钥
            base_url: API 基础 URL（如 https://api.openai.com/v1）
            model:    默认使用的模型名称
        """
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        model: str | None = None,
    ) -> LLMResponse:
        """
        发送聊天请求并返回标准化响应。

        实现要点:
            - 仅当 tools 非空时才传 tools 和 tool_choice="auto"，
              避免硅基流动等 API 在 tool_choice 存在而 tools 为空时报错。
            - 容错获取 reasoning_content（可能位于 tool_call 或 message 顶层）。
            - 捕获所有异常，返回 finish_reason="error" 的 LLMResponse。
        """
        target_model = model or self.model

        # 动态构建请求参数
        request_params: dict[str, Any] = {
            "model": target_model,
            "messages": messages,
        }

        # 只有 tools 非空时才传 tools 和 tool_choice
        if tools:
            request_params["tools"] = tools
            request_params["tool_choice"] = "auto"

        try:
            response = await self.client.chat.completions.create(**request_params)
        except Exception as exc:
            return LLMResponse(
                content=f"API 调用失败: {exc}",
                finish_reason="error",
            )

        # 解析响应
        choice = response.choices[0]
        message = choice.message

        # 提取 message 顶层的 reasoning_content（部分模型放在此处）
        message_reasoning = getattr(message, "reasoning_content", None)

        # 转换 tool_calls
        tool_call_requests: list[ToolCallRequest] = []
        if message.tool_calls:
            for tc in message.tool_calls:
                # 容错获取 reasoning_content（优先 tool_call 自身，其次 message 顶层）
                reasoning = getattr(tc, "reasoning_content", None) or message_reasoning

                # 解析 arguments JSON 字符串为 dict
                try:
                    args_dict = json.loads(tc.function.arguments) if tc.function.arguments else {}
                except json.JSONDecodeError:
                    args_dict = {"_raw": tc.function.arguments}

                tool_call_requests.append(
                    ToolCallRequest(
                        id=tc.id,
                        name=tc.function.name or "",
                        arguments=args_dict,
                        reasoning_content=reasoning,
                    )
                )

        # 提取 usage 信息
        usage: dict[str, Any] = {}
        if response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }

        return LLMResponse(
            content=message.content,
            tool_calls=tool_call_requests,
            finish_reason=choice.finish_reason or "stop",
            usage=usage,
        )
