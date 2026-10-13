"""Binizox Agent 到独立个人工具服务的 HTTP 适配器。"""

from __future__ import annotations

import os

import httpx


class PersonalToolRunnerError(RuntimeError):
    """个人工具服务不可用或拒绝调用。"""


async def invoke_personal_tool(payload: dict) -> dict:
    """调用独立工具服务，并返回标准化 ToolResult。

    人工确认发生在 LangGraph HumanInTheLoopMiddleware 中，因此只有确认后的
    tool call 才会执行到这里。适配器仍然携带固定幂等键，以处理 worker 重试。
    """

    base_url = os.getenv("BINIZOX_TOOL_RUNNER_URL", "http://127.0.0.1:8091").rstrip("/")
    service_token = os.getenv("BINIZOX_TOOL_RUNNER_TOKEN", "").strip()
    if not service_token:
        raise PersonalToolRunnerError("个人工具服务凭据未配置")
    timeout = float(os.getenv("BINIZOX_TOOL_TIMEOUT_SECONDS", "30"))
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{base_url}/v1/invocations",
                json=payload,
                headers={"Authorization": f"Bearer {service_token}"},
            )
    except httpx.HTTPError as exc:
        raise PersonalToolRunnerError(f"个人工具服务连接失败：{exc}") from exc

    if response.status_code >= 400:
        raise PersonalToolRunnerError(f"个人工具服务拒绝调用：HTTP {response.status_code} {response.text[:500]}")
    result = response.json()
    if not isinstance(result, dict):
        raise PersonalToolRunnerError("个人工具服务返回了无效结果")
    return result


async def get_personal_tool_runner_health() -> dict:
    """读取个人工具服务健康状态，不把内部地址暴露给浏览器。"""

    base_url = os.getenv("BINIZOX_TOOL_RUNNER_URL", "http://127.0.0.1:8091").rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            response = await client.get(f"{base_url}/health")
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPError:
        # 浏览器只需要能力状态；连接异常可能包含内部服务名和端口，不能透传。
        return {"status": "unavailable"}
    except ValueError:
        return {"status": "invalid_response"}
    return payload if isinstance(payload, dict) else {"status": "invalid_response"}
