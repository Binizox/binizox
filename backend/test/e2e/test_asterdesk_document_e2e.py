"""验证第二阶段文档、权限 Evidence 与 Agent Run 的真实闭环。"""

from __future__ import annotations

import io
import json
import os
import uuid
from pathlib import Path

import asyncpg
import httpx
import pytest
from docx import Document

from e2e_helpers import consume_events, postgres_dsn, wait_for_run
from test.live_api_cleanup import make_test_conversation_metadata, make_test_conversation_title

pytestmark = [pytest.mark.asyncio, pytest.mark.e2e, pytest.mark.slow]

KB_ID = "asterdesk-phase2-e2e"
DOCUMENT_ID = "AD-REMOTE-001"
QUESTION = "管理员权限需要哪些确认和材料？"
PROVIDER_ID = "asterdesk-evidence-replay"
MODEL_SPEC = f"{PROVIDER_ID}:evidence-chat"
SENSITIVE_FACT = "工单编号"


async def _create_user(client: httpx.AsyncClient, admin_headers: dict[str, str], department_id: int) -> dict:
    suffix = uuid.uuid4().hex[:10]
    password = f"Pw!{uuid.uuid4().hex[:16]}"
    created = await client.post(
        "/api/auth/users",
        json={
            "username": f"phase2_{suffix}",
            "password": password,
            "role": "user",
            "department_id": department_id,
        },
        headers=admin_headers,
    )
    assert created.status_code == 200, created.text
    user = created.json()
    login = await client.post("/api/auth/token", data={"username": user["uid"], "password": password})
    assert login.status_code == 200, login.text
    return {
        "user": user,
        "password": password,
        "headers": {"Authorization": f"Bearer {login.json()['access_token']}"},
    }


async def _seed_knowledge_base(admin_uid: str, department_id: int) -> None:
    share_config = {
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
                    (
                        kb_id, name, description, kb_type, additional_params,
                        share_config, created_by, created_at, updated_at
                    )
                VALUES ($1, $2, $3, 'dify', '{}'::jsonb, $4::jsonb, $5, NOW(), NOW())
                """,
                KB_ID,
                "AsterDesk Phase 2 E2E",
                "Server-side document ACL evidence test",
                json.dumps(share_config),
                admin_uid,
            )
    finally:
        await conn.close()


def _version_two_bytes(source: bytes) -> bytes:
    document = Document(io.BytesIO(source))
    for paragraph in document.paragraphs:
        if "直属主管确认" in paragraph.text:
            for run in paragraph.runs:
                run.text = run.text.replace("直属主管确认", "直属主管确认和工单编号")
    output = io.BytesIO()
    document.save(output)
    return output.getvalue()


async def _upload(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    *,
    data: bytes,
    version: str,
    allowed_uid: str,
    document_id: str = DOCUMENT_ID,
    filename: str = "remote-access-policy.docx",
) -> httpx.Response:
    return await client.post(
        "/api/asterdesk/documents",
        data={
            "knowledge_base_id": KB_ID,
            "document_id": document_id,
            "version": version,
            "access_level": "user",
            "user_uids": json.dumps([allowed_uid]),
            "title": "AsterDesk 远程访问权限测试政策",
        },
        files={"file": (filename, data, "application/octet-stream")},
        headers=headers,
    )


async def _search(client: httpx.AsyncClient, headers: dict[str, str]) -> list[dict]:
    response = await client.post(
        "/api/asterdesk/search",
        json={"knowledge_base_ids": [KB_ID], "query": QUESTION, "top_k": 8},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()["evidence"]


async def _create_provider(client: httpx.AsyncClient, headers: dict[str, str]) -> None:
    deleted = await client.delete(f"/api/system/model-providers/{PROVIDER_ID}", headers=headers)
    assert deleted.status_code in {200, 404}, deleted.text
    response = await client.post(
        "/api/system/model-providers",
        json={
            "provider_id": PROVIDER_ID,
            "display_name": "AsterDesk evidence replay",
            "provider_type": "openai",
            "base_url": "http://asterdesk-replay:8767/v1",
            "api_key": "asterdesk-evidence-replay-key",
            "capabilities": ["chat"],
            "enabled_models": [
                {"id": "evidence-chat", "display_name": "Evidence replay", "type": "chat", "source": "manual"}
            ],
            "is_enabled": True,
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text


async def _create_agent(client: httpx.AsyncClient, headers: dict[str, str], user_uids: list[str]) -> str:
    slug = f"asterdesk-evidence-{uuid.uuid4().hex[:8]}"
    response = await client.post(
        "/api/agent",
        json={
            "name": f"AsterDesk Evidence {slug[-8:]}",
            "slug": slug,
            "backend_id": "ChatbotAgent",
            "description": "第二阶段权限过滤 Evidence 问答",
            "config_json": {
                "context": {
                    "model": MODEL_SPEC,
                    "system_prompt": "必须先检索 AsterDesk Evidence，只能引用本次工具返回的来源。",
                    "tools": [],
                    "knowledges": [],
                    "mcps": [],
                    "skills": ["asterdesk-evidence"],
                    "preload_skills": ["asterdesk-evidence"],
                    "subagents": [],
                }
            },
            "share_config": {
                "version": 2,
                "read_scope": {"access_level": "user", "department_ids": [], "user_uids": user_uids},
                "manage_scope": None,
            },
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return slug


async def _run_agent(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    agent_slug: str,
    label: str,
) -> tuple[str, str, dict[str, int]]:
    thread = await client.post(
        "/api/chat/thread",
        json={
            "agent_id": agent_slug,
            "title": make_test_conversation_title(label),
            "metadata": make_test_conversation_metadata(label, e2e=True),
        },
        headers=headers,
    )
    assert thread.status_code == 200, thread.text
    thread_id = str(thread.json().get("thread_id") or thread.json()["id"])
    created = await client.post(
        "/api/agent/runs",
        json={
            "query": QUESTION,
            "agent_slug": agent_slug,
            "thread_id": thread_id,
            "meta": {"request_id": f"p2-{label[-12:]}-{uuid.uuid4()}"},
        },
        headers=headers,
    )
    assert created.status_code == 200, created.text
    run_id = str(created.json()["run_id"])
    events = await consume_events(client, headers, run_id)
    run = await wait_for_run(client, headers, run_id)
    assert run["status"] == "completed", run
    result = await client.get(f"/api/agent/runs/{run_id}/result", headers=headers)
    assert result.status_code == 200, result.text
    return run_id, result.json()["output"], events


async def test_document_acl_versioning_and_agent_evidence(
    e2e_client: httpx.AsyncClient,
    e2e_headers: dict[str, str],
) -> None:
    me = await e2e_client.get("/api/auth/me", headers=e2e_headers)
    assert me.status_code == 200, me.text
    admin = me.json()
    department_id = int(admin["department_id"])
    authorized = await _create_user(e2e_client, e2e_headers, department_id)
    unauthorized = await _create_user(e2e_client, e2e_headers, department_id)
    await _seed_knowledge_base(str(admin["uid"]), department_id)

    sample_path = Path("/workspace-examples/remote-access-policy-v1.docx")
    source = sample_path.read_bytes()
    uploaded = await _upload(
        e2e_client,
        e2e_headers,
        data=source,
        version="1.0",
        allowed_uid=authorized["user"]["uid"],
    )
    assert uploaded.status_code == 200, uploaded.text
    assert uploaded.json()["status"] == "active"
    assert uploaded.json()["chunk_count"] > 0

    authorized_evidence = await _search(e2e_client, authorized["headers"])
    assert authorized_evidence
    assert all(item["document_version"] == "1.0" for item in authorized_evidence)
    assert any(item["location"]["page"] in {1, 2} for item in authorized_evidence)
    assert all(item["citation"] for item in authorized_evidence)
    assert await _search(e2e_client, unauthorized["headers"]) == []

    duplicate = await _upload(
        e2e_client,
        e2e_headers,
        data=source,
        version="1.0",
        allowed_uid=authorized["user"]["uid"],
    )
    assert duplicate.status_code == 200, duplicate.text
    assert duplicate.json()["idempotent_replay"] is True
    assert duplicate.json()["chunk_count"] == uploaded.json()["chunk_count"]

    broken = await _upload(
        e2e_client,
        e2e_headers,
        data=b"not-a-docx",
        version="1.0",
        allowed_uid=authorized["user"]["uid"],
        document_id="AD-BROKEN-001",
        filename="broken.docx",
    )
    assert broken.status_code == 200, broken.text
    assert broken.json()["status"] == "parse_failed"
    assert broken.json()["chunk_count"] == 0
    status = await e2e_client.get(
        f"/api/asterdesk/documents/{KB_ID}/AD-BROKEN-001/versions/1.0",
        headers=authorized["headers"],
    )
    assert status.status_code == 200, status.text
    assert status.json()["status"] == "parse_failed"

    version_two = await _upload(
        e2e_client,
        e2e_headers,
        data=_version_two_bytes(source),
        version="2.0",
        allowed_uid=authorized["user"]["uid"],
    )
    assert version_two.status_code == 200, version_two.text
    assert version_two.json()["status"] == "active"
    current_evidence = await _search(e2e_client, authorized["headers"])
    assert current_evidence
    assert all(item["document_version"] == "2.0" for item in current_evidence)
    assert all(" v2.0," in item["citation"] for item in current_evidence)

    conn = await asyncpg.connect(postgres_dsn())
    try:
        rows = await conn.fetch(
            """
            SELECT status, processing_params->'asterdesk'->>'version' AS version, chunk_count
            FROM knowledge_files
            WHERE kb_id=$1 AND processing_params->'asterdesk'->>'document_id'=$2
            ORDER BY version
            """,
            KB_ID,
            DOCUMENT_ID,
        )
        assert [(row["version"], row["status"]) for row in rows] == [
            ("1.0", "superseded"),
            ("2.0", "active"),
        ]
        chunk_versions = await conn.fetch(
            """
            SELECT DISTINCT extraction_result->'asterdesk'->>'version' AS version
            FROM knowledge_chunks WHERE kb_id=$1
            """,
            KB_ID,
        )
        assert {row["version"] for row in chunk_versions} >= {"1.0", "2.0"}
    finally:
        await conn.close()

    await _create_provider(e2e_client, e2e_headers)
    agent_slug = await _create_agent(
        e2e_client,
        e2e_headers,
        [authorized["user"]["uid"], unauthorized["user"]["uid"]],
    )
    authorized_run, authorized_answer, authorized_events = await _run_agent(
        e2e_client, authorized["headers"], agent_slug, "asterdesk-phase2-authorized"
    )
    assert SENSITIVE_FACT in authorized_answer
    assert " v2.0," in authorized_answer
    assert authorized_events.get("messages", 0) > 0
    assert authorized_events.get("end", 0) == 1

    _, unauthorized_answer, unauthorized_events = await _run_agent(
        e2e_client, unauthorized["headers"], agent_slug, "asterdesk-phase2-unauthorized"
    )
    assert "NO_AUTHORIZED_EVIDENCE" in unauthorized_answer
    assert SENSITIVE_FACT not in unauthorized_answer
    assert DOCUMENT_ID not in unauthorized_answer
    assert unauthorized_events.get("end", 0) == 1

    result_path = os.getenv("ASTERDESK_E2E_RESULT_PATH")
    if result_path:
        Path(result_path).write_text(
            json.dumps(
                {
                    "run_id": authorized_run,
                    "access_token": authorized["headers"]["Authorization"].removeprefix("Bearer "),
                    "expected": " v2.0,",
                }
            ),
            encoding="utf-8",
        )
