"""
Web 搜索工具模块
使用博查Bocha API联网搜索，返回相关结果。
依赖：pip install requests
"""
import asyncio
import json
import os
import requests
from typing import Any
from agent.tools.base import Tool

# 输出最大字符数，超过则截断
_MAX_OUTPUT_CHARS = 8000

# 博查API配置
BOCHA_API_KEY ="sk-82e09d16b850441ea968703b097be706"
BOCHA_URL = "https://api.bocha.cn/v1/web-search"

class WebSearchTool(Tool):
    """
    Web 搜索工具。
    使用博查Bocha搜索引擎查询互联网，获取最新信息。
    适用于查询实时信息、新闻或不确定的知识。
    """

    @property
    def name(self) -> str:
        return "web_search"

    @property
    def description(self) -> str:
        return "搜索互联网获取最新信息。当你需要查询实时信息、最新新闻或不确定的知识时使用。"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索关键词",
                },
                "max_results": {
                    "type": "integer",
                    "description": "最多返回几条结果，默认为 5",
                    "default": 5,
                },
            },
            "required": ["query"],
        }

    async def execute(self, **kwargs) -> str:
        """
        执行 Web 搜索。
        使用博查Bocha API搜索指定关键词，并返回格式化的搜索结果。
        参数:
            query: 搜索关键词
            max_results: 最多返回结果数，默认为 5
        返回:
            格式化的搜索结果字符串
        """
        query = kwargs.get("query", "")
        max_results = kwargs.get("max_results", 5)

        if not BOCHA_API_KEY:
            return "搜索出错: 博查API密钥未配置，请设置环境变量 BOCHA_API_KEY"

        def _sync_bocha_search():
            payload = json.dumps({
                "query": query,
                "summary": True,
                "count": max_results
            })
            headers = {
                'Authorization': f'Bearer {BOCHA_API_KEY}',
                'Content-Type': 'application/json'
            }
            resp = requests.post(BOCHA_URL, headers=headers, data=payload, timeout=30)
            return resp.json()

        try:
            # requests是同步，用to_thread包装异步执行
            response_data = await asyncio.to_thread(_sync_bocha_search)

            if response_data.get("code") != 200:
                error_msg = response_data.get("msg", "未知错误")
                return f"API请求失败: {error_msg}"

            data = response_data.get("data", {})
            web_pages = data.get("webPages", {})
            results = web_pages.get("value", [])

            if not results:
                return f"未找到与 '{query}' 相关的搜索结果"

            output_parts = []
            # 优先放博查AI摘要
            if web_pages.get("summary"):
                output_parts.append(f"【AI摘要】\n{web_pages['summary']}\n")

            output_parts.append(f"找到 {len(results)} 条搜索结果：\n")

            for idx, item in enumerate(results, start=1):
                title = item.get("name", "无标题")
                snippet = item.get("snippet", item.get("summary", ""))
                href = item.get("url", "")
                site_name = item.get("siteName", "未知来源")
                date_raw = item.get("datePublished", "")
                date = date_raw.split("T")[0] if date_raw else ""

                snippet_text = snippet[:300] + "..." if len(snippet) > 300 else snippet
                line = f"### {idx}. {title}\n链接: {href}\n来源：{site_name}"
                if date:
                    line += f" 发布日期：{date}"
                line += f"\n{snippet_text}\n"
                output_parts.append(line)

            full_output = "\n".join(output_parts)
            # 全局截断，防止超长文本消耗大量token
            if len(full_output) > _MAX_OUTPUT_CHARS:
                full_output = full_output[:_MAX_OUTPUT_CHARS] + "\n...(输出过长，已截断)"
            return full_output

        except requests.exceptions.Timeout:
            return "搜索出错: 请求超时，请稍后重试"
        except requests.exceptions.RequestException as e:
            return f"搜索出错: 网络异常 {str(e)}"
        except json.JSONDecodeError:
            return "搜索出错: API返回数据解析失败"
        except Exception as e:
            return f"搜索出错: {str(e)}"
