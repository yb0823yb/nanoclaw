"""渠道包"""

from channels.base import Channel
from channels.cli import CLIChannel
from channels.feishu import FeishuChannel
from channels.qq import QQChannel
from channels.web import WebChannel

__all__ = ["Channel", "CLIChannel", "FeishuChannel", "QQChannel", "WebChannel"]
