"""第二阶段 Evidence 工具调用的确定性 OpenAI 兼容 replay。"""

from __future__ import annotations

import argparse
import json
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

EXPECTED_AUTHORIZATION = "Bearer binizox-evidence-replay-key"
EXPECTED_MODEL = "evidence-chat"
EXPECTED_TOOL = "search_binizox_evidence"
EXPECTED_SKILL_MARKER = "# Binizox 个人知识与笔记"
EXPECTED_KB_ID = "binizox-evidence-e2e"
TOOL_CALL_ID = "call-binizox-evidence"
SAVE_TOOL = "save_binizox_note"
SAVE_TOOL_CALL_ID = "call-binizox-save-note"
SAVE_REQUEST_MARKER = "BINIZOX_SAVE_NOTE_E2E"
SAVE_NOTE_CONTENT = "# Binizox E2E 笔记\n\n这是经过用户确认后保存的测试内容。\n"
SAVE_FINISHED_MARKER = "BINIZOX_NOTE_FLOW_FINISHED"
_SAVE_REQUEST_RE = re.compile(rf"{SAVE_REQUEST_MARKER}:([a-f0-9]{{32}}):(approve|reject)")


def _tool_result(messages: list[dict]) -> dict | None:
    for message in reversed(messages):
        if message.get("role") != "tool" or message.get("tool_call_id") != TOOL_CALL_ID:
            continue
        content = message.get("content")
        try:
            return json.loads(content) if isinstance(content, str) else content
        except (TypeError, json.JSONDecodeError):
            return None
    return None


def _save_request(messages: list[dict]) -> tuple[str, str] | None:
    """从真实用户消息中读取唯一测试路径和预期审批分支。"""

    for message in messages:
        if message.get("role") != "user" or not isinstance(message.get("content"), str):
            continue
        matched = _SAVE_REQUEST_RE.search(message["content"])
        if matched:
            return matched.group(1), matched.group(2)
    return None


def _save_tool_result(messages: list[dict]) -> object | None:
    """识别审批后工具结果；拒绝结果不要求是 JSON。"""

    for message in reversed(messages):
        if message.get("role") != "tool" or message.get("tool_call_id") != SAVE_TOOL_CALL_ID:
            continue
        content = message.get("content")
        if not isinstance(content, str):
            return content
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return content
    return None


def _validate(authorization: str | None, request: dict) -> str | None:
    if authorization != EXPECTED_AUTHORIZATION:
        return "invalid_authorization"
    if request.get("model") != EXPECTED_MODEL or request.get("stream") is not True:
        return "invalid_model_contract"
    messages = request.get("messages")
    if not isinstance(messages, list) or not messages:
        return "messages_required"
    serialized = json.dumps(messages, ensure_ascii=False)
    if EXPECTED_SKILL_MARKER not in serialized:
        return "evidence_skill_missing"
    tools = request.get("tools") or []
    names = {
        item.get("function", {}).get("name")
        for item in tools
        if isinstance(item, dict) and isinstance(item.get("function"), dict)
    }
    if EXPECTED_TOOL not in names:
        return "evidence_tool_missing"
    if _save_request(messages) is not None and SAVE_TOOL not in names:
        return "note_tool_missing"
    result = _tool_result(messages)
    if result is not None and not isinstance(result.get("evidence"), list):
        return "invalid_tool_result"
    return None


def _payloads(model: str, messages: list[dict]) -> list[dict]:
    common = {
        "id": "chatcmpl-binizox-evidence",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
    }
    save_request = _save_request(messages)
    if save_request is not None:
        request_token, _ = save_request
        save_result = _save_tool_result(messages)
        if save_result is None:
            return [
                {
                    **common,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {
                                "role": "assistant",
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "id": SAVE_TOOL_CALL_ID,
                                        "type": "function",
                                        "function": {
                                            "name": SAVE_TOOL,
                                            "arguments": json.dumps(
                                                {
                                                    "relative_path": f"notes/{request_token}.md",
                                                    "content": SAVE_NOTE_CONTENT,
                                                    "source_citations": ["Binizox E2E · 用户确认"],
                                                },
                                                ensure_ascii=False,
                                            ),
                                        },
                                    }
                                ],
                            },
                            "finish_reason": None,
                        }
                    ],
                },
                {
                    **common,
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}],
                    "usage": {"prompt_tokens": 12, "completion_tokens": 5, "total_tokens": 17},
                },
            ]
        return [
            {
                **common,
                "choices": [
                    {
                        "index": 0,
                        "delta": {"role": "assistant", "content": SAVE_FINISHED_MARKER},
                        "finish_reason": None,
                    }
                ],
            },
            {
                **common,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 20, "completion_tokens": 8, "total_tokens": 28},
            },
        ]

    result = _tool_result(messages)
    if result is None:
        return [
            {
                **common,
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "role": "assistant",
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": TOOL_CALL_ID,
                                    "type": "function",
                                    "function": {
                                        "name": EXPECTED_TOOL,
                                        "arguments": json.dumps(
                                            {
                                                "query": "管理员权限需要哪些确认和材料",
                                                "knowledge_base_ids": [EXPECTED_KB_ID],
                                                "top_k": 8,
                                            },
                                            ensure_ascii=False,
                                        ),
                                    },
                                }
                            ],
                        },
                        "finish_reason": None,
                    }
                ],
            },
            {
                **common,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 5, "total_tokens": 17},
            },
        ]

    evidence = result["evidence"]
    if evidence:
        item = evidence[0]
        answer = f"根据本次检索证据：{item['text']} {item['citation']}"
    else:
        answer = "当前用户可访问的已发布文档中没有相关证据。NO_AUTHORIZED_EVIDENCE"
    return [
        {
            **common,
            "choices": [{"index": 0, "delta": {"role": "assistant", "content": answer}, "finish_reason": None}],
        },
        {
            **common,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 20, "completion_tokens": 16, "total_tokens": 36},
        },
    ]


class ReplayHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._write_json(200, {"status": "ok"})
            return
        self._write_json(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path.rstrip("/") != "/v1/chat/completions":
            self._write_json(404, {"error": "not_found"})
            return
        try:
            length = int(self.headers.get("content-length", "0"))
            request = json.loads(self.rfile.read(length) or b"{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            self._write_json(400, {"error": "invalid_json"})
            return
        error = _validate(self.headers.get("authorization"), request)
        if error:
            self._write_json(422, {"error": error})
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        for payload in _payloads(str(request["model"]), request["messages"]):
            self.wfile.write(f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode())
            self.wfile.flush()
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()
        self.close_connection = True

    def log_message(self, format: str, *args: object) -> None:
        return

    def _write_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", default=8767, type=int)
    args = parser.parse_args()
    ThreadingHTTPServer((args.host, args.port), ReplayHandler).serve_forever()


if __name__ == "__main__":
    main()
