"""
记忆巩固模块

实现 MemoryConsolidator 类，负责在会话历史超过 Token 预算时，
将较旧的对话消息压缩为摘要，避免上下文窗口溢出：
  - estimate_tokens:    粗略估算消息的 Token 数
  - maybe_consolidate:  超预算时将中间旧消息压缩为摘要
  - _summarize:         调用 LLM 生成摘要
  - _save_to_history:   把摘要追加写入 workspace/memory/HISTORY.md
"""

import json
import logging
import os
from datetime import datetime

from providers.base import LLMProvider

logger = logging.getLogger(__name__)

# 摘要生成失败时的兜底文案
SUMMARY_FAILED_FALLBACK = "（摘要生成失败，旧消息已丢弃）"

# 压缩时保留的最后消息条数
KEEP_LAST_N = 6


class MemoryConsolidator:
    """
    记忆巩固器。

    当会话消息的 Token 估算值超过预算时，调用 LLM 把中间的旧消息
    压缩成一条摘要，从而压缩上下文长度；摘要同时写入 HISTORY.md 留档。
    """

    def __init__(
        self,
        provider: LLMProvider,
        workspace: str,
        token_budget: int = 6000,
    ) -> None:
        """
        初始化记忆巩固器。

        参数:
            provider:     LLM Provider 实例，用于生成摘要
            workspace:    工作区路径，用于写 HISTORY.md
            token_budget: Token 预算，默认 6000
        """
        self.provider = provider
        self.workspace = workspace
        self.token_budget = token_budget

    def estimate_tokens(self, messages: list[dict]) -> int:
        """
        粗略估算消息列表的 Token 数。

        规则：对每条消息做 JSON 序列化（ensure_ascii=False），
        取其字符长度 // 2 作为 Token 估算值，累加得到总估算。

        参数:
            messages: 消息列表

        返回:
            估算的总 Token 数
        """
        total = 0
        for msg in messages:
            total += len(json.dumps(msg, ensure_ascii=False)) // 2
        return total

    async def maybe_consolidate(self, messages: list[dict]) -> list[dict]:
        """
        在超预算时压缩会话历史。

        若估算 Token 未超预算，直接原样返回；
        否则保留第一条（system prompt）和最后 6 条不动，
        把中间的旧消息用一条摘要消息替换。

        参数:
            messages: 完整的消息列表

        返回:
            压缩后的消息列表（未超预算时为原列表）
        """
        # 未超预算，无需压缩
        if self.estimate_tokens(messages) <= self.token_budget:
            return messages

        # 消息太少（首条 + 最后 6 条已覆盖全部），没有可压缩的中间部分
        if len(messages) <= KEEP_LAST_N + 1:
            return messages

        # a. 保留第一条（system prompt）
        head = messages[:1]
        # a. 保留最后 6 条不动
        tail = messages[-KEEP_LAST_N:]
        # b. 中间的旧消息（要被压缩的部分）
        old_messages = messages[1:-KEEP_LAST_N]

        # c. 生成摘要
        summary = await self._summarize(old_messages)

        # d. 用一条摘要消息替换旧消息
        summary_msg = {"role": "system", "content": f"[历史摘要]: {summary}"}

        # e. 追加写入 HISTORY.md 留档
        self._save_to_history(summary, len(old_messages))

        # f. 返回压缩后的消息列表
        return head + [summary_msg] + tail

    async def _summarize(self, messages: list[dict]) -> str:
        """
        调用 LLM 生成旧消息的摘要。

        把旧消息拼接成文本后，连同摘要指令一起发给 provider.chat()。
        若调用失败或结果为空，返回兜底文案。

        参数:
            messages: 要压缩的旧消息列表

        返回:
            摘要文本
        """
        # 把旧消息拼接成文本
        lines = []
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content") or ""
            lines.append(f"{role}: {content}")
        text = "\n".join(lines)

        prompt = (
            "请用 3-5 句话概括以下对话的关键信息，保留重要的事实和结论，"
            "省略过程细节和寒暄。只输出摘要，不要其他内容。\n\n"
            f"{text}"
        )

        try:
            response = await self.provider.chat(
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception:
            logger.exception("摘要生成失败")
            return SUMMARY_FAILED_FALLBACK

        if response.finish_reason == "error" or not response.content:
            logger.error("摘要生成失败: %s", response.content)
            return SUMMARY_FAILED_FALLBACK

        summary = response.content.strip()
        return summary or SUMMARY_FAILED_FALLBACK

    def _save_to_history(self, summary: str, original_count: int) -> None:
        """
        把摘要追加写入 workspace/memory/HISTORY.md。

        参数:
            summary:        摘要内容
            original_count: 被压缩的旧消息条数
        """
        history_dir = os.path.join(self.workspace, "memory")
        os.makedirs(history_dir, exist_ok=True)
        history_path = os.path.join(history_dir, "HISTORY.md")

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = (
            f"## {timestamp}\n"
            f"压缩了 {original_count} 条旧消息\n\n"
            f"{summary}\n\n"
            f"---\n"
        )

        with open(history_path, "a", encoding="utf-8") as f:
            f.write(entry)
        logger.info("已把 %d 条旧消息的摘要写入 HISTORY.md", original_count)
