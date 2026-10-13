"""个人工具服务的安全、幂等和持久化测试。"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
import importlib
import os
import sqlite3
import threading

from fastapi.testclient import TestClient
import pytest

from app.contracts import ToolInvocation
from app.executor import canonical_digest
from app.repository import ExecutionClaimLostError

TEST_SERVICE_TOKEN = "test-tool-runner-token-at-least-thirty-two-characters"


def _create_client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("BINIZOX_WORKSPACE_ROOT", str(tmp_path / "workspace"))
    monkeypatch.setenv("BINIZOX_TOOL_STATE_PATH", str(tmp_path / "state" / "executions.sqlite3"))
    monkeypatch.setenv("BINIZOX_TOOL_RUNNER_TOKEN", TEST_SERVICE_TOKEN)
    module = importlib.import_module("app.main")
    return TestClient(module.create_app())


def _payload(*, content: str = "# Binizox\n", key: str = "run-1:tool-1") -> dict:
    return {
        "uid": "user-1",
        "run_id": "run-1",
        "tool_call_id": "tool-1",
        "tool_name": "workspace.write_note",
        "parameters": {
            "relative_path": "notes/summary.md",
            "content": content,
            "source_citations": ["个人资料.pdf · 第 2 页"],
        },
        "idempotency_key": key,
    }


@pytest.mark.parametrize("token", ["short", f" {TEST_SERVICE_TOKEN} "])
def test_runner_rejects_weak_or_padded_service_token(tmp_path, monkeypatch, token: str) -> None:
    monkeypatch.setenv("BINIZOX_WORKSPACE_ROOT", str(tmp_path / "workspace"))
    monkeypatch.setenv("BINIZOX_TOOL_STATE_PATH", str(tmp_path / "state" / "executions.sqlite3"))
    monkeypatch.setenv("BINIZOX_TOOL_RUNNER_TOKEN", TEST_SERVICE_TOKEN)
    module = importlib.import_module("app.main")
    monkeypatch.setenv("BINIZOX_TOOL_RUNNER_TOKEN", token)

    with pytest.raises(RuntimeError, match="BINIZOX_TOOL_RUNNER_TOKEN"):
        module.create_app()


@pytest.mark.parametrize(
    "other_name",
    ["JWT_SECRET_KEY", "API_KEY_DERIVATION_SECRET", "SANDBOX_PROVISIONER_TOKEN"],
)
def test_runner_rejects_reused_service_token(tmp_path, monkeypatch, other_name: str) -> None:
    monkeypatch.setenv("BINIZOX_WORKSPACE_ROOT", str(tmp_path / "workspace"))
    monkeypatch.setenv("BINIZOX_TOOL_STATE_PATH", str(tmp_path / "state" / "executions.sqlite3"))
    monkeypatch.setenv("BINIZOX_TOOL_RUNNER_TOKEN", TEST_SERVICE_TOKEN)
    monkeypatch.setenv(other_name, TEST_SERVICE_TOKEN)
    module = importlib.import_module("app.main")

    with pytest.raises(RuntimeError, match=f"independent from {other_name}"):
        module.create_app()


def test_write_note_and_replay_are_idempotent(tmp_path, monkeypatch) -> None:
    client = _create_client(tmp_path, monkeypatch)

    headers = {"Authorization": f"Bearer {TEST_SERVICE_TOKEN}"}
    first = client.post("/v1/invocations", json=_payload(), headers=headers)
    replay = client.post("/v1/invocations", json=_payload(), headers=headers)

    assert first.status_code == 200
    assert first.json()["status"] == "succeeded"
    assert first.json()["idempotent_replay"] is False
    assert replay.status_code == 200
    assert replay.json()["idempotent_replay"] is True
    assert (tmp_path / "workspace" / "shared" / "user-1" / "workspace" / "notes" / "summary.md").read_text(
        encoding="utf-8"
    ) == "# Binizox\n"


def test_same_key_with_different_parameters_is_rejected(tmp_path, monkeypatch) -> None:
    client = _create_client(tmp_path, monkeypatch)
    headers = {"Authorization": f"Bearer {TEST_SERVICE_TOKEN}"}
    assert client.post("/v1/invocations", json=_payload(), headers=headers).status_code == 200

    conflict = client.post("/v1/invocations", json=_payload(content="不同内容"), headers=headers)

    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "idempotency_conflict"


def test_path_escape_is_rejected(tmp_path, monkeypatch) -> None:
    client = _create_client(tmp_path, monkeypatch)
    payload = _payload(key="run-1:unsafe")
    payload["parameters"]["relative_path"] = "../outside.md"

    response = client.post(
        "/v1/invocations", json=payload, headers={"Authorization": f"Bearer {TEST_SERVICE_TOKEN}"}
    )

    assert response.status_code == 422
    assert not (tmp_path / "outside.md").exists()


def test_existing_equal_file_recovers_without_overwrite(tmp_path, monkeypatch) -> None:
    """模拟文件已落盘、执行记录尚未完成时的 worker 崩溃窗口。"""

    client = _create_client(tmp_path, monkeypatch)
    invocation = ToolInvocation.model_validate(_payload(key="run-1:recovery"))
    reservation = client.app.state.repository.reserve(
        idempotency_key=invocation.idempotency_key,
        parameter_digest=canonical_digest(invocation),
        lease_seconds=60,
    )
    expired_at = (datetime.now(UTC) - timedelta(minutes=2)).isoformat()
    with sqlite3.connect(tmp_path / "state" / "executions.sqlite3") as connection:
        connection.execute(
            "UPDATE tool_executions SET updated_at = ? WHERE idempotency_key = ?",
            (expired_at, invocation.idempotency_key),
        )
    target = tmp_path / "workspace" / "shared" / "user-1" / "workspace" / "notes" / "summary.md"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"# Binizox\n")

    response = client.post(
        "/v1/invocations",
        json=_payload(key="run-1:recovery"),
        headers={"Authorization": f"Bearer {TEST_SERVICE_TOKEN}"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "succeeded"
    assert response.json()["idempotent_replay"] is True
    assert target.read_text(encoding="utf-8") == "# Binizox\n"
    with pytest.raises(ExecutionClaimLostError):
        client.app.state.repository.complete(
            idempotency_key=invocation.idempotency_key,
            claim_token=reservation.claim_token,
            result={"unsafe": "stale owner"},
        )


def test_concurrent_same_key_reports_in_progress_without_double_execution(tmp_path, monkeypatch) -> None:
    client = _create_client(tmp_path, monkeypatch)
    entered = threading.Event()
    release = threading.Event()
    original = client.app.state.executor._write_note
    call_count = 0
    call_count_lock = threading.Lock()

    def blocking_write(invocation):
        nonlocal call_count
        with call_count_lock:
            call_count += 1
        entered.set()
        assert release.wait(timeout=5)
        return original(invocation)

    monkeypatch.setattr(client.app.state.executor, "_write_note", blocking_write)
    headers = {"Authorization": f"Bearer {TEST_SERVICE_TOKEN}"}
    with ThreadPoolExecutor(max_workers=2) as pool:
        first_future = pool.submit(client.post, "/v1/invocations", json=_payload(), headers=headers)
        assert entered.wait(timeout=5)
        duplicate = client.post("/v1/invocations", json=_payload(), headers=headers)
        release.set()
        first = first_future.result(timeout=5)

    assert first.status_code == 200
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["code"] == "execution_in_progress"
    assert call_count == 1


def test_invocation_requires_internal_service_token(tmp_path, monkeypatch) -> None:
    client = _create_client(tmp_path, monkeypatch)

    response = client.post("/v1/invocations", json=_payload())

    assert response.status_code == 401
    assert not (tmp_path / "workspace" / "shared" / "user-1" / "workspace").exists()


def test_user_workspaces_are_isolated(tmp_path, monkeypatch) -> None:
    client = _create_client(tmp_path, monkeypatch)
    headers = {"Authorization": f"Bearer {TEST_SERVICE_TOKEN}"}
    first = _payload(content="first", key="user-1:key")
    second = _payload(content="second", key="user-2:key")
    second["uid"] = "user-2"

    assert client.post("/v1/invocations", json=first, headers=headers).status_code == 200
    assert client.post("/v1/invocations", json=second, headers=headers).status_code == 200
    assert (tmp_path / "workspace" / "shared" / "user-1" / "workspace" / "notes" / "summary.md").read_text() == "first"
    assert (tmp_path / "workspace" / "shared" / "user-2" / "workspace" / "notes" / "summary.md").read_text() == "second"


def test_symlinked_user_workspace_is_rejected(tmp_path, monkeypatch) -> None:
    client = _create_client(tmp_path, monkeypatch)
    shared = tmp_path / "workspace" / "shared"
    victim = shared / "user-2"
    victim.mkdir(parents=True)
    try:
        (shared / "user-1").symlink_to(victim, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"当前平台不允许创建测试 symlink: {exc}")

    response = client.post(
        "/v1/invocations",
        json=_payload(key="user-1:symlink"),
        headers={"Authorization": f"Bearer {TEST_SERVICE_TOKEN}"},
    )

    assert response.status_code == 422
    assert not (victim / "workspace" / "notes" / "summary.md").exists()


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="当前平台不支持 FIFO")
def test_existing_fifo_is_rejected_without_blocking(tmp_path, monkeypatch) -> None:
    client = _create_client(tmp_path, monkeypatch)
    target = tmp_path / "workspace" / "shared" / "user-1" / "workspace" / "notes" / "summary.md"
    target.parent.mkdir(parents=True)
    os.mkfifo(target)

    response = client.post(
        "/v1/invocations",
        json=_payload(key="run-1:fifo"),
        headers={"Authorization": f"Bearer {TEST_SERVICE_TOKEN}"},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "unsafe_path"


def test_existing_large_file_is_rejected_without_reading_it_all(tmp_path, monkeypatch) -> None:
    client = _create_client(tmp_path, monkeypatch)
    target = tmp_path / "workspace" / "shared" / "user-1" / "workspace" / "notes" / "summary.md"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"x" * (1024 * 1024))

    response = client.post(
        "/v1/invocations",
        json=_payload(key="run-1:large"),
        headers={"Authorization": f"Bearer {TEST_SERVICE_TOKEN}"},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "target_conflict"
    assert target.stat().st_size == 1024 * 1024
