import importlib.util
import json
from pathlib import Path

_REPLAY_PATH = Path(__file__).parents[2] / "support" / "binizox_evidence_replay_server.py"
_REPLAY_SPEC = importlib.util.spec_from_file_location("binizox_evidence_replay_server", _REPLAY_PATH)
assert _REPLAY_SPEC is not None and _REPLAY_SPEC.loader is not None
_REPLAY = importlib.util.module_from_spec(_REPLAY_SPEC)
_REPLAY_SPEC.loader.exec_module(_REPLAY)

EXPECTED_AUTHORIZATION = _REPLAY.EXPECTED_AUTHORIZATION
EXPECTED_KB_ID = _REPLAY.EXPECTED_KB_ID
EXPECTED_MODEL = _REPLAY.EXPECTED_MODEL
EXPECTED_SKILL_MARKER = _REPLAY.EXPECTED_SKILL_MARKER
EXPECTED_TOOL = _REPLAY.EXPECTED_TOOL
SAVE_FINISHED_MARKER = _REPLAY.SAVE_FINISHED_MARKER
SAVE_NOTE_CONTENT = _REPLAY.SAVE_NOTE_CONTENT
SAVE_REQUEST_MARKER = _REPLAY.SAVE_REQUEST_MARKER
SAVE_TOOL = _REPLAY.SAVE_TOOL
SAVE_TOOL_CALL_ID = _REPLAY.SAVE_TOOL_CALL_ID
TOOL_CALL_ID = _REPLAY.TOOL_CALL_ID
_payloads = _REPLAY._payloads
_validate = _REPLAY._validate


def _request() -> dict:
    skill_path = (
        Path(__file__).parents[3]
        / "package"
        / "binizox"
        / "agents"
        / "skills"
        / "buildin"
        / "binizox-personal-agent"
        / "SKILL.md"
    )
    skill_content = skill_path.read_text(encoding="utf-8")
    assert EXPECTED_SKILL_MARKER in skill_content
    return {
        "model": EXPECTED_MODEL,
        "stream": True,
        "messages": [{"role": "system", "content": skill_content}],
        "tools": [
            {"type": "function", "function": {"name": EXPECTED_TOOL, "parameters": {}}},
            {"type": "function", "function": {"name": SAVE_TOOL, "parameters": {}}},
        ],
    }


def test_replay_requires_binizox_evidence_tool_contract() -> None:
    request = _request()
    assert _validate(EXPECTED_AUTHORIZATION, request) is None
    assert _validate("Bearer wrong", request) == "invalid_authorization"

    request["tools"] = []
    assert _validate(EXPECTED_AUTHORIZATION, request) == "evidence_tool_missing"


def test_replay_calls_binizox_tool_then_quotes_returned_evidence() -> None:
    request = _request()
    first = _payloads(EXPECTED_MODEL, request["messages"])
    tool_call = first[0]["choices"][0]["delta"]["tool_calls"][0]
    arguments = json.loads(tool_call["function"]["arguments"])
    assert tool_call["function"]["name"] == EXPECTED_TOOL
    assert arguments["knowledge_base_ids"] == [EXPECTED_KB_ID]

    request["messages"].append(
        {
            "role": "tool",
            "tool_call_id": TOOL_CALL_ID,
            "content": json.dumps(
                {
                    "evidence": [
                        {
                            "text": "个人资料中的可核对内容",
                            "citation": "[Binizox BZ-PERSONAL-001 v1.0, p.1, chunk c1]",
                        }
                    ]
                },
                ensure_ascii=False,
            ),
        }
    )
    answer = _payloads(EXPECTED_MODEL, request["messages"])[0]["choices"][0]["delta"]["content"]
    assert "个人资料中的可核对内容" in answer
    assert "BZ-PERSONAL-001" in answer


def test_replay_uses_real_skill_and_drives_note_tool_then_final_answer() -> None:
    request = _request()
    token = "a" * 32
    request["messages"].append(
        {"role": "user", "content": f"请保存笔记 {SAVE_REQUEST_MARKER}:{token}:approve"}
    )

    assert _validate(EXPECTED_AUTHORIZATION, request) is None
    first = _payloads(EXPECTED_MODEL, request["messages"])
    tool_call = first[0]["choices"][0]["delta"]["tool_calls"][0]
    arguments = json.loads(tool_call["function"]["arguments"])
    assert tool_call["function"]["name"] == SAVE_TOOL
    assert arguments == {
        "relative_path": f"notes/{token}.md",
        "content": SAVE_NOTE_CONTENT,
        "source_citations": ["Binizox E2E · 用户确认"],
    }

    request["messages"].append(
        {
            "role": "tool",
            "tool_call_id": SAVE_TOOL_CALL_ID,
            "content": json.dumps({"status": "succeeded"}),
        }
    )
    final = _payloads(EXPECTED_MODEL, request["messages"])
    assert final[0]["choices"][0]["delta"]["content"] == SAVE_FINISHED_MARKER
