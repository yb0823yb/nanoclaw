"""NanoClaw 入口文件"""

import asyncio
import os
import sys

from agent.context import ContextBuilder
from agent.loop import AgentLoop
from agent.memory import MemoryConsolidator
from agent.skills import SkillsLoader
from agent.tools.filesystem import ListDirTool, ReadFileTool, WriteFileTool
from agent.tools.mcp import MCPClientManager
from agent.tools.registry import ToolRegistry
from agent.tools.shell import ExecTool
from agent.tools.spawn import SpawnSubagentTool
from agent.tools.web_fetch import WebFetchTool
from agent.tools.web_search import WebSearchTool
from bus.queue import MessageBus
from channels import CLIChannel, FeishuChannel, QQChannel, WebChannel
from config import load_config
from gateway import Gateway
from providers.openai_compat import OpenAICompatProvider
from session.manager import SessionManager


def build_agent(config, session_key: str, mcp_tools: list | None = None) -> AgentLoop:
    """构建 Agent 实例。

    Args:
        config: 配置对象（由 load_config() 返回）
        session_key: 会话标识，格式为 "{channel}:{sender_id}"
        mcp_tools: 由 main() 启动时连接的 MCP 工具列表，注册到该 Agent
    """

    if not config.api_key:
        print("错误：未配置 API_KEY，请在 config.json 中设置或设置环境变量 NANOCLAW_API_KEY")
        sys.exit(1)

    # 创建 LLM Provider
    provider = OpenAICompatProvider(
        api_key=config.api_key,
        base_url=config.base_url,
        model=config.model,
    )

    # 创建工具注册中心
    tools = ToolRegistry()
    tools.register(ReadFileTool(config.workspace))
    tools.register(WriteFileTool(config.workspace))
    tools.register(ListDirTool(config.workspace))
    tools.register(ExecTool(config.workspace))
    tools.register(WebSearchTool())
    tools.register(WebFetchTool())

    # 注册子 Agent 工具
    def create_provider(model=None):
        """Provider 工厂函数，子 Agent 用。"""
        # 子 Agent 默认用 subagent 模型（更便宜）
        if model is None and config.models:
            model = config.models.get("subagent", config.model)
        return OpenAICompatProvider(
            api_key=config.api_key,
            base_url=config.base_url,
            model=model or config.model
        )

    # 注册 MCP 工具（由 main() 在启动时连接并传入）
    for mcp_tool in (mcp_tools or []):
        tools.register(mcp_tool)

    tools.register(SpawnSubagentTool(
        provider_factory=create_provider,
        tools_registry=tools,
        workspace=config.workspace,
    ))

    # 加载技能摘要
    skills_loader = SkillsLoader(skills_dir=os.path.join(config.workspace, "skills"))
    skills_summary = skills_loader.build_skills_summary()
    if skills_summary:
        skills_list = skills_loader.list_skills()
        print(f"发现 {len(skills_list)} 个技能")

    # 创建会话管理器（sessions 在 workspace/workspace/sessions 目录下）
    sessions_dir = os.path.join(config.workspace, "workspace", "sessions")
    session_manager = SessionManager(sessions_dir=sessions_dir)

    # 如果有历史，显示恢复提示
    existing_history = session_manager.get_history(session_key)
    if existing_history:
        print(f"[{session_key}] 已恢复 {len(existing_history)} 条历史消息")

    # 创建上下文构建器
    context = ContextBuilder(
        workspace=config.workspace,
        identity_file=config.identity_file,
        skills_summary=skills_summary,
    )

    # 创建 Token 压缩器
    consolidator = MemoryConsolidator(
        provider=provider,
        workspace=config.workspace,
        token_budget=6000,
    )

    # 创建 Agent 循环
    agent = AgentLoop(
        provider=provider,
        tools=tools,
        context=context,
        session_manager=session_manager,
        session_key=session_key,
        model=config.model,
        max_iterations=config.max_iterations,
    )
    agent.consolidator = consolidator  # 挂载压缩器

    print(f"[{session_key}] 已注册工具：{', '.join(tools.list_tools())}")
    return agent


async def run_nanoclaw(config) -> None:
    """启动 MCP、渠道与网关，退出时清理 MCP 连接。"""
    bus = MessageBus()

    # 启动时连接 MCP 服务器（与网关共用同一事件循环）
    mcp_manager = MCPClientManager(config.mcp_servers or {})
    if config.mcp_servers:
        await mcp_manager.connect_all()
        print(f"[启动] 已连接 MCP，发现 {len(mcp_manager.get_tools())} 个工具")
    mcp_tools = mcp_manager.get_tools()

    # 定义 Agent 工厂函数
    def create_agent(session_key: str) -> AgentLoop:
        return build_agent(config, session_key, mcp_tools=mcp_tools)

    # 注册渠道
    cli_channel = CLIChannel(bus)
    channels = [cli_channel]

    # 飞书渠道（如果配置了 feishu app_id / app_secret 就自动启用）
    if config.feishu_app_id and config.feishu_app_secret:
        feishu_channel = FeishuChannel(bus, config.feishu_app_id, config.feishu_app_secret)
        channels.append(feishu_channel)
        print("[启动] 已启用飞书渠道")
    else:
        print("[启动] 未配置飞书，跳过飞书渠道")

    # QQ 渠道（如果配置了 qq app_id / app_secret 就自动启用）
    if config.qq_app_id and config.qq_app_secret:
        qq_channel = QQChannel(bus, config.qq_app_id, config.qq_app_secret)
        channels.append(qq_channel)
        print("[启动] 已启用 QQ 渠道")
    else:
        print("[启动] 未配置 QQ，跳过 QQ 渠道")

    # Web 渠道（默认启用，不需要外部凭证）
    if config.web_enabled:
        web_channel = WebChannel(bus, host=config.web_host, port=config.web_port)
        channels.append(web_channel)
        print(f"[启动] 已启用 Web 渠道: http://{config.web_host}:{config.web_port}")
    else:
        print("[启动] Web 渠道已禁用")

    # 启动网关
    gateway = Gateway(bus, channels, create_agent)

    # 预创建 CLI Agent，让初始化信息在启动时就显示
    cli_session_key = "cli:local"
    agent = create_agent(cli_session_key)
    gateway._agents[cli_session_key] = agent

    # 注入工具列表和清空回调给 CLI 渠道
    cli_channel.tool_names = agent.tools.list_tools()
    cli_channel._clear_callback = lambda: agent.clear_history()
    cli_channel._exit_callback = gateway.request_shutdown

    try:
        await gateway.run()
    finally:
        # 退出时关闭 MCP 连接
        await mcp_manager.shutdown()

    # 强制退出，杀掉 feishu/QQ 等残留的子线程，确保进程彻底结束
    os._exit(0)


def main() -> None:
    """主入口"""
    print("=" * 50)
    print("  NanoClaw - 智能编程助手")
    print("=" * 50)

    config = load_config()

    try:
        asyncio.run(run_nanoclaw(config))
    except KeyboardInterrupt:
        print("\n[NanoClaw] 正在退出...")
        import os
        os._exit(0)  # 强制退出，杀掉残留的 WebSocket 子线程


if __name__ == "__main__":
    main()
