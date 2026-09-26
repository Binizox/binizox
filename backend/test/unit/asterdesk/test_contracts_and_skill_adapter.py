from pathlib import Path

import pytest
from pydantic import ValidationError

from yuxi.asterdesk.contracts import ToolInvocation
from yuxi.asterdesk.skill_adapter import load_skill_manifest


def test_tool_invocation_requires_non_empty_idempotency_key() -> None:
    with pytest.raises(ValidationError):
        ToolInvocation(run_id="run-1", tool_name="grant-access", arguments={}, idempotency_key="")


def test_deerflow_frontmatter_adapter_loads_asterdesk_skill() -> None:
    skill_file = (
        Path(__file__).parents[3]
        / "package"
        / "yuxi"
        / "agents"
        / "skills"
        / "buildin"
        / "asterdesk-it-policy"
        / "SKILL.md"
    )

    manifest = load_skill_manifest(skill_file, source="builtin://asterdesk-it-policy")

    assert manifest.name == "asterdesk-it-policy"
    assert manifest.version == "1.0.0"
    assert manifest.required_tools == []
    assert manifest.required_permissions == ["knowledge:it-policy:read"]
    assert manifest.visibility == "tenant"


def test_deerflow_frontmatter_adapter_rejects_missing_frontmatter(tmp_path: Path) -> None:
    skill_file = tmp_path / "SKILL.md"
    skill_file.write_text("# missing frontmatter\n", encoding="utf-8")

    with pytest.raises(ValueError, match="No YAML frontmatter found"):
        load_skill_manifest(skill_file, source="test://invalid")
