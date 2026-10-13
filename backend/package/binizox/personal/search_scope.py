"""Binizox 检索工具的 Agent 知识库范围收敛。"""

from __future__ import annotations


def resolve_knowledge_base_scope(
    visible_knowledge_bases: list[dict],
    requested_ids: list[str] | None,
) -> list[str]:
    """把模型请求限制在当前 Agent 已启用且用户可见的知识库内。"""

    visible_ids = list(
        dict.fromkeys(
            str(item.get("kb_id") or "").strip()
            for item in visible_knowledge_bases
            if str(item.get("kb_id") or "").strip()
        )
    )
    requested = list(
        dict.fromkeys(str(value).strip() for value in (requested_ids or []) if str(value).strip())
    )
    if not requested:
        return visible_ids

    allowed = set(visible_ids)
    return [kb_id for kb_id in requested if kb_id in allowed]
