"""
技能加载器模块

从 skills 目录加载技能定义：
  - 解析 SKILL.md 文件的 frontmatter（YAML 元数据）
  - 构建技能摘要摘要
  - 加载具体技能内容
依赖：pip install pyyaml
"""

from pathlib import Path
from typing import Optional


class SkillsLoader:
    """
    技能加载器。

    从指定目录加载技能定义，每个技能是一个子目录，
    包含一个 SKILL.md 文件，文件开头可以有 YAML frontmatter 元数据。
    """

    def __init__(self, skills_dir: str = "skills") -> None:
        """
        初始化技能加载器。

        参数:
            skills_dir: 技能目录路径，默认为 "skills"
        """
        self._skills_dir = Path(skills_dir)

    def _parse_frontmatter(self, content: str) -> tuple[dict, str]:
        """
        解析 SKILL.md 文件的 frontmatter。

        如果文件以 "---\\n" 开头，找到第二个 "---"，提取中间的 YAML 内容。

        参数:
            content: SKILL.md 文件的完整内容

        返回:
            (metadata字典, 去掉frontmatter后的正文)
            如果没有 frontmatter，返回 (空字典, 原文)
        """
        # 检查是否以 frontmatter 开头
        if not content.startswith("---\n"):
            return {}, content

        # 查找第二个 "---"
        lines = content.split("\n")
        end_index = -1

        for i, line in enumerate(lines[1:], start=1):
            if line.strip() == "---":
                end_index = i
                break

        # 如果没有找到结束的 "---"，返回原文
        if end_index == -1:
            return {}, content

        # 提取 YAML 内容
        yaml_lines = lines[1:end_index]
        yaml_content = "\n".join(yaml_lines)

        # 提取正文（去掉 frontmatter 后的内容）
        body_lines = lines[end_index + 1 :]
        body = "\n".join(body_lines).strip()

        # 解析 YAML
        try:
            import yaml
            metadata = yaml.safe_load(yaml_content) or {}
        except Exception:
            metadata = {}

        return metadata, body

    def build_skills_summary(self) -> str:
        """
        构建技能摘要列表。

        遍历 skills_dir 下的每个子目录，查找 SKILL.md 文件，
        解析 frontmatter 获取 name 和 description，格式化为摘要列表。

        返回:
            技能目录字符串，如果没有技能则返回空字符串
        """
        # 检查技能目录是否存在
        if not self._skills_dir.exists() or not self._skills_dir.is_dir():
            return ""

        skills_list = []

        # 遍历技能目录下的子目录
        for skill_dir in self._skills_dir.iterdir():
            if not skill_dir.is_dir():
                continue

            skill_file = skill_dir / "SKILL.md"
            if not skill_file.exists():
                continue

            # 读取并解析 SKILL.md
            try:
                content = skill_file.read_text(encoding="utf-8")
                metadata, _ = self._parse_frontmatter(content)

                name = metadata.get("name", skill_dir.name)
                description = metadata.get("description", "无描述")

                # 计算相对路径
                relative_path = skill_dir.relative_to(self._skills_dir.parent)

                skills_list.append(f"- {name} ({relative_path}/SKILL.md)：{description}")
            except Exception:
                continue

        # 如果没有找到任何技能，返回空字符串
        if not skills_list:
            return ""

        # 构建完整的技能目录字符串
        header = (
            "你有以下技能可用。当你需要使用某项技能时，\n"
            "请先用 read_file 工具读取对应的 SKILL.md 文件获取详细指南。\n\n"
            "可用技能：\n"
        )

        return header + "\n".join(skills_list)

    def load_skill(self, name: str) -> Optional[str]:
        """
        加载指定技能的正文内容。

        在 skills_dir 下查找名为 name 的子目录中的 SKILL.md，
        读取文件内容，去掉 frontmatter，返回正文内容。

        参数:
            name: 技能名称（子目录名）

        返回:
            技能正文内容，如果找不到则返回 None
        """
        skill_file = self._skills_dir / name / "SKILL.md"

        if not skill_file.exists():
            return None

        try:
            content = skill_file.read_text(encoding="utf-8")
            _, body = self._parse_frontmatter(content)
            return body
        except Exception:
            return None

    def list_skills(self) -> list[dict]:
        """
        列出所有已发现的技能信息。

        返回:
            包含所有技能的 [{name, description, path}] 列表
        """
        skills_list = []

        if not self._skills_dir.exists() or not self._skills_dir.is_dir():
            return skills_list

        for skill_dir in self._skills_dir.iterdir():
            if not skill_dir.is_dir():
                continue

            skill_file = skill_dir / "SKILL.md"
            if not skill_file.exists():
                continue

            try:
                content = skill_file.read_text(encoding="utf-8")
                metadata, _ = self._parse_frontmatter(content)

                skills_list.append({
                    "name": metadata.get("name", skill_dir.name),
                    "description": metadata.get("description", "无描述"),
                    "path": str(skill_file),
                })
            except Exception:
                continue

        return skills_list
