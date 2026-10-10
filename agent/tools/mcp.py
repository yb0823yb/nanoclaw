"""
MCP (Model Context Protocol) 工具模块

提供 MCP 服务器的连接管理和工具包装能力，包含：
- MCPClientManager: 管理 MCP 服务器连接、工具发现和调用
- MCPTool: 包装 MCP 工具为 Agent 可用的 Tool 接口

使用示例：
    # 配置格式（config.json）
    "mcp_servers": {
        "filesystem": {
            "command": "python",
            "args": ["-m", "mcp_server_filesystem"]
        }
    }

    # 使用
    manager = MCPClientManager(mcp_config)
    await manager.connect_all()
    tools = manager.get_tools()
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from agent.tools.base import Tool


@contextlib.asynccontextmanager
async def _timeout(seconds: float):
    """在当前 Task 上施加超时，不新建 Task。

    asyncio.wait_for 会把协程包装成新 Task，导致 stdio_client/ClientSession 的
    __aenter__ 与 shutdown 的 __aexit__ 处于不同 Task，anyio 会报
    "Attempted to exit cancel scope in a different task than it was entered in"。
    这里改用 loop.call_later 取消当前 Task，保持进出在同一 Task。
    """
    task = asyncio.current_task()
    if task is None or seconds is None:
        yield
        return

    loop = asyncio.get_running_loop()
    timed_out = False

    def _fire() -> None:
        nonlocal timed_out
        timed_out = True
        task.cancel()

    handle = loop.call_later(seconds, _fire)
    try:
        yield
    except asyncio.CancelledError:
        if timed_out:
            raise asyncio.TimeoutError() from None
        raise
    finally:
        handle.cancel()

class MCPClientManager:
    """
    MCP 客户端管理器

    管理多个 MCP 服务器的连接，发现并收集工具，提供统一的工具调用接口。

    内部状态：
    - _context_managers: 存储 stdio_client 返回的异步上下文管理器
    - _sessions: 按 server_name 存储的 ClientSession 连接
    - _tools: 所有已发现的 MCPTool 实例

    使用示例：
        manager = MCPClientManager(config["mcp_servers"])
        await manager.connect_all()
        tools = manager.get_tools()
        result = await manager.call_tool("server", "tool", {"arg": "value"})
        await manager.shutdown()
    """

    def __init__(self, mcp_config: dict) -> None:
        """
        Args:
            mcp_config: MCP 服务器配置字典，格式如下：
                {
                    "server_name": {
                        "command": "python",
                        "args": ["-m", "mcp_server"]
                    },
                    ...
                }
        """
        self.mcp_config = mcp_config
        self._context_managers: dict[str, Any] = {}  # 存储 stdio_client 上下文管理器
        self._session_managers: dict[str, Any] = {}  # 存储 ClientSession 上下文管理器
        self._sessions: dict[str, ClientSession] = {}
        self._tools: list[MCPTool] = []

    async def _connect_one(self, server_name: str, server_config: dict) -> None:
        """
        连接单个 MCP 服务器并发现工具（内部方法）

        Args:
            server_name: 服务器名称
            server_config: 服务器配置字典
        """
        # 创建服务器参数
        params = StdioServerParameters(
            command=server_config["command"],
            args=server_config.get("args", []),
            env=server_config.get("env", None),
        )

        # 创建上下文管理器（不立即进入）
        ctx_mgr = stdio_client(params)

        # 手动进入上下文，获取读写流
        read_stream, write_stream = await ctx_mgr.__aenter__()

        # 存储上下文管理器（用于后续退出）
        self._context_managers[server_name] = ctx_mgr

        # 初始化 session（MCP 1.x 需要作为上下文管理器使用，__aenter__ 启动内部消息循环）
        session_mgr = ClientSession(read_stream, write_stream)
        session = await session_mgr.__aenter__()
        self._session_managers[server_name] = session_mgr

        await session.initialize()

        # 存储连接
        self._sessions[server_name] = session

        # 发现工具
        tools_response = await session.list_tools()
        discovered_tools = tools_response.tools

        # 创建 MCPTool 实例
        for tool_info in discovered_tools:
            mcp_tool = MCPTool(
                server_name=server_name,
                tool_info={
                    "name": tool_info.name,
                    "description": tool_info.description or "",
                    "inputSchema": tool_info.inputSchema,
                },
                client_manager=self,
            )
            self._tools.append(mcp_tool)

        print(f"  [MCP] [{server_name}]: 发现 {len(discovered_tools)} 个工具")

    async def connect_all(self, timeout: float = 30.0) -> None:
        """
        连接所有 MCP 服务器并发现工具（每个服务器有超时保护）

        遍历 mcp_config 中的每个服务器配置：
        1. 使用 StdioServerParameters 创建连接参数
        2. 使用 stdio_client 创建上下文管理器，手动调用 __aenter__
        3. 初始化 ClientSession
        4. 调用 list_tools() 发现可用工具
        5. 为每个工具创建 MCPTool 实例

        Args:
            timeout: 每个服务器的连接超时时间（秒），默认 30 秒
        """
        for server_name, server_config in self.mcp_config.items():
            try:
                print(f"  [MCP] [{server_name}]: 正在连接...")
                async with _timeout(timeout):
                    await self._connect_one(server_name, server_config)
            except asyncio.TimeoutError:
                print(f"  [!] MCP [{server_name}]: 连接超时（{timeout}s），跳过")
                await self._cleanup_server(server_name)
            except Exception as e:
                print(f"  [!] MCP [{server_name}]: 连接失败 - {e}")
                await self._cleanup_server(server_name)

    async def _cleanup_server(self, server_name: str) -> None:
        """清理某个服务器已（部分）建立的连接。

        按 session → 上下文 的顺序退出，避免残留子进程。
        """
        session_mgr = self._session_managers.pop(server_name, None)
        if session_mgr is not None:
            try:
                await session_mgr.__aexit__(None, None, None)
            except Exception as e:
                print(f"  [!] MCP [{server_name}]: session 清理失败 - {e}")

        ctx_mgr = self._context_managers.pop(server_name, None)
        if ctx_mgr is not None:
            try:
                await ctx_mgr.__aexit__(None, None, None)
            except Exception as e:
                print(f"  [!] MCP [{server_name}]: 上下文清理失败 - {e}")

    def get_tools(self) -> list[MCPTool]:
        """
        获取所有已发现的 MCP 工具列表

        Returns:
            list[MCPTool]: MCPTool 实例列表
        """
        return self._tools

    async def call_tool(self, server_name: str, tool_name: str, arguments: dict) -> str:
        """
        调用指定服务器的工具

        Args:
            server_name: MCP 服务器名称
            tool_name: 工具原始名称（不含 server 前缀）
            arguments: 工具参数字典

        Returns:
            str: 工具执行结果（文本）或错误信息
        """
        session = self._sessions.get(server_name)
        if session is None:
            return f"错误: MCP 服务器 '{server_name}' 未连接"

        try:
            result = await session.call_tool(tool_name, arguments=arguments)

            # 从 result.content 中提取文本
            text_content = []
            for content_block in result.content:
                if hasattr(content_block, "text"):
                    text_content.append(content_block.text)
                elif hasattr(content_block, "type") and content_block.type == "text":
                    text_content.append(str(content_block))

            if text_content:
                return "\n".join(text_content)
            else:
                return "工具执行成功（无文本输出）"

        except Exception as e:
            return f"错误: MCP 工具调用失败 - {e}"

    async def shutdown(self) -> None:
        """
        关闭所有 MCP 连接

        关闭所有 session，调用上下文管理器的 __aexit__，清理连接资源。
        """
        # 逐个服务器退出 session → 上下文（保持与 __aenter__ 同一 Task）
        server_names = set(self._context_managers.keys()) | set(self._session_managers.keys())
        for server_name in server_names:
            await self._cleanup_server(server_name)

        # 清空状态
        self._sessions.clear()
        self._tools.clear()
        print("  [MCP] 所有连接已关闭")

class MCPTool(Tool):
    """
    MCP 工具包装类

    将 MCP 服务器的工具包装为 Agent 可用的 Tool 接口。
    工具名称格式为 "{server_name}__{原始工具名}"，便于区分来源。

    使用示例：
        tool = MCPTool(
            server_name="filesystem",
            tool_info={
                "name": "read_file",
                "description": "读取文件内容",
                "inputSchema": {...}
            },
            client_manager=manager
        )
        result = await tool.execute(path="/tmp/test.txt")
    """

    def __init__(
        self,
        server_name: str,
        tool_info: dict,
        client_manager: MCPClientManager,
    ) -> None:
        """
        Args:
            server_name: MCP 服务器名称
            tool_info: MCP 工具定义，包含：
                - name: 工具原始名称
                - description: 工具描述
                - inputSchema: 参数 JSON Schema
            client_manager: MCPClientManager 实例
        """
        self.server_name = server_name
        self._tool_info = tool_info
        self._client_manager = client_manager

        # 存储原始工具名（不含 server 前缀）
        self._original_name = tool_info["name"]

    @property
    def name(self) -> str:
        """工具名称，格式: {server_name}__{原始工具名}"""
        return f"{self.server_name}__{self._original_name}"

    @property
    def description(self) -> str:
        """工具描述"""
        return self._tool_info.get("description", f"MCP 工具: {self._original_name}")

    @property
    def parameters(self) -> dict:
        """参数 Schema（直接使用 inputSchema）"""
        return self._tool_info.get("inputSchema", {
            "type": "object",
            "properties": {},
        })

    async def execute(self, **kwargs: Any) -> str:
        """
        调用 MCP 工具

        通过 client_manager.call_tool() 调用远程工具。

        Args:
            **kwargs: 工具参数

        Returns:
            str: 工具执行结果
        """
        return await self._client_manager.call_tool(
            server_name=self.server_name,
            tool_name=self._original_name,
            arguments=kwargs,
        )

    def to_function_definition(self) -> dict:
        """
        构建工具的 OpenAI function calling 定义

        直接使用 tool_info 中的 inputSchema 构造定义。

        Returns:
            dict: OpenAI 格式的工具定义
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }