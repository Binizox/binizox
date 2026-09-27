"""第三阶段 VPN 申请、审批、幂等执行和恢复的隔离环境验收。"""

from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path

import asyncpg
import httpx
import pytest

from e2e_helpers import postgres_dsn, wait_for_run
from test.live_api_cleanup import make_test_conversation_metadata, make_test_conversation_title
from yuxi.services.asterdesk_action_worker import enqueue_asterdesk_action

pytestmark = [pytest.mark.asyncio, pytest.mark.e2e, pytest.mark.slow]

KB_ID = "asterdesk-phase3-vpn"
DOCUMENT_ID = "AD-VPN-POLICY-001"
PROVIDER_ID = "asterdesk-vpn-replay"
MODEL_SPEC = f"{PROVIDER_ID}:vpn-chat"


async def _create_user(
    client: httpx.AsyncClient,
    admin_headers: dict[str, str],
    department_id: int,
    *,
    role: str = "user",
) -> dict:
    suffix = uuid.uuid4().hex[:10]
    password = f"Pw!{uuid.uuid4().hex[:16]}"
    response = await client.post(
        "/api/auth/users",
        json={"username": f"phase3_{suffix}", "password": password, "role": role, "department_id": department_id},
        headers=admin_headers,
    )
    assert response.status_code == 200, response.text
    user = response.json()
    login = await client.post("/api/auth/token", data={"username": user["uid"], "password": password})
    assert login.status_code == 200, login.text
    return {"user": user, "headers": {"Authorization": f"Bearer {login.json()['access_token']}"}}


async def _seed_kb(admin_uid: str, department_id: int) -> None:
    share = {
        "version": 2,
        "read_scope": {"access_level": "department", "department_ids": [department_id], "user_uids": []},
        "manage_scope": {"access_level": "department", "department_ids": [department_id], "user_uids": []},
    }
    conn = await asyncpg.connect(postgres_dsn())
    try:
        async with conn.transaction():
            await conn.execute("DELETE FROM knowledge_chunks WHERE kb_id=$1", KB_ID)
            await conn.execute("DELETE FROM knowledge_files WHERE kb_id=$1", KB_ID)
            await conn.execute("DELETE FROM knowledge_bases WHERE kb_id=$1", KB_ID)
            await conn.execute(
                """
                INSERT INTO knowledge_bases
                    (kb_id, name, description, kb_type, additional_params,
                     share_config, created_by, created_at, updated_at)
                VALUES ($1, 'VPN policy', 'Phase 3 policy', 'dify', '{}'::jsonb, $2::jsonb, $3, NOW(), NOW())
                """,
                KB_ID,
                json.dumps(share),
                admin_uid,
            )
    finally:
        await conn.close()


async def _configure_agent(client: httpx.AsyncClient, headers: dict[str, str], users: list[str]) -> str:
    deleted = await client.delete(f"/api/system/model-providers/{PROVIDER_ID}", headers=headers)
    assert deleted.status_code in {200, 404}, deleted.text
    provider = await client.post(
        "/api/system/model-providers",
        json={
            "provider_id": PROVIDER_ID,
            "display_name": "AsterDesk VPN replay",
            "provider_type": "openai",
            "base_url": "http://asterdesk-vpn-replay:8768/v1",
            "api_key": "asterdesk-vpn-replay-key",
            "capabilities": ["chat"],
            "enabled_models": [{"id": "vpn-chat", "display_name": "VPN replay", "type": "chat", "source": "manual"}],
            "is_enabled": True,
        },
        headers=headers,
    )
    assert provider.status_code == 200, provider.text
    slug = f"asterdesk-vpn-{uuid.uuid4().hex[:8]}"
    agent = await client.post(
        "/api/agent",
        json={
            "name": f"VPN Agent {slug[-8:]}",
            "slug": slug,
            "backend_id": "ChatbotAgent",
            "description": "Phase 3 VPN approval E2E",
            "config_json": {
                "context": {
                    "model": MODEL_SPEC,
                    "system_prompt": "严格按 VPN Skill 检索、收集、申请并等待业务审批。",
                    "tools": [],
                    "knowledges": [],
                    "mcps": [],
                    "skills": ["asterdesk-vpn-access"],
                    "preload_skills": ["asterdesk-vpn-access"],
                    "subagents": [],
                }
            },
            "share_config": {
                "version": 2,
                "read_scope": {"access_level": "user", "department_ids": [], "user_uids": users},
                "manage_scope": None,
            },
        },
        headers=headers,
    )
    assert agent.status_code == 200, agent.text
    return slug


async def _start_application(
    client: httpx.AsyncClient,
    applicant: dict,
    agent_slug: str,
    label: str,
) -> tuple[str, str, str]:
    uid = applicant["user"]["uid"]
    thread = await client.post(
        "/api/chat/thread",
        json={
            "agent_id": agent_slug,
            "title": make_test_conversation_title(label),
            "metadata": make_test_conversation_metadata(label, e2e=True),
        },
        headers=applicant["headers"],
    )
    assert thread.status_code == 200, thread.text
    thread_id = str(thread.json().get("thread_id") or thread.json()["id"])
    created = await client.post(
        "/api/agent/runs",
        json={
            "query": (
                "申请 VPN 标准权限；"
                f"target_user_uid={uid}；有效期 2030-12-31；业务理由为远程客户支持；"
                "设备 ASSET-E2E-001；经理确认 MGR-E2E-001。"
            ),
            "agent_slug": agent_slug,
            "thread_id": thread_id,
            "meta": {"request_id": f"p3-{label}-{uuid.uuid4()}"},
        },
        headers=applicant["headers"],
    )
    assert created.status_code == 200, created.text
    run_id = str(created.json()["run_id"])
    run = await wait_for_run(client, applicant["headers"], run_id)
    assert run["status"] == "interrupted", run
    conn = await asyncpg.connect(postgres_dsn())
    try:
        row = await conn.fetchrow(
            "SELECT id, parameter_digest FROM asterdesk_action_requests WHERE run_id=$1",
            run_id,
        )
    finally:
        await conn.close()
    assert row is not None
    return run_id, str(row["id"]), str(row["parameter_digest"])


async def _wait_action(client: httpx.AsyncClient, headers: dict[str, str], action_id: str) -> dict:
    for _ in range(120):
        response = await client.get(f"/api/asterdesk/actions/{action_id}", headers=headers)
        assert response.status_code == 200, response.text
        action = response.json()
        if action.get("resume_run_id"):
            resume = await wait_for_run(client, headers, action["resume_run_id"])
            if resume["status"] in {"completed", "failed"}:
                action["resume_run"] = resume
                return action
        await asyncio.sleep(0.5)
    pytest.fail(f"Action did not resume: {action_id}")


async def _decide(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    action_id: str,
    digest: str,
    decision: str,
    *,
    inject_crash: bool = False,
) -> httpx.Response:
    extra = {"X-AsterDesk-Failure-Injection": "after-external-success"} if inject_crash else {}
    return await client.post(
        f"/api/asterdesk/actions/{action_id}/decision",
        json={"decision": decision, "reason": f"e2e-{decision}", "parameter_digest": digest},
        headers={**headers, **extra},
    )


async def _grant_count() -> int:
    async with httpx.AsyncClient() as client:
        response = await client.get("http://asterdesk-vpn-simulator:8091/v1/stats")
        response.raise_for_status()
        return int(response.json()["grant_count"])


async def test_vpn_approval_execution_and_recovery(
    e2e_client: httpx.AsyncClient,
    e2e_headers: dict[str, str],
) -> None:
    me = await e2e_client.get("/api/auth/me", headers=e2e_headers)
    assert me.status_code == 200, me.text
    admin = me.json()
    department_id = int(admin["department_id"])
    applicant = await _create_user(e2e_client, e2e_headers, department_id)
    unauthorized = await _create_user(e2e_client, e2e_headers, department_id)
    await _seed_kb(str(admin["uid"]), department_id)

    policy = Path("/workspace-examples/remote-access-policy-v1.docx").read_bytes()
    upload = await e2e_client.post(
        "/api/asterdesk/documents",
        data={
            "knowledge_base_id": KB_ID,
            "document_id": DOCUMENT_ID,
            "version": "3.0",
            "access_level": "user",
            "user_uids": json.dumps([applicant["user"]["uid"]]),
            "title": "VPN 远程访问政策",
        },
        files={
            "file": (
                "vpn-policy.docx",
                policy,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
        headers=e2e_headers,
    )
    assert upload.status_code == 200 and upload.json()["status"] == "active", upload.text
    agent_slug = await _configure_agent(
        e2e_client,
        e2e_headers,
        [applicant["user"]["uid"], unauthorized["user"]["uid"]],
    )

    # 1. 正常批准：一项外部授权，恢复 Run 完成且有来源。
    before = await _grant_count()
    _, action_id, digest = await _start_application(e2e_client, applicant, agent_slug, "approved")
    approved = await _decide(e2e_client, e2e_headers, action_id, digest, "approved")
    assert approved.status_code == 200, approved.text
    action = await _wait_action(e2e_client, applicant["headers"], action_id)
    assert action["execution_status"] == "succeeded"
    assert action["resume_run"]["status"] == "completed"
    assert await _grant_count() == before + 1
    result = await e2e_client.get(f"/api/agent/runs/{action['resume_run_id']}/result", headers=applicant["headers"])
    assert result.status_code == 200
    assert action["external_reference_id"] in result.json()["output"]
    assert f"{DOCUMENT_ID} v3.0" in result.json()["output"]

    # 2. 拒绝：外部次数不变，恢复结果说明拒绝。
    before_reject = await _grant_count()
    _, rejected_id, rejected_digest = await _start_application(e2e_client, applicant, agent_slug, "rejected")
    rejected = await _decide(e2e_client, e2e_headers, rejected_id, rejected_digest, "rejected")
    assert rejected.status_code == 200
    rejected_action = await _wait_action(e2e_client, applicant["headers"], rejected_id)
    assert rejected_action["status"] == "rejected"
    assert await _grant_count() == before_reject
    rejected_result = await e2e_client.get(
        f"/api/agent/runs/{rejected_action['resume_run_id']}/result", headers=applicant["headers"]
    )
    assert "已拒绝" in rejected_result.json()["output"]

    # 3/4. 自批和普通用户审批均被拒绝且保持 pending。
    _, protected_id, protected_digest = await _start_application(e2e_client, applicant, agent_slug, "protected")
    self_decision = await _decide(e2e_client, applicant["headers"], protected_id, protected_digest, "approved")
    assert self_decision.status_code == 403
    unprivileged = await _decide(e2e_client, unauthorized["headers"], protected_id, protected_digest, "approved")
    assert unprivileged.status_code == 403
    protected = await e2e_client.get(f"/api/asterdesk/actions/{protected_id}", headers=applicant["headers"])
    assert protected.json()["status"] == "pending"

    # 5/6. 并发重复批准只有一个决定；额外重复投递也只产生一个授权。
    protected_before = await _grant_count()
    decisions = await asyncio.gather(
        _decide(e2e_client, e2e_headers, protected_id, protected_digest, "approved"),
        _decide(e2e_client, e2e_headers, protected_id, protected_digest, "approved"),
    )
    assert sorted(item.status_code for item in decisions) == [200, 200]
    await asyncio.gather(
        enqueue_asterdesk_action(protected_id, dispatch_id=f"duplicate-a-{uuid.uuid4().hex}"),
        enqueue_asterdesk_action(protected_id, dispatch_id=f"duplicate-b-{uuid.uuid4().hex}"),
    )
    protected_done = await _wait_action(e2e_client, applicant["headers"], protected_id)
    assert protected_done["execution_status"] == "succeeded"
    assert await _grant_count() == protected_before + 1
    assert len([event for event in protected_done["audit"] if event["event_type"] == "approval.approved"]) == 1

    # 7. 外部成功后注入 worker 崩溃点；重试查询到同一结果且没有重复授权。
    crash_before = await _grant_count()
    _, crash_id, crash_digest = await _start_application(e2e_client, applicant, agent_slug, "crash-recovery")
    crash_approval = await _decide(
        e2e_client,
        e2e_headers,
        crash_id,
        crash_digest,
        "approved",
        inject_crash=True,
    )
    assert crash_approval.status_code == 200, crash_approval.text
    crash_done = await _wait_action(e2e_client, applicant["headers"], crash_id)
    assert crash_done["execution_status"] == "succeeded"
    assert await _grant_count() == crash_before + 1
    assert len(crash_done["execution_attempts"]) >= 2
    recovered_external_ids = {
        item["external_reference_id"]
        for item in crash_done["execution_attempts"]
        if item["external_reference_id"]
    }
    assert len(recovered_external_ids) == 1

    # 9. 无权用户得到零 Evidence，Agent 完成但不能创建 ActionRequest。
    thread = await e2e_client.post(
        "/api/chat/thread",
        json={
            "agent_id": agent_slug,
            "title": make_test_conversation_title("unauthorized-policy"),
            "metadata": make_test_conversation_metadata("unauthorized-policy", e2e=True),
        },
        headers=unauthorized["headers"],
    )
    thread_id = str(thread.json().get("thread_id") or thread.json()["id"])
    run = await e2e_client.post(
        "/api/agent/runs",
        json={
            "query": f"申请 VPN，target_user_uid={unauthorized['user']['uid']}",
            "agent_slug": agent_slug,
            "thread_id": thread_id,
            "meta": {"request_id": f"p3-unauthorized-{uuid.uuid4()}"},
        },
        headers=unauthorized["headers"],
    )
    unauthorized_run_id = str(run.json()["run_id"])
    unauthorized_run = await wait_for_run(e2e_client, unauthorized["headers"], unauthorized_run_id)
    assert unauthorized_run["status"] == "completed"
    unauthorized_result = await e2e_client.get(
        f"/api/agent/runs/{unauthorized_run_id}/result", headers=unauthorized["headers"]
    )
    assert "NO_POLICY_ACCESS" in unauthorized_result.json()["output"]
    conn = await asyncpg.connect(postgres_dsn())
    try:
        unauthorized_actions = await conn.fetchval(
            "SELECT COUNT(*) FROM asterdesk_action_requests WHERE run_id=$1",
            unauthorized_run_id,
        )
        decision_count = await conn.fetchval(
            "SELECT COUNT(*) FROM asterdesk_approval_decisions WHERE action_request_id=$1", protected_id
        )
        grant_business_ids = await conn.fetchval(
            "SELECT COUNT(DISTINCT external_reference_id) FROM asterdesk_action_requests WHERE id=$1", protected_id
        )
    finally:
        await conn.close()
    assert decision_count == 1
    assert grant_business_ids == 1
    assert unauthorized_actions == 0

    result_path = __import__("os").getenv("ASTERDESK_E2E_RESULT_PATH")
    if result_path:
        Path(result_path).write_text(
            json.dumps(
                {
                    "run_id": action["resume_run_id"],
                    "action_request_id": action_id,
                    "access_token": applicant["headers"]["Authorization"].removeprefix("Bearer "),
                    "external_reference_id": action["external_reference_id"],
                    "citation": f"{DOCUMENT_ID} v3.0",
                }
            ),
            encoding="utf-8",
        )
