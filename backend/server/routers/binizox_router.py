"""Binizox 产品信息与本地集成状态 API。"""

from fastapi import APIRouter

from yuxi.binizox.integrations import list_upstream_integrations
from yuxi.binizox.tool_runner_client import get_personal_tool_runner_health

binizox = APIRouter(prefix="/binizox", tags=["Binizox"])


@binizox.get("/info")
async def get_binizox_info() -> dict:
    """返回不包含凭据和内部地址的产品能力摘要。"""

    return {
        "name": "Binizox",
        "mode": "personal-local-first",
        "version": "0.1.0-dev",
        "integrations": list_upstream_integrations(),
    }


@binizox.get("/tool-runner/health")
async def get_tool_runner_health() -> dict:
    """由后端代理健康检查，浏览器无需知道工具服务内部地址。"""

    return await get_personal_tool_runner_health()
