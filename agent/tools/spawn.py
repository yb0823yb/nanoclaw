"""SpawnSubagentTool 工具模块，用于创建临时子 Agent 执行子任务。"""

from typing import Callable

from providers.base import LLMProvider
from agent.tools.base import Tool
from agent.tools.registry import ToolRegistry
from agent.loop import AgentLoop
from agent.context import ContextBuilder
from session.manager import SessionManager

class DummySessionManager(SessionManager):
    """虚拟会话管理器，不执行任何持久化操作。

    用于子 Agent，子 Agent 不需要持久化历史。
    """

    def get_history(self, session_key: str) -> list[dict]:
        """返回空历史。"""
        return []

    def save_message(self, session_key: str, message: dict) -> None:
        """不保存消息。"""
        pass

    def clear(self, session_key: str) -> None:
        """不清空任何内容。"""
        pass

class SubagentContextBuilder(ContextBuilder):
    """子 Agent 的简化上下文构建器。

    System prompt 只有一句话，不加载人设、记忆、技能等。
    """

    SYSTEM_PROMPT = "你是任务专员，完成任务直接输出结果。"

    def build_system_prompt(self) -> str:
        """返回简化的 System Prompt。"""
        return self.SYSTEM_PROMPT

    def build_messages(
        self,
        history: list[dict] | None = None,
        current_message: str = ""
    ) -> list[dict]:
        """构建简化消息列表。"""
        messages = [{"role": "system", "content": self.SYSTEM_PROMPT}]
        if current_message:
            messages.append({"role": "user", "content": current_message})
        return messages

class SpawnSubagentTool(Tool):
    """创建临时子 Agent 执行子任务的工具。"""

    def __init__(
        self,
        provider_factory: Callable[[str | None], LLMProvider],
        tools_registry: ToolRegistry,
        workspace: str,
        current_depth: int = 0,
        max_depth: int = 2
    ):
        """初始化 SpawnSubagentTool。

        Args:
            provider_factory: Provider 工厂函数，输入 model 返回 LLMProvider 实例
            tools_registry: 当前 Agent 的工具注册表（用于复制工具）
            workspace: 工作区路径
            current_depth: 当前嵌套深度
            max_depth: 最大嵌套深度
        """
        self._provider_factory = provider_factory
        self._tools_registry = tools_registry
        self._workspace = workspace
        self._current_depth = current_depth
        self._max_depth = max_depth

    @property
    def name(self) -> str:
        """工具名称。"""
        return "spawn_subagent"

    @property
    def description(self) -> str:
        """工具描述。"""
        return "创建一个临时子 Agent 执行子任务，返回结果。适用于需要独立思考或并行处理的复杂任务。"

    @property
    def parameters(self) -> dict:
        """参数定义。"""
        return {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "子任务描述，需要子 Agent 完成的具体任务"
                },
                "model": {
                    "type": "string",
                    "description": "子 Agent 使用的模型名称（可选，默认与主 Agent 相同）"
                }
            },
            "required": ["task"]
        }

    async def execute(self, **kwargs) -> str:
        """执行子 Agent 任务。

        Args:
            task: 子任务描述
            model: 可选的模型名称

        Returns:
            子 Agent 执行结果
        """
        task = kwargs.get("task", "")
        model = kwargs.get("model")

        if not task:
            return "错误：task 参数不能为空"

        # 1. 创建 Provider
        provider = self._provider_factory(model)

        # 2. 复制工具（跳过 spawn_subagent 自己）
        sub_tools = ToolRegistry()
        for tool in self._tools_registry._tools.values():
            if tool.name != self.name:
                # 复制工具实例（假设工具是不可变的，直接引用）
                sub_tools.register(tool)

        # 3. 如果未达到最大深度，给子 Agent 也注册 SpawnSubagentTool
        if self._current_depth + 1 < self._max_depth:
            sub_spawn = SpawnSubagentTool(
                provider_factory=self._provider_factory,
                tools_registry=self._tools_registry,
                workspace=self._workspace,
                current_depth=self._current_depth + 1,
                max_depth=self._max_depth
            )
            sub_tools.register(sub_spawn)

        # 4. 创建简化上下文构建器
        context = SubagentContextBuilder(workspace=self._workspace)

        # 5. 创建 DummySessionManager
        session_manager = DummySessionManager(sessions_dir="")

        # 6. 创建 AgentLoop
        agent = AgentLoop(
            provider=provider,
            tools=sub_tools,
            context=context,
            session_manager=session_manager,
            session_key="subagent:temp",
            model=model,
            max_iterations=16  # 子 Agent 迭代次数较少
        )

        # 7. 执行任务并返回结果
        try:
            result = await agent.run(task)
            return result
        except Exception as e:
            return f"子 Agent 执行失败: {str(e)}"