"""Binizox 上游状态与工具确认策略的最小契约测试。"""

import importlib.util
from pathlib import Path
import runpy

import httpx
import pytest

from yuxi.binizox import tool_runner_client
from yuxi.binizox.integrations import list_upstream_integrations
from yuxi.binizox.search_scope import resolve_knowledge_base_scope


# yuxi.agents.__init__ 会加载完整数据库和模型依赖。该测试只验证独立策略模块，
# 因此直接从文件加载，避免把“未安装完整平台依赖”误判为策略代码失败。
_POLICY_PATH = Path(__file__).parents[3] / "package" / "yuxi" / "agents" / "tool_approval.py"
_POLICY_SPEC = importlib.util.spec_from_file_location("binizox_tool_approval_under_test", _POLICY_PATH)
assert _POLICY_SPEC is not None and _POLICY_SPEC.loader is not None
_POLICY_MODULE = importlib.util.module_from_spec(_POLICY_SPEC)
_POLICY_SPEC.loader.exec_module(_POLICY_MODULE)
_BUILTIN_SKILLS_PATH = Path(__file__).parents[3] / "package" / "yuxi" / "agents" / "skills" / "buildin" / "__init__.py"


def test_all_fixed_upstreams_are_listed_without_overstating_integration() -> None:
    integrations = list_upstream_integrations()
    by_name = {item["name"]: item for item in integrations}

    assert set(by_name) == {"Yuxi", "RAGFlow", "WeKnora", "DeerFlow", "LibreChat", "DeepSeek Harness"}
    assert by_name["Yuxi"]["state"] == "active"
    assert by_name["RAGFlow"]["state"] == "active"
    assert by_name["DeerFlow"]["state"] == "active"
    assert by_name["WeKnora"]["state"] == "candidate"
    assert by_name["LibreChat"]["state"] == "reference"
    assert by_name["DeepSeek Harness"]["state"] == "reference"


def test_note_write_is_guarded_by_human_approval() -> None:
    assert "save_binizox_note" in _POLICY_MODULE.SENSITIVE_BACKEND_TOOLS
    assert _POLICY_MODULE.create_tool_approval_middleware("default") is not None
    assert _POLICY_MODULE.create_tool_approval_middleware("always_trust") is None


def test_binizox_skill_is_registered_with_its_gated_tools() -> None:
    namespace = runpy.run_path(str(_BUILTIN_SKILLS_PATH))
    by_slug = {spec.slug: spec for spec in namespace["BUILTIN_SKILLS"]}

    spec = by_slug["binizox-personal-agent"]
    assert spec.source_dir.is_dir()
    assert spec.tool_dependencies == ("search_binizox_evidence", "save_binizox_note")


def test_search_scope_defaults_to_agent_visible_knowledge_bases() -> None:
    visible = [{"kb_id": "personal"}, {"kb_id": "projects"}, {"kb_id": "personal"}]

    assert resolve_knowledge_base_scope(visible, []) == ["personal", "projects"]


def test_search_scope_rejects_model_requested_out_of_scope_knowledge_base() -> None:
    visible = [{"kb_id": "personal"}]

    assert resolve_knowledge_base_scope(visible, ["other-tenant", "personal"]) == ["personal"]
    assert resolve_knowledge_base_scope(visible, ["other-tenant"]) == []


@pytest.mark.asyncio
async def test_tool_runner_health_hides_internal_connection_details(monkeypatch) -> None:
    class UnavailableClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, _url):
            raise httpx.ConnectError("failed: http://binizox-tool-runner:8091/health")

    monkeypatch.setattr(tool_runner_client.httpx, "AsyncClient", UnavailableClient)

    result = await tool_runner_client.get_personal_tool_runner_health()

    assert result == {"status": "unavailable"}
    assert "8091" not in str(result)


@pytest.mark.asyncio
async def test_tool_runner_health_rejects_invalid_json(monkeypatch) -> None:
    class InvalidResponse:
        def raise_for_status(self):
            return None

        def json(self):
            raise ValueError("not json")

    class InvalidJsonClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, _url):
            return InvalidResponse()

    monkeypatch.setattr(tool_runner_client.httpx, "AsyncClient", InvalidJsonClient)

    assert await tool_runner_client.get_personal_tool_runner_health() == {
        "status": "invalid_response"
    }
