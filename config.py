"""NanoClaw 配置模块"""

import json
import os
from dataclasses import dataclass

@dataclass
class NanoClawConfig:
    """NanoClaw 运行配置"""
    api_key: str = ""
    base_url: str = "https://api.siliconflow.cn/v1"
    model: str = "deepseek-ai/DeepSeek-V4-Flash"
    models: dict = None  # {"main": "...", "subagent": "...", "cheap": "..."}
    workspace: str = "."
    max_iterations: int = 32
    identity_file: str = "identity.md"
    # 飞书配置
    feishu_app_id: str = ""
    feishu_app_secret: str = ""
    # QQ 配置
    qq_app_id: str = ""
    qq_app_secret: str = ""
    # Web 配置
    web_enabled: bool = True
    web_host: str = "0.0.0.0"
    web_port: int = 8080
    # MCP 配置
    mcp_servers: dict = None  # {server_name: {command, args, env}}

def load_config(config_path: str = "config.json") -> NanoClawConfig:
    """
    加载配置文件

    Args:
        config_path: 配置文件路径（JSON 格式）

    Returns:
        NanoClawConfig: 配置对象
    """
    config = NanoClawConfig()

    # 读取 JSON 文件
    if os.path.isfile(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            for key in ["api_key", "base_url", "model", "workspace", "max_iterations", "identity_file"]:
                if key in data:
                    setattr(config, key, data[key])


            # 加载多模型配置
            if "models" in data:
                config.models = data["models"]
                # 如果没有单独的 model 字段，用 models.main
                if "model" not in data and "main" in config.models:
                    config.model = config.models["main"]

            # 加载飞书配置
            feishu = data.get("feishu", {})
            if feishu.get("app_id"):
                config.feishu_app_id = feishu["app_id"]
            if feishu.get("app_secret"):
                config.feishu_app_secret = feishu["app_secret"]

            # 加载 QQ 配置
            qq = data.get("qq", {})
            if qq.get("app_id"):
                config.qq_app_id = qq["app_id"]
            if qq.get("app_secret"):
                config.qq_app_secret = qq["app_secret"]
            
            # 加载 Web 配置
            web = data.get("web", {})
            if "enabled" in web:
                config.web_enabled = web["enabled"]
            if web.get("host"):
                config.web_host = web["host"]
            if web.get("port"):
                config.web_port = web["port"]

            # 加载 MCP 配置
            if data.get("mcp_servers"):
                config.mcp_servers = data["mcp_servers"]

        except Exception:
            pass

    # 环境变量优先级最高
    if env_key := os.environ.get("NANOCLAW_API_KEY"):
        config.api_key = env_key

    return config
