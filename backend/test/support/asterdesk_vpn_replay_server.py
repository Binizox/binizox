"""第三阶段 VPN Agent 的确定性 OpenAI 兼容 replay。"""

from __future__ import annotations

import argparse
import json
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

EXPECTED_AUTHORIZATION = "Bearer asterdesk-vpn-replay-key"
EXPECTED_MODEL = "vpn-chat"
EXPECTED_KB_ID = "asterdesk-phase3-vpn"
SEARCH_CALL_ID = "call-vpn-policy-search"
ACTION_CALL_ID = "call-vpn-action"
SKILL_MARKER = "# VPN 权限申请 Agent"


def _tool_result(messages: list[dict], call_id: str) -> dict | None:
    for message in reversed(messages):
        if message.get("role") != "tool" or message.get("tool_call_id") != call_id:
            continue
        content = message.get("content")
        try:
            return json.loads(content) if isinstance(content, str) else content
        except (TypeError, json.JSONDecodeError):
            return None
    return None


def _target_uid(messages: list[dict]) -> str:
    serialized = json.dumps(messages, ensure_ascii=False)
    matched = re.search(r"target_user_uid[=:：]\s*([a-zA-Z0-9_-]+)", serialized)
    return matched.group(1) if matched else "missing-target-user"


def _chunks(model: str, *, tool_call: tuple[str, str, dict] | None = None, content: str | None = None) -> list[dict]:
    common = {
        "id": "chatcmpl-asterdesk-vpn",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
    }
    if tool_call:
        call_id, name, arguments = tool_call
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
                                    "id": call_id,
                                    "type": "function",
                                    "function": {
                                        "name": name,
                                        "arguments": json.dumps(arguments, ensure_ascii=False),
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
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            },
        ]
    return [
        {
            **common,
            "choices": [{"index": 0, "delta": {"role": "assistant", "content": content}, "finish_reason": None}],
        },
        {
            **common,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 20, "completion_tokens": 15, "total_tokens": 35},
        },
    ]


def _payloads(model: str, messages: list[dict]) -> list[dict]:
    search = _tool_result(messages, SEARCH_CALL_ID)
    action = _tool_result(messages, ACTION_CALL_ID)
    if search is None:
        return _chunks(
            model,
            tool_call=(
                SEARCH_CALL_ID,
                "search_asterdesk_evidence",
                {"query": "VPN 远程访问申请材料与审批要求", "knowledge_base_ids": [EXPECTED_KB_ID], "top_k": 8},
            ),
        )
    evidence = search.get("evidence") if isinstance(search, dict) else None
    if not evidence:
        return _chunks(model, content="当前用户无权访问可作为依据的 VPN 政策，未创建 ActionRequest。NO_POLICY_ACCESS")
    if action is None:
        return _chunks(
            model,
            tool_call=(
                ACTION_CALL_ID,
                "request_vpn_access",
                {
                    "knowledge_base_ids": [EXPECTED_KB_ID],
                    "evidence_chunk_ids": [evidence[0]["chunk_id"]],
                    "target_user_uid": _target_uid(messages),
                    "permission_scope": "vpn_standard",
                    "valid_until": "2030-12-31",
                    "business_reason": "远程处理已授权的客户支持工单",
                    "device_asset_id": "ASSET-E2E-001",
                    "manager_approval_reference": "MGR-E2E-001",
                },
            ),
        )
    citation = (action.get("policy_evidence") or [{}])[0].get("citation", "")
    if action.get("approval_status") == "rejected":
        answer = (
            "VPN 申请已拒绝，未执行外部授权。"
            f"原因：{action.get('decision_reason') or '未说明'}；"
            f"ActionRequest={action.get('action_request_id')} "
            f"{citation}"
        )
    elif action.get("execution_status") == "succeeded":
        answer = (
            f"VPN 权限已批准并完成授权。ActionRequest={action.get('action_request_id')}；"
            f"外部引用={action.get('external_reference_id')}；有效期 2030-12-31。{citation}"
        )
    else:
        answer = (
            f"VPN 申请执行结果：{action.get('execution_status')}。"
            f"ActionRequest={action.get('action_request_id')} {citation}"
        )
    return _chunks(model, content=answer)


class ReplayHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:  # noqa: N802
        self._write_json(200, {"status": "ok"}) if self.path == "/health" else self._write_json(404, {})

    def do_POST(self) -> None:  # noqa: N802
        if self.path.rstrip("/") != "/v1/chat/completions":
            self._write_json(404, {"error": "not_found"})
            return
        try:
            request = json.loads(self.rfile.read(int(self.headers.get("content-length", "0"))) or b"{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            self._write_json(400, {"error": "invalid_json"})
            return
        serialized = json.dumps(request.get("messages") or [], ensure_ascii=False)
        tool_names = {
            item.get("function", {}).get("name")
            for item in request.get("tools") or []
            if isinstance(item, dict)
        }
        if self.headers.get("authorization") != EXPECTED_AUTHORIZATION:
            self._write_json(401, {"error": "invalid_authorization"})
            return
        if request.get("model") != EXPECTED_MODEL or request.get("stream") is not True:
            self._write_json(422, {"error": "invalid_model_contract"})
            return
        if SKILL_MARKER not in serialized or not {"search_asterdesk_evidence", "request_vpn_access"} <= tool_names:
            self._write_json(422, {"error": "vpn_skill_or_tools_missing"})
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
    parser.add_argument("--port", default=8768, type=int)
    args = parser.parse_args()
    ThreadingHTTPServer((args.host, args.port), ReplayHandler).serve_forever()


if __name__ == "__main__":
    main()
