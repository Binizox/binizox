"""验证 AsterDesk 政策问答经过真实 API、worker、LangGraph、SSE 和持久化。"""

from __future__ import annotations

import os
import uuid

import asyncpg
import httpx
import pytest

from e2e_helpers import consume_events, delete_agent, postgres_dsn, wait_for_run
from test.live_api_cleanup import make_test_conversation_metadata, make_test_conversation_title

pytestmark = [pytest.mark.asyncio, pytest.mark.e2e, pytest.mark.slow]

QUESTION = "申请某软件权限需要提供什么材料？"
EXPECTED_CITATION = "[AsterDesk-IT-POL-001 v1.0, §3 申请材料]"
PROVIDER_ID = "asterdesk-replay"
MODEL_SPEC = f"{PROVIDER_ID}:policy-chat"


async def _create_provider(client: httpx.AsyncClient, headers: dict[str, str]) -> None:
    deleted = await client.delete(f"/api/system/model-providers/{PROVIDER_ID}", headers=headers)
    assert deleted.status_code in {200, 404}, deleted.text
    response = await client.post(
        "/api/system/model-providers",
        json={
            "provider_id": PROVIDER_ID,
            "display_name": "AsterDesk policy replay",
            "provider_type": "openai",
            "base_url": "http://api:8766/v1",
            "api_key": "asterdesk-replay-key",
            "capabilities": ["chat"],
            "enabled_models": [
                {"id": "policy-chat", "display_name": "Policy replay", "type": "chat", "source": "manual"}
            ],
            "is_enabled": True,
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text


async def _create_agent(client: httpx.AsyncClient, headers: dict[str, str], uid: str) -> str:
    slug = f"asterdesk-policy-{uuid.uuid4().hex[:8]}"
    response = await client.post(
        "/api/agent",
        json={
            "name": f"AsterDesk Policy {slug[-8:]}",
            "slug": slug,
            "backend_id": "ChatbotAgent",
            "description": "第一阶段虚构 IT 政策问答",
            "config_json": {
                "context": {
                    "model": MODEL_SPEC,
                    "system_prompt": "仅根据预加载的 AsterDesk IT 政策回答，并给出精确来源。",
                    "tools": [],
                    "knowledges": [],
                    "mcps": [],
                    "skills": ["asterdesk-it-policy"],
                    "preload_skills": ["asterdesk-it-policy"],
                    "subagents": [],
                }
            },
            "share_config": {
                "version": 2,
                "read_scope": {"access_level": "user", "department_ids": [], "user_uids": [uid]},
                "manage_scope": None,
            },
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return slug


async def _assert_persisted_result(run_id: str, request_id: str) -> None:
    conn = await asyncpg.connect(postgres_dsn())
    try:
        row = await conn.fetchrow(
            """
            SELECT run.status, run.request_id, run.output_message_id,
                   message.run_id AS output_run_id, message.content
            FROM agent_runs run
            LEFT JOIN messages message ON message.id = run.output_message_id
            WHERE run.id = $1
            """,
            run_id,
        )
        assert row
        assert row["status"] == "completed"
        assert row["request_id"] == request_id
        assert row["output_message_id"] is not None
        assert row["output_run_id"] == run_id
        assert EXPECTED_CITATION in row["content"]
    finally:
        await conn.close()


async def test_policy_question_reaches_cited_persisted_result(
    e2e_client: httpx.AsyncClient,
    e2e_headers: dict[str, str],
) -> None:
    me = await e2e_client.get("/api/auth/me", headers=e2e_headers)
    assert me.status_code == 200, me.text
    uid = str(me.json()["uid"])

    await _create_provider(e2e_client, e2e_headers)
    agent_slug: str | None = None
    thread_id: str | None = None
    try:
        agent_slug = await _create_agent(e2e_client, e2e_headers, uid)
        thread = await e2e_client.post(
            "/api/chat/thread",
            json={
                "agent_id": agent_slug,
                "title": make_test_conversation_title("asterdesk-policy"),
                "metadata": make_test_conversation_metadata("asterdesk-policy", e2e=True),
            },
            headers=e2e_headers,
        )
        assert thread.status_code == 200, thread.text
        thread_id = str(thread.json().get("thread_id") or thread.json()["id"])
        request_id = f"asterdesk-policy-{uuid.uuid4()}"

        created = await e2e_client.post(
            "/api/agent/runs",
            json={
                "query": QUESTION,
                "agent_slug": agent_slug,
                "thread_id": thread_id,
                "meta": {"request_id": request_id},
            },
            headers=e2e_headers,
        )
        assert created.status_code == 200, created.text
        run_id = str(created.json()["run_id"])

        event_counts = await consume_events(e2e_client, e2e_headers, run_id)
        assert event_counts.get("messages", 0) > 0, event_counts
        assert event_counts.get("end", 0) == 1, event_counts

        run = await wait_for_run(e2e_client, e2e_headers, run_id)
        assert run["status"] == "completed", run
        result = await e2e_client.get(f"/api/agent/runs/{run_id}/result", headers=e2e_headers)
        assert result.status_code == 200, result.text
        assert EXPECTED_CITATION in result.json()["output"]
        await _assert_persisted_result(run_id, request_id)
    finally:
        keep_artifacts = os.getenv("ASTERDESK_E2E_KEEP_ARTIFACTS") == "1"
        if not keep_artifacts:
            if thread_id:
                deleted = await e2e_client.delete(f"/api/chat/thread/{thread_id}", headers=e2e_headers)
                assert deleted.status_code in {200, 404}, deleted.text
            if agent_slug:
                await delete_agent(e2e_client, e2e_headers, agent_slug)
            deleted_provider = await e2e_client.delete(
                f"/api/system/model-providers/{PROVIDER_ID}", headers=e2e_headers
            )
            assert deleted_provider.status_code in {200, 404}, deleted_provider.text
