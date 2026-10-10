"""
Web 抓取工具模块

抓取指定 URL 的网页内容，转换成纯文本返回。
依赖：pip install httpx html2text
"""

import re
from typing import Any
from urllib.parse import urlparse

from agent.tools.base import Tool

# 输出最大字符数，超过则截断
_MAX_OUTPUT_CHARS = 12000


class WebFetchTool(Tool):
    """
    Web 抓取工具。

    抓取指定 URL 的网页内容，将 HTML 转换为 Markdown 格式纯文本返回。
    通常配合 web_search 工具先搜索再抓取。
    """

    @property
    def name(self) -> str:
        return "web_fetch"

    @property
    def description(self) -> str:
        return "抓取指定 URL 的网页内容。当你需要阅读某个具体网页的详细内容时使用。通常配合 web_search 工具先搜索再抓取。"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "要抓取的网页 URL",
                },
            },
            "required": ["url"],
        }

    async def execute(self, **kwargs) -> str:
        """
        抓取网页内容。

        流程：
          1. URL 安全检查（协议验证）
          2. 发送 HTTP GET 请求
          3. HTML 转换为 Markdown 纯文本
          4. 清理输出（去除多余空行、截断）

        参数:
            url: 要抓取的网页 URL

        返回:
            网页内容的 Markdown 格式文本
        """
        url = kwargs.get("url", "")

        # 1. URL 安全检查
        try:
            parsed = urlparse(url)
            if parsed.scheme not in ("http", "https"):
                return "安全拦截：只允许 http/https 协议"
            if not parsed.netloc:
                return "安全拦截：URL 格式无效"
        except Exception as e:
            return f"安全拦截：URL 解析失败 - {e}"

        try:
            # 导入依赖库
            import html2text
            import httpx

            # 2. 发送 HTTP GET 请求
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }

            async with httpx.AsyncClient(
                timeout=15,
                headers=headers,
                follow_redirects=True,
            ) as client:
                response = await client.get(url)

            # 检查响应状态码
            if not response.is_success:
                return f"抓取失败：HTTP {response.status_code}"

            # 获取 HTML 内容
            html_content = response.text

            # 3. HTML 转换成纯文本
            h = html2text.HTML2Text()
            h.ignore_links = False      # 保留链接
            h.ignore_images = True      # 忽略图片
            h.body_width = 0            # 不自动换行

            text_content = h.handle(html_content)

            # 4. 清理输出
            # 去除连续多个空行
            text_content = re.sub(r"\n{3,}", "\n\n", text_content)

            # 截断过长内容
            if len(text_content) > _MAX_OUTPUT_CHARS:
                text_content = text_content[:_MAX_OUTPUT_CHARS] + "\n...(内容过长，已截断)"

            return text_content

        except ImportError:
            return "抓取出错: 未安装依赖库，请先运行 pip install httpx html2text 安装"
        except httpx.TimeoutException:
            return "抓取出错: 请求超时（15秒）"
        except httpx.ConnectError:
            return "抓取出错: 无法连接到目标服务器，请检查 URL 是否正确"
        except Exception as e:
            return f"抓取出错: {e}"
