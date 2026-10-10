"""CLI 渠道实现模块。"""

import asyncio
from typing import Callable

from bus import InboundMessage, MessageBus, OutboundMessage
from .base import Channel

class CLIChannel(Channel):
    """命令行交互渠道。

    继承 Channel 基类，实现命令行界面的消息收发。
    使用 asyncio.Event 同步等待回复完成。
    """

    def __init__(self, bus: MessageBus):
        """初始化 CLI 渠道。

        Args:
            bus: 消息总线实例
        """
        super().__init__(name="cli", bus=bus)
        self._response_event = asyncio.Event()  # 用于同步等待回复

        # 预留属性，由 main.py 在创建后注入
        self.tool_names: list[str] = []  # 工具名列表
        self._clear_callback: Callable[[], None] | None = None  # 清空历史回调
        self._exit_callback: Callable[[], None] | None = None  # 退出回调

    async def start(self) -> None:
        """启动 CLI 渠道，循环读取用户输入。

        支持命令（带 / 前缀或裸词均可）：
            /exit 或 退出/exit/quit - 退出程序
            /clear 或 清除/clear/reset - 清空历史（调用 _clear_callback）
            /tools - 列出可用工具（打印 tool_names）

        正常输入将构造 InboundMessage 并发布到消息总线，
        然后等待回复完成再继续下一轮输入。
        """
        while True:
            # 使用 asyncio.to_thread 包装阻塞的 input()
            user_input = await self._async_input("你> ")

            # 跳过空输入
            if not user_input.strip():
                continue

            # 处理命令（支持 / 前缀和裸词，大小写不敏感）
            command = user_input.strip().lower()

            if command in ("/exit", "exit", "quit", "退出"):
                print("再见！")
                if self._exit_callback:
                    self._exit_callback()
                break
            elif command in ("/clear", "clear", "reset", "清除"):
                # 调用清空历史回调
                if self._clear_callback:
                    self._clear_callback()
                print("历史已清空")
                continue
            elif command == "/tools":
                # 打印工具列表
                if self.tool_names:
                    print("可用工具列表：")
                    for name in self.tool_names:
                        print(f"  - {name}")
                else:
                    print("当前没有可用工具")
                continue
            elif command.startswith("/"):
                print(f"未知命令: {user_input}")
                continue

            # 重置事件，准备等待回复
            self._response_event.clear()

            # 构造入站消息并发布
            message = InboundMessage(
                channel="cli",
                sender_id="local",
                chat_id="direct",
                content=user_input,
            )
            await self.bus.publish_inbound(message)

            # 等待回复完成
            await self._response_event.wait()

    async def send(self, message: OutboundMessage) -> None:
        """发送出站消息到 CLI。

        Args:
            message: 出站消息实例
        """
        print(f"🤖 {message.content}")
        # 通知 start() 可以继续了
        self._response_event.set()

    async def _async_input(self, prompt: str = "") -> str:
        """异步包装同步的 input() 函数。

        Args:
            prompt: 输入提示符

        Returns:
            用户输入的字符串
        """
        return await asyncio.to_thread(input, prompt)