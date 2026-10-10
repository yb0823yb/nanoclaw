"""消息总线模块，用于处理入站和出站消息的队列管理。"""

import asyncio
from dataclasses import dataclass

@dataclass
class InboundMessage:
    """入站消息数据类。

    Attributes:
        channel: 来源渠道名称（如 "feishu"、"qq"、"web"、"cli"）
        sender_id: 发送者标识
        chat_id: 会话标识（群聊或私聊）
        content: 消息正文
        raw: 原始消息，调试用，可选
    """
    channel: str
    sender_id: str
    chat_id: str
    content: str
    raw: dict | None = None

@dataclass
class OutboundMessage:
    """出站消息数据类。

    Attributes:
        channel: 目标渠道
        chat_id: 目标会话
        content: 回复正文
        reply_to: 引用的消息 ID，可选
    """
    channel: str
    chat_id: str
    content: str
    reply_to: str | None = None

class MessageBus:
    """消息总线类，管理入站和出站消息队列。"""

    def __init__(self):
        """构造函数，创建入站和出站消息队列。"""
        self.inbound_queue: asyncio.Queue[InboundMessage] = asyncio.Queue()
        self.outbound_queue: asyncio.Queue[OutboundMessage] = asyncio.Queue()

    async def publish_inbound(self, msg: InboundMessage) -> None:
        """发布入站消息到队列。

        Args:
            msg: 入站消息实例
        """
        await self.inbound_queue.put(msg)

    async def consume_inbound(self) -> InboundMessage:
        """从入站队列消费消息。

        Returns:
            InboundMessage: 入站消息实例
        """
        return await self.inbound_queue.get()

    async def publish_outbound(self, msg: OutboundMessage) -> None:
        """发布出站消息到队列。

        Args:
            msg: 出站消息实例
        """
        await self.outbound_queue.put(msg)

    async def consume_outbound(self) -> OutboundMessage:
        """从出站队列消费消息。

        Returns:
            OutboundMessage: 出站消息实例
        """
        return await self.outbound_queue.get()