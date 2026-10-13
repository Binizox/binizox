"""LITE 进程的重依赖导入边界。"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


def test_lite_shipping_surface_excludes_knowledge_runtime_routes_skills_and_tools() -> None:
    """Fresh process 的导入图和能力面都不能宣告知识运行时。"""

    backend_root = Path(__file__).resolve().parents[3]
    environment = os.environ.copy()
    environment["LITE_MODE"] = "true"
    environment["PYTHONPATH"] = os.pathsep.join([str(backend_root), str(backend_root / "package")])
    script = """
import os
import sys
if not hasattr(os, "O_DIRECTORY"):
    os.O_DIRECTORY = 0
if not hasattr(os, "O_NOFOLLOW"):
    os.O_NOFOLLOW = 0
import server.main
from binizox.agents.skills.buildin import BUILTIN_SKILLS
from binizox.agents.toolkits.service import get_tool_metadata

forbidden = (
    "binizox.knowledge.runtime",
    "binizox.knowledge.parser.unified",
    "binizox.knowledge.chunking",
    "binizox.knowledge.implementations.milvus",
    "binizox.knowledge.eval",
    "binizox.repositories.knowledge_base_repository",
    "binizox.repositories.knowledge_file_repository",
    "binizox.services.knowledge_dashboard_service",
    "binizox.storage.neo4j",
    "server.routers.knowledge_dashboard_router",
    "server.routers.evidence_router",
    "binizox.evidence",
    "binizox.agents.toolkits.binizox",
)
loaded = sorted(
    name
    for name in sys.modules
    if any(name == prefix or name.startswith(prefix + ".") for prefix in forbidden)
)
if loaded:
    raise SystemExit("LITE imported forbidden modules: " + ", ".join(loaded))

blocked_route_prefixes = (
    "/api/knowledge",
    "/api/evaluation",
    "/api/graph",
    "/api/dashboard/stats/knowledge",
    "/api/workspace/knowledge",
    "/api/binizox/evidence",
)
knowledge_routes = sorted(
    path
    for path in server.main.app.openapi()["paths"]
    if any(path.startswith(prefix) for prefix in blocked_route_prefixes)
)
if knowledge_routes:
    raise SystemExit("LITE advertised knowledge routes: " + ", ".join(knowledge_routes))

builtin_slugs = {spec.slug for spec in BUILTIN_SKILLS}
if "knowledge-base" in builtin_slugs:
    raise SystemExit("LITE advertised builtin knowledge-base Skill")
if "binizox-personal-agent" in builtin_slugs:
    raise SystemExit("LITE advertised Evidence-dependent personal Agent Skill")

knowledge_tools = sorted(
    item["slug"] for item in get_tool_metadata() if item.get("category") == "knowledge"
)
if knowledge_tools:
    raise SystemExit("LITE advertised knowledge tools: " + ", ".join(knowledge_tools))
personal_evidence_tools = sorted(
    item["slug"] for item in get_tool_metadata()
    if item.get("slug") in {"search_binizox_evidence", "save_binizox_note"}
)
if personal_evidence_tools:
    raise SystemExit("LITE advertised Evidence-dependent tools: " + ", ".join(personal_evidence_tools))
"""

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=backend_root,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout


def test_full_shipping_surface_registers_knowledge_dashboard() -> None:
    """完整模式仍必须保留知识域 Dashboard 契约。"""

    backend_root = Path(__file__).resolve().parents[3]
    environment = os.environ.copy()
    environment.pop("LITE_MODE", None)
    environment["PYTHONPATH"] = os.pathsep.join([str(backend_root), str(backend_root / "package")])
    script = """
import os
if not hasattr(os, "O_DIRECTORY"):
    os.O_DIRECTORY = 0
if not hasattr(os, "O_NOFOLLOW"):
    os.O_NOFOLLOW = 0
import server.main

paths = server.main.app.openapi()["paths"]
if "/api/dashboard/stats/knowledge" not in paths:
    raise SystemExit("full mode omitted /api/dashboard/stats/knowledge")
"""

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=backend_root,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
