"""为 AsterDesk 政策问答 E2E 提供最小 OpenAI 兼容确定性响应。"""

from __future__ import annotations

import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

EXPECTED_AUTHORIZATION = "Bearer asterdesk-replay-key"
EXPECTED_MODEL = "policy-chat"
EXPECTED_QUESTION = "申请某软件权限需要提供什么材料？"
EXPECTED_POLICY_MARKER = "AsterDesk-IT-POL-001"
EXPECTED_SECTION_MARKER = "第 3 节：申请材料"
EXPECTED_OUTPUT = (
    "需要提供：申请人姓名和所属部门；软件名称、版本及权限范围；设备资产编号和操作系统；"
    "业务用途与预计使用期限；直属主管确认；数据分类及是否导出或对外共享的说明。"
    "管理员权限、敏感数据或对外共享场景还需信息安全复核。"
    "来源：[AsterDesk-IT-POL-001 v1.0, §3 申请材料]"
)


def _validate_request(authorization: str | None, request: dict) -> str | None:
    """仅接受携带指定政策上下文的确定性请求。"""
    if authorization != EXPECTED_AUTHORIZATION:
        return "invalid_authorization"
    if request.get("model") != EXPECTED_MODEL:
        return "invalid_model"
    if request.get("stream") is not True:
        return "stream_required"

    messages = request.get("messages")
    if not isinstance(messages, list) or not messages:
        return "messages_required"
    serialized = json.dumps(messages, ensure_ascii=False)
    if EXPECTED_QUESTION not in serialized:
        return "question_missing"
    if EXPECTED_POLICY_MARKER not in serialized or EXPECTED_SECTION_MARKER not in serialized:
        return "policy_context_missing"
    return None


def _stream_payloads(model: str) -> list[dict]:
    """产生两段 OpenAI SSE 响应。"""
    common = {
        "id": "chatcmpl-asterdesk-policy",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
    }
    return [
        {
            **common,
            "choices": [
                {
                    "index": 0,
                    "delta": {"role": "assistant", "content": EXPECTED_OUTPUT},
                    "finish_reason": None,
                }
            ],
        },
        {
            **common,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 120, "completion_tokens": 80, "total_tokens": 200},
        },
    ]


class ReplayHandler(BaseHTTPRequestHandler):
    """只实现健康检查和 chat completions。"""

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

        error = _validate_request(self.headers.get("authorization"), request)
        if error:
            self._write_json(422, {"error": error})
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        for payload in _stream_payloads(str(request["model"])):
            self.wfile.write(f"data: {json.dumps(payload)}\n\n".encode())
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
    parser.add_argument("--port", default=8766, type=int)
    args = parser.parse_args()
    ThreadingHTTPServer((args.host, args.port), ReplayHandler).serve_forever()


if __name__ == "__main__":
    main()
