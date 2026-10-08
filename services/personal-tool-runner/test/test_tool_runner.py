"""个人工具服务的安全、幂等和持久化测试。"""

from __future__ import annotations

import importlib

from fastapi.testclient import TestClient


def _create_client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("BINIZOX_WORKSPACE_ROOT", str(tmp_path / "workspace"))
    monkeypatch.setenv("BINIZOX_TOOL_STATE_PATH", str(tmp_path / "state" / "executions.sqlite3"))
    module = importlib.import_module("app.main")
    return TestClient(module.create_app())


def _payload(*, content: str = "# Binizox\n", key: str = "run-1:tool-1") -> dict:
    return {
        "run_id": "run-1",
        "tool_name": "workspace.write_note",
        "parameters": {
            "relative_path": "notes/summary.md",
            "content": content,
            "source_citations": ["个人资料.pdf · 第 2 页"],
        },
        "idempotency_key": key,
    }


def test_write_note_and_replay_are_idempotent(tmp_path, monkeypatch) -> None:
    client = _create_client(tmp_path, monkeypatch)

    first = client.post("/v1/invocations", json=_payload())
    replay = client.post("/v1/invocations", json=_payload())

    assert first.status_code == 200
    assert first.json()["status"] == "succeeded"
    assert first.json()["idempotent_replay"] is False
    assert replay.status_code == 200
    assert replay.json()["idempotent_replay"] is True
    assert (tmp_path / "workspace" / "notes" / "summary.md").read_text(encoding="utf-8") == "# Binizox\n"


def test_same_key_with_different_parameters_is_rejected(tmp_path, monkeypatch) -> None:
    client = _create_client(tmp_path, monkeypatch)
    assert client.post("/v1/invocations", json=_payload()).status_code == 200

    conflict = client.post("/v1/invocations", json=_payload(content="不同内容"))

    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "idempotency_conflict"


def test_path_escape_is_rejected(tmp_path, monkeypatch) -> None:
    client = _create_client(tmp_path, monkeypatch)
    payload = _payload(key="run-1:unsafe")
    payload["parameters"]["relative_path"] = "../outside.md"

    response = client.post("/v1/invocations", json=payload)

    assert response.status_code == 422
    assert not (tmp_path / "outside.md").exists()


def test_existing_equal_file_recovers_without_overwrite(tmp_path, monkeypatch) -> None:
    """模拟文件已落盘、执行记录尚未完成时的 worker 崩溃窗口。"""

    client = _create_client(tmp_path, monkeypatch)
    target = tmp_path / "workspace" / "notes" / "summary.md"
    target.parent.mkdir(parents=True)
    target.write_text("# Binizox\n", encoding="utf-8")

    response = client.post("/v1/invocations", json=_payload(key="run-1:recovery"))

    assert response.status_code == 200
    assert response.json()["status"] == "succeeded"
    assert target.read_text(encoding="utf-8") == "# Binizox\n"
