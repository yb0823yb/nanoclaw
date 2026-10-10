"""
Context Builder 模块

负责构建 Agent 的上下文环境，包括：
  - 加载人设文件（identity.md）
  - 加载长期记忆（MEMORY.md，预留接口）
  - 拼接 System Prompt
  - 构建完整的 messages 列表
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Optional


# 默认人设内容（当 identity.md 不存在时使用）
DEFAULT_IDENTITY = """你是一个有用的 AI 助手，运行在 nanoclaw 框架中。
你可以通过工具与文件系统交互，帮助用户完成各种任务。
请始终遵循安全规范，不要访问工作区之外的文件。"""


class ContextBuilder:
    """
    上下文构建器。

    负责加载人设、记忆，并构建发送给 LLM 的 System Prompt 和 messages 列表。
    """

    def __init__(self, workspace: str | Path, identity_file: str = "identity.md", skills_summary: str = "") -> None:
        """
        初始化上下文构建器。

        参数:
            workspace:      工作区路径（Agent 被允许操作的根目录）
            identity_file:  人设文件名，默认为 identity.md，位于工作区根目录
            skills_summary: 技能摘要字符串，默认为空字符串
        """
        self.workspace = Path(workspace).resolve()
        self.identity_file = identity_file
        self.skills_summary = skills_summary
        self._identity_content: Optional[str] = None
        self._memory_content: Optional[str] = None

    def _load_identity(self) -> str:
        """
        加载人设文件内容。

        从工作区根目录读取 identity_file 指定的文件。
        如果文件不存在或读取失败，返回默认人设内容。

        返回:
            人设文本内容
        """
        if self._identity_content is not None:
            return self._identity_content

        identity_path = self.workspace / self.identity_file
        try:
            if identity_path.exists():
                self._identity_content = identity_path.read_text(encoding="utf-8").strip()
                if self._identity_content:
                    return self._identity_content
        except Exception:
            pass

        # 文件不存在或为空，使用默认人设
        self._identity_content = DEFAULT_IDENTITY
        return self._identity_content

    def _load_memory(self) -> str:
        """
        加载长期记忆内容。

        从 workspace/memory/MEMORY.md 读取记忆内容。
        这是为第六章（记忆系统）预留的接口。
        如果文件不存在，返回空字符串。

        返回:
            记忆文本内容，不存在则为空字符串
        """
        if self._memory_content is not None:
            return self._memory_content

        memory_path = self.workspace / "memory" / "MEMORY.md"
        try:
            if memory_path.exists():
                self._memory_content = memory_path.read_text(encoding="utf-8").strip()
                return self._memory_content
        except Exception:
            pass

        self._memory_content = ""
        return self._memory_content

    def build_system_prompt(self) -> str:
        """
        构建完整的 System Prompt。

        拼接以下部分：
          1. 人设内容
          2. 当前时间
          3. 工作区路径
          4. 长期记忆（如果有）
          5. 技能摘要（如果有）

        返回:
            完整的 System Prompt 字符串
        """
        identity = self._load_identity()
        memory = self._load_memory()
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M (%A)")

        parts = [
            identity,
            "",
            f"当前时间: {current_time}",
            f"工作区路径: {self.workspace}",
        ]

        # 如果有长期记忆，添加到 System Prompt
        if memory:
            parts.extend([
                "",
                "长期记忆:",
                memory,
            ])

        # 如果有技能摘要，添加到 System Prompt
        if self.skills_summary:
            parts.extend([
                "",
                "## 可用技能",
                self.skills_summary,
            ])

        return "\n".join(parts)

    def build_messages(
        self,
        history: list[dict] | None = None,
        current_message: str = "",
    ) -> list[dict]:
        """
        构建完整的 messages 列表。

        格式为: [System Prompt] + 历史对话 + 当前用户消息

        参数:
            history:         历史对话列表，每个元素为 {"role": "...", "content": "..."}
            current_message: 当前用户消息内容

        返回:
            完整的 messages 列表，可直接传给 LLM API
        """
        messages: list[dict] = [
            {"role": "system", "content": self.build_system_prompt()}
        ]

        # 添加历史对话
        if history:
            messages.extend(history)

        # 添加当前用户消息
        if current_message:
            messages.append({"role": "user", "content": current_message})

        return messages
