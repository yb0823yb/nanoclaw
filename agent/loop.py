"""
Agent Loop 模块

实现 Agent 的核心运行循环：
  - 构建上下文 → 调用 LLM → 处理工具调用 → 循环直到得出最终回答
  - 防爆检测：防止工具陷入死循环
  - 会话历史：跨轮次保持对话上下文
"""

import json
import logging
from typing import Optional

from agent.context import ContextBuilder
from agent.tools.registry import ToolRegistry
from providers.base import LLMProvider, LLMResponse
from session.manager import SessionManager

logger = logging.getLogger(__name__)

# 防爆检测阈值
LOOP_WARNING_THRESHOLD = 10   # 警告阈值：提示模型可能陷入循环
LOOP_BREAK_THRESHOLD = 20     # 熔断阈值：强制终止执行
HISTORY_WINDOW_SIZE = 30      # 滑动窗口大小


class AgentLoop:
    """
    Agent 核心运行循环。

    负责协调 LLM Provider、工具注册表和上下文构建器，
    实现"思考-行动-观察"的 ReAct 循环。
    """

    def __init__(
        self,
        provider: LLMProvider,
        tools: ToolRegistry,
        context: ContextBuilder,
        model: str | None = None,
        max_iterations: int = 32,
        session_manager: SessionManager | None = None,
        session_key: str = "cli:direct",
    ) -> None:
        """
        初始化 Agent 循环。

        参数:
            provider:        LLM Provider 实例
            tools:           工具注册表
            context:         上下文构建器
            model:           可选，覆盖默认模型
            max_iterations:  单次 run() 最大迭代次数，默认 32
            session_manager: 会话管理器，用于持久化对话历史；默认 None 不持久化
            session_key:     会话标识，默认 "cli:direct"
        """
        self.provider = provider
        self.tools = tools
        self.context = context
        self.model = model
        self.max_iterations = max_iterations
        self.session_manager = session_manager
        self.session_key = session_key

        # 内部状态
        self._tool_call_history: list[str] = []  # 滑动窗口，存工具调用签名

        # 对话历史：优先从磁盘恢复，未提供 session_manager 时为空
        self._session_history: list[dict] = (
            session_manager.get_history(session_key) if session_manager else []
        )

    async def run(self, user_message: str) -> str:
        """
        执行一次完整的 Agent 循环。

        流程：
          1. 用 context.build_messages() 构建初始 messages
          2. 循环调用 LLM，处理工具调用，直到得出最终回答
          3. 超过 max_iterations 次则返回超时提示

        参数:
            user_message: 用户输入的消息

        返回:
            Agent 的最终回答文本
        """
        # 构建初始 messages
        messages = self.context.build_messages(
            history=self._session_history,
            current_message=user_message,
        )

        # 持久化当前用户消息
        self._persist_message({"role": "user", "content": user_message})

        # 记录本轮新增的消息，用于保存到历史
        new_messages: list[dict] = []

        for iteration in range(self.max_iterations):
            logger.debug("Agent 循环第 %d 次迭代", iteration + 1)

            # 调用 LLM
            response = await self.provider.chat(
                messages=messages,
                tools=self.tools.get_definitions(),
                model=self.model,
            )

            # 如果 API 调用出错，直接返回
            if response.finish_reason == "error":
                logger.error("LLM API 调用失败: %s", response.content)
                return response.content or "API 调用失败"

            # 如果模型请求了工具调用
            if response.has_tool_calls:
                # 构建 assistant 消息（严格遵循 OpenAI 格式）
                assistant_msg = self._build_assistant_message(response)
                messages.append(assistant_msg)
                new_messages.append(assistant_msg)
                self._persist_message(assistant_msg)

                # ★ 打印模型的思考过程（如果有的话）
                reasoning = None
                for tc in response.tool_calls:
                    if tc.reasoning_content:
                        reasoning = tc.reasoning_content
                        break
                if reasoning:
                    # 截断显示，避免刷屏
                    preview = reasoning[:300] + "..." if len(reasoning) > 300 else reasoning
                    print(f"\n  💭 思考: {preview}")

                # 遍历每个工具调用
                for tc in response.tool_calls:
                    args_json = json.dumps(tc.arguments, ensure_ascii=False)
                    
                    # ★ 打印工具调用过程，让用户看到 Agent 在干什么
                    print(f"\n  🛠️  调用工具: {tc.name}({args_json})")

                    # 防爆检测
                    loop_result = self._check_tool_loop(tc.name, args_json)
                    if loop_result is not None:
                        if "熔断" in loop_result:
                            # 熔断：直接返回，终止整个循环
                            print(f"  🚨 {loop_result}")
                            logger.warning("工具调用熔断: %s", loop_result)
                            return loop_result
                        else:
                            # 警告：跳过本次执行，返回系统错误消息
                            print(f"  ⚠️  {loop_result}")
                            logger.warning("工具调用警告: %s", loop_result)
                            tool_msg = {
                                "role": "tool",
                                "tool_call_id": tc.id,
                                "content": f"[SYSTEM_ERROR] {loop_result}",
                            }
                            messages.append(tool_msg)
                            new_messages.append(tool_msg)
                            self._persist_message(tool_msg)
                            continue

                    # 防爆通过，执行工具
                    logger.info("执行工具: %s(%s)", tc.name, args_json[:100])
                    result = await self.tools.execute(tc.name, tc.arguments)
                    logger.debug("工具结果: %s", result[:200] if result else "")
                                            # 打印工具结果（截断显示，避免刷屏）
                    preview = result[:200] + "..." if len(result) > 200 else result
                    print(f"  ✅ 结果: {preview}")
                    tool_msg = {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result,
                    }
                    messages.append(tool_msg)
                    new_messages.append(tool_msg)
                    self._persist_message(tool_msg)

                # 继续循环，让模型根据工具结果继续推理
                continue

            # 模型没有调用工具，得出最终回答
            final_content = response.content or ""
            logger.info("Agent 循环结束，迭代次数: %d", iteration + 1)

            # 保存本轮对话到历史
            assistant_msg = {"role": "assistant", "content": final_content}
            new_messages.append(assistant_msg)
            self._persist_message(assistant_msg)
            self._save_to_history(new_messages)

            return final_content

        # 超过最大迭代次数
        timeout_msg = f"已达到最大迭代次数 ({self.max_iterations})，请简化任务后重试。"
        logger.warning(timeout_msg)
        self._save_to_history(new_messages)
        return timeout_msg

    def _build_assistant_message(self, response: LLMResponse) -> dict:
        """
        构建 assistant 消息（严格遵循 OpenAI 格式）。

        ⚠️ 关键：tool_calls 数组的每个元素只能有 id、type、function 三个字段。
        reasoning_content 必须放在 assistant 消息的顶层，不能放进 tool_calls 元素里。

        参数:
            response: LLM 响应

        返回:
            符合 OpenAI 格式的 assistant 消息字典
        """
        # 构建 tool_calls 数组（严格格式）
        tool_calls_list = []
        for tc in response.tool_calls:
            tool_calls_list.append({
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.name,
                    "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                },
            })

        assistant_msg: dict = {
            "role": "assistant",
            "content": response.content,
            "tool_calls": tool_calls_list,
        }

        # reasoning_content 放在消息顶层（如果有）
        if response.tool_calls and response.tool_calls[0].reasoning_content:
            assistant_msg["reasoning_content"] = response.tool_calls[0].reasoning_content

        return assistant_msg

    def _check_tool_loop(self, tool_name: str, tool_args_json: str) -> str | None:
        """
        防爆检测：检查工具是否陷入重复调用循环。

        使用滑动窗口统计相同签名的出现次数：
          - >= 20 次：熔断，强制终止
          - >= 10 次：警告，跳过本次执行
          - 否则：放行，记录签名

        参数:
            tool_name:      工具名称
            tool_args_json: 工具参数的 JSON 字符串

        返回:
            None 表示放行；否则返回熔断/警告消息
        """
        signature = f"{tool_name}:{tool_args_json}"
        count = self._tool_call_history.count(signature)

        if count >= LOOP_BREAK_THRESHOLD:
            return f"[熔断] 工具 '{tool_name}' 已被连续调用 {count} 次，疑似陷入死循环，已强制终止。"

        if count >= LOOP_WARNING_THRESHOLD:
            return f"[警告] 工具 '{tool_name}' 已被调用 {count} 次，可能存在循环风险，跳过本次执行。"

        # 放行：记录签名，维护滑动窗口
        self._tool_call_history.append(signature)
        if len(self._tool_call_history) > HISTORY_WINDOW_SIZE:
            self._tool_call_history.pop(0)

        return None

    def _persist_message(self, message: dict) -> None:
        """
        将单条消息持久化到会话文件。

        若未配置 session_manager 则为空操作。

        参数:
            message: 要持久化的消息字典
        """
        if self.session_manager:
            self.session_manager.save_message(self.session_key, message)

    def _save_to_history(self, messages_snapshot: list[dict]) -> None:
        """
        保存本轮新增的消息到会话历史。

        用于跨轮次保持对话上下文，使 Agent 能记住之前的交互。

        参数:
            messages_snapshot: 本轮新增的消息列表
        """
        self._session_history.extend(messages_snapshot)
        logger.debug("会话历史已更新，当前长度: %d", len(self._session_history))

    def clear_history(self) -> None:
        """
        清空所有历史状态。

        同时清空工具调用滑动窗口、会话历史和持久化文件。
        """
        self._tool_call_history.clear()
        self._session_history.clear()
        if self.session_manager:
            self.session_manager.clear(self.session_key)
        logger.info("已清空 Agent 历史")
