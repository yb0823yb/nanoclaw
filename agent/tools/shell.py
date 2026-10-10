"""
Shell 命令执行工具模块

提供在工作区内执行 Shell 命令的功能，包含安全防护机制：
  - 危险命令拦截（rm -rf、sudo 等）
  - 超时控制（60秒）
  - 输出截断（10000字符）
"""

import asyncio
import os
import re
from typing import Any

from agent.tools.base import Tool

# 输出最大字符数，超过则截断
_MAX_OUTPUT_CHARS = 10000

# 命令执行超时时间（秒）
_TIMEOUT_SECONDS = 60


class ExecTool(Tool):
    """
    Shell 命令执行工具。

    在指定工作目录下执行 Shell 命令，并返回输出结果。
    内置安全防护机制，拦截危险命令。
    """

    def __init__(self, workspace: str = ".") -> None:
        """
        初始化 Shell 执行工具。

        参数:
            workspace: 工作目录路径，命令在此目录下执行，默认为当前目录
        """
        self._workspace = os.path.abspath(workspace)

    @property
    def name(self) -> str:
        return "exec_shell"

    @property
    def description(self) -> str:
        return "在工作区目录下执行 Shell 命令，返回命令输出结果。支持超时控制（60秒）和输出截断（10000字符）"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "要执行的 Shell 命令",
                }
            },
            "required": ["command"],
        }

    def _is_dangerous(self, command: str) -> str | None:
        """
        检查命令是否包含危险模式。

        遍历预定义的危险命令模式列表，使用正则匹配检查命令。

        参数:
            command: 要检查的命令字符串

        返回:
            如果检测到危险模式，返回拦截信息字符串；否则返回 None
        """
        deny_patterns = [
            r"rm\s+.*-r",           # 递归删除
            r"rm\s+-rf",            # 递归强制删除
            r"rmdir\s+/s",          # Windows 递归删除
            r"format\s+",           # 格式化磁盘
            r"mkfs",                # Linux 格式化
            r"shutdown",            # 关机
            r"reboot",              # 重启
            r"sudo\s+",             # sudo 提权
            r"\bsu\b",              # su 提权
            r"chmod\s+777",         # 危险权限修改
            r">\s*/dev/",           # 覆盖设备文件
            r"wget\s+.*\|\s*sh",    # 下载执行恶意脚本
            r"curl\s+.*\|\s*bash",  # 下载执行恶意脚本
            r"nc\s+-l",             # 开网络后门
            r"ncat\s+-l",           # 开网络后门
            r"dd\s+if=",            # 磁盘镜像覆写
            r":\(\)\{.*\}",         # Fork 炸弹
        ]

        for pattern in deny_patterns:
            if re.search(pattern, command, re.IGNORECASE):
                return f"安全拦截：检测到危险命令模式 '{pattern}'"

        return None

    async def execute(self, **kwargs) -> str:
        """
        执行 Shell 命令。

        流程：
          1. 安全检查：拦截危险命令
          2. 创建子进程执行命令
          3. 等待命令完成（60秒超时）
          4. 收集输出并截断
          5. 返回结果

        参数:
            command: 要执行的 Shell 命令

        返回:
            命令执行结果（stdout + stderr + 退出码）
        """
        command = kwargs.get("command", "")

        # 1. 安全检查
        danger_check = self._is_dangerous(command)
        if danger_check is not None:
            return danger_check

        try:
            # 2. 创建子进程
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self._workspace,
            )

            # 3. 等待命令完成（带超时）
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                # 超时：终止进程
                process.kill()
                await process.wait()
                return "命令执行超时（60秒），已终止"

            # 4. 拼接输出
            output_parts = []

            # stdout
            stdout_text = stdout.decode("utf-8", errors="replace")
            if stdout_text:
                output_parts.append(stdout_text)

            # stderr
            stderr_text = stderr.decode("utf-8", errors="replace")
            if stderr_text:
                output_parts.append(f"标准错误:\n{stderr_text}")

            # 合并输出
            full_output = "\n".join(output_parts) if output_parts else ""

            # 5. 截断过长输出
            if len(full_output) > _MAX_OUTPUT_CHARS:
                full_output = full_output[:_MAX_OUTPUT_CHARS] + "\n...(输出过长，已截断)"

            # 6. 添加退出码信息
            exit_code = process.returncode
            full_output += f"\n[退出码: {exit_code}]"

            return full_output

        except Exception as e:
            # 7. 捕获所有异常
            return f"命令执行失败: {e}"
