"""Web 渠道实现模块，提供 WebSocket 接口。"""

import asyncio
import uuid
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse

from bus import InboundMessage, MessageBus, OutboundMessage
from .base import Channel

class WebChannel(Channel):
    """Web 渠道，通过 WebSocket 接收和发送消息。"""

    def __init__(self, bus: MessageBus, host: str = "0.0.0.0", port: int = 8080):
        """初始化 Web 渠道。

        Args:
            bus: 消息总线实例
            host: 监听地址
            port: 监听端口
        """
        super().__init__(name="web", bus=bus)
        self.host = host
        self.port = port
        self._connections: dict[str, WebSocket] = {}  # client_id -> WebSocket
        self._app: FastAPI | None = None
        self._server: uvicorn.Server | None = None

    async def start(self) -> None:
        """启动 FastAPI + WebSocket 服务。"""
        # 创建 FastAPI 应用
        self._app = FastAPI(title="NanoClaw Web")

        # 注册路由
        self._register_routes()

        print(f"[WebChannel] 正在启动 Web 服务: http://{self.host}:{self.port}")

        # 使用 uvicorn.Server.serve() 启动（异步方式，不阻塞事件循环）
        config = uvicorn.Config(
            self._app,
            host=self.host,
            port=self.port,
            log_level="info",
        )
        self._server = uvicorn.Server(config)
        await self._server.serve()

    def _register_routes(self) -> None:
        """注册 FastAPI 路由。"""
        if self._app is None:
            return

        # GET / -> 返回 index.html
        @self._app.get("/")
        async def index():
            """返回 Web UI 页面。"""
            index_path = Path(__file__).parent / "web_ui" / "index.html"
            if index_path.exists():
                return HTMLResponse(content=index_path.read_text(encoding="utf-8"))
            else:
                return HTMLResponse(content="<h1>index.html not found</h1>")

        # WebSocket /ws
        @self._app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            """WebSocket 连接处理。"""
            # 接收连接
            await websocket.accept()

            # 生成 client_id
            client_id = str(uuid.uuid4())
            self._connections[client_id] = websocket

            print(f"[WebChannel] 新连接: client_id={client_id}")

            try:
                # 循环接收消息
                while True:
                    data = await websocket.receive_text()

                    # 跳过空消息
                    if not data.strip():
                        continue

                    print(f"[WebChannel] 收到消息: client_id={client_id} content={data[:50]}...")

                    # 构造入站消息（chat_id = client_id，用于找回连接发送回复）
                    message = InboundMessage(
                        channel="web",
                        sender_id=client_id,
                        chat_id=client_id,
                        content=data,
                        raw={
                            "client_id": client_id,
                        },
                    )

                    # 发布到总线
                    await self.bus.publish_inbound(message)

            except Exception as e:
                # 连接断开
                print(f"[WebChannel] 连接断开: client_id={client_id} reason={e}")

            finally:
                # 清理连接
                self._connections.pop(client_id, None)

    async def send(self, message: OutboundMessage) -> None:
        """发送消息到 WebSocket 客户端。

        Args:
            message: 出站消息实例
        """
        # 通过 chat_id 找回 WebSocket 连接
        ws = self._connections.get(message.chat_id)

        if ws is None:
            # 连接不存在（用户已断开）
            print(f"[WebChannel] 连接不存在: chat_id={message.chat_id}")
            return

        try:
            # 发送文本消息
            await ws.send_text(message.content)
            print(f"[WebChannel] 消息已发送: chat_id={message.chat_id}")

        except Exception as e:
            # 发送失败，清理连接
            print(f"[WebChannel] 发送失败: chat_id={message.chat_id} reason={e}")
            self._connections.pop(message.chat_id, None)

    async def stop(self) -> None:
        """停止 Web 服务。"""
        if self._server is not None:
            # 通知 server 停止
            self._server.should_exit = True
            self._server = None

        # 关闭所有 WebSocket 连接
        for client_id, ws in list(self._connections.items()):
            try:
                await ws.close()
            except Exception:
                pass
        self._connections.clear()

        print("[WebChannel] 服务已停止")