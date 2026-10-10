"""Channel 抽象基类模块。"""

from abc import ABC, abstractmethod

from bus import MessageBus, OutboundMessage

class Channel(ABC):
    """渠道抽象基类，定义所有渠道必须实现的接口。

    Attributes:
        name: 渠道名称标识
        bus: 消息总线实例
    """

    def __init__(self, name: str, bus: MessageBus):
        """初始化渠道。

        Args:
            name: 渠道名称标识
            bus: 消息总线实例
        """
        self.name = name
        self.bus = bus

    @abstractmethod
    async def start(self) -> None:
        """启动渠道，开始监听消息。"""
        pass

    @abstractmethod
    async def send(self, message: OutboundMessage) -> None:
        """发送出站消息。

        Args:
            message: 出站消息实例
        """
        pass

    async def stop(self) -> None:
        """停止渠道，可选覆盖。

        子类可根据需要覆盖此方法以实现清理逻辑。
        """
        pass