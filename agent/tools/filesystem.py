"""
文件系统工具模块

提供文件读写和目录列表功能，所有操作都限制在指定的工作区内，
防止路径穿越攻击。
"""

import os
from typing import Any

from agent.tools.base import Tool

# 读取文件时的最大输出字符数，超过则截断
_MAX_OUTPUT_CHARS = 16000


def _safe_resolve(workspace: str, user_path: str) -> str:
    """
    解析用户路径并验证其在工作区内。

    返回安全的绝对路径；若路径越界则抛出 ValueError。
    """
    absolute = os.path.abspath(os.path.join(workspace, user_path))
    # 加 os.sep 防止 /workspace2 绕过 /workspace 的检查
    if not (absolute == workspace or absolute.startswith(workspace + os.sep)):
        raise ValueError(f"路径 '{user_path}' 越界，不允许跳出工作区")
    return absolute


class ReadFileTool(Tool):
    """读取工作区内的文件"""

    def __init__(self, workspace: str) -> None:
        self._workspace = os.path.abspath(workspace)

    @property
    def name(self) -> str:
        return "read_file"

    @property
    def description(self) -> str:
        return "读取工作区内指定路径的文件内容，超过 16000 字符会自动截断"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "要读取的文件路径（相对于工作区）",
                }
            },
            "required": ["file_path"],
        }

    async def execute(self, **kwargs) -> str:
        file_path = kwargs["file_path"]
        try:
            absolute = _safe_resolve(self._workspace, file_path)
            with open(absolute, "r", encoding="utf-8") as f:
                content = f.read()
            if len(content) > _MAX_OUTPUT_CHARS:
                content = content[:_MAX_OUTPUT_CHARS] + "\n...（已截断）"
            return content
        except ValueError as e:
            return f"安全检查失败：{e}"
        except Exception as e:
            return f"读取文件失败：{e}"


class WriteFileTool(Tool):
    """写入文件到工作区"""

    def __init__(self, workspace: str) -> None:
        self._workspace = os.path.abspath(workspace)

    @property
    def name(self) -> str:
        return "write_file"

    @property
    def description(self) -> str:
        return "将内容写入工作区内指定路径的文件，自动创建不存在的父目录"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "要写入的文件路径（相对于工作区）",
                },
                "content": {
                    "type": "string",
                    "description": "要写入的文件内容",
                },
            },
            "required": ["file_path", "content"],
        }

    async def execute(self, **kwargs) -> str:
        file_path = kwargs["file_path"]
        content = kwargs["content"]
        try:
            absolute = _safe_resolve(self._workspace, file_path)
            os.makedirs(os.path.dirname(absolute), exist_ok=True)
            with open(absolute, "w", encoding="utf-8") as f:
                f.write(content)
            return f"成功写入文件：{file_path}"
        except ValueError as e:
            return f"安全检查失败：{e}"
        except Exception as e:
            return f"写入文件失败：{e}"


class ListDirTool(Tool):
    """列出目录内容"""

    def __init__(self, workspace: str) -> None:
        self._workspace = os.path.abspath(workspace)

    @property
    def name(self) -> str:
        return "list_dir"

    @property
    def description(self) -> str:
        return "列出工作区内指定目录的文件和子目录，显示文件大小和类型"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "dir_path": {
                    "type": "string",
                    "description": "要列出的目录路径（相对于工作区），默认为工作区根目录",
                    "default": ".",
                }
            },
            "required": [],
        }

    async def execute(self, **kwargs) -> str:
        dir_path = kwargs.get("dir_path", ".")
        try:
            absolute = _safe_resolve(self._workspace, dir_path)
            if not os.path.isdir(absolute):
                return f"错误：'{dir_path}' 不是目录"

            entries = []
            for entry in os.scandir(absolute):
                if entry.is_dir():
                    entries.append(f"{entry.name}/")
                else:
                    size = entry.stat().st_size
                    entries.append(f"{entry.name} ({self._format_size(size)})")

            entries.sort()
            return "\n".join(entries) if entries else "（空目录）"
        except ValueError as e:
            return f"安全检查失败：{e}"
        except Exception as e:
            return f"列出目录失败：{e}"

    @staticmethod
    def _format_size(size: int) -> str:
        """格式化文件大小"""
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"
