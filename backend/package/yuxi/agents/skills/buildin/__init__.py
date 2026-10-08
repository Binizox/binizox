from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from yuxi.config.runtime import knowledge_capability_enabled


@dataclass(frozen=True)
class BuiltinSkillSpec:
    slug: str
    source_dir: Path
    description: str = ""
    version: str = "1.0.0"
    tool_dependencies: tuple[str, ...] = ()
    mcp_dependencies: tuple[str, ...] = ()
    skill_dependencies: tuple[str, ...] = ()


_SKILLS_ROOT = Path(__file__).resolve().parent

BUILTIN_SKILLS: list[BuiltinSkillSpec] = [
    BuiltinSkillSpec(
        slug="binizox-personal-agent",
        source_dir=_SKILLS_ROOT / "binizox-personal-agent",
        description="检索个人资料、生成带来源回答，并在用户确认后保存个人笔记。",
        version="0.1.0",
        tool_dependencies=("search_binizox_evidence", "save_binizox_note"),
    ),
    BuiltinSkillSpec(
        slug="asterdesk-vpn-access",
        source_dir=_SKILLS_ROOT / "asterdesk-vpn-access",
        description="AsterDesk 第三阶段 VPN 权限申请、业务审批和可恢复执行。",
        version="3.0.0",
        tool_dependencies=("search_asterdesk_evidence", "request_vpn_access", "ask_user_question"),
    ),
    BuiltinSkillSpec(
        slug="asterdesk-evidence",
        source_dir=_SKILLS_ROOT / "asterdesk-evidence",
        description="AsterDesk 第二阶段服务端权限过滤的文档证据检索。",
        version="2.0.0",
        tool_dependencies=("search_asterdesk_evidence",),
    ),
    BuiltinSkillSpec(
        slug="asterdesk-it-policy",
        source_dir=_SKILLS_ROOT / "asterdesk-it-policy",
        description="AsterDesk 第一阶段用于验证带来源企业政策问答的虚构 IT 政策。",
        version="1.0.0",
    ),
    BuiltinSkillSpec(
        slug="image-gen",
        source_dir=_SKILLS_ROOT / "image-gen",
        description="在 Agent 沙盒中生成图片并保存到 outputs，默认支持 Qwen-Image，也可接入其它图片生成接口。",
        version="2026.06.02",
        tool_dependencies=("present_artifacts",),
    ),
    BuiltinSkillSpec(
        slug="html-preview",
        source_dir=_SKILLS_ROOT / "html-preview",
        description=(
            "使用 Markdown `html:preview` 围栏输出轻量静态 HTML/CSS 可视化，"
            "适合数值对比、流程、时间线、层级关系和关键指标。"
        ),
        version="2026.07.23",
    ),
    BuiltinSkillSpec(
        slug="deep-research",
        source_dir=_SKILLS_ROOT / "deep-research",
        description="深度研究编排方法论：澄清范围、拆解规划、并行调度子智能体调研、对抗式核验、综合成带引用的结构化报告。",
        version="2026.07.29",
        tool_dependencies=("web_search",),
        skill_dependencies=("html-preview",),
    ),
]

if knowledge_capability_enabled():
    BUILTIN_SKILLS.append(
        BuiltinSkillSpec(
            slug="knowledge-base",
            source_dir=_SKILLS_ROOT / "knowledge-base",
            description="使用 Yuxi 知识库进行检索、打开文档、文档内定位和查看思维导图。",
            version="2026.06.24",
            tool_dependencies=(
                "list_kbs",
                "query_kb",
                "find_kb_document",
                "open_kb_document",
                "get_mindmap",
                "search_file",
                "download_kb_file",
            ),
        )
    )

BUILTIN_SKILLS.append(
    BuiltinSkillSpec(
        slug="mysql-reporter",
        source_dir=_SKILLS_ROOT / "mysql-reporter",
        description="基于 MySQL 数据库生成查询报表和可视化图表，适合分析业务指标、统计趋势，并用 Charts MCP 展示结果。",
        version="2026.06.05",
        mcp_dependencies=("mcp-server-chart",),
    )
)
