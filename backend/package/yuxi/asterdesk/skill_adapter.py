"""把 SKILL.md frontmatter 映射为 AsterDesk SkillManifest。"""

from __future__ import annotations

from pathlib import Path

from yuxi.asterdesk._vendor.deerflow_skill_frontmatter import split_skill_markdown
from yuxi.asterdesk.contracts import SkillManifest


def load_skill_manifest(skill_file: Path, *, source: str) -> SkillManifest:
    """读取 Skill 文件并在 AsterDesk 边界执行确定性校验。"""
    parts, error = split_skill_markdown(skill_file.read_text(encoding="utf-8"))
    if error or parts is None:
        raise ValueError(error or "Invalid SKILL.md frontmatter")

    metadata = parts.metadata
    tools = metadata.get("allowed-tools") or []
    if isinstance(tools, str):
        tools = tools.split()
    if not isinstance(tools, list) or not all(isinstance(tool, str) and tool.strip() for tool in tools):
        raise ValueError("allowed-tools must be a string or a list of non-empty strings")

    extension_metadata = metadata.get("metadata") or {}
    if not isinstance(extension_metadata, dict):
        raise ValueError("metadata must be a mapping")
    permissions = extension_metadata.get("permissions") or []
    if not isinstance(permissions, list) or not all(isinstance(item, str) for item in permissions):
        raise ValueError("metadata.permissions must be a list of strings")

    return SkillManifest(
        name=str(metadata.get("name") or ""),
        version=str(metadata.get("version") or "0.1.0"),
        purpose=str(metadata.get("description") or ""),
        required_tools=[tool.strip() for tool in tools],
        required_permissions=permissions,
        source=source,
        visibility=str(extension_metadata.get("visibility") or "private"),
    )
