"""AsterDesk 第三阶段独立 VPN 权限模拟系统。"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="AsterDesk VPN Simulator", version="1.0.0")
_write_lock = Lock()


class GrantRequest(BaseModel):
    business_request_id: str = Field(min_length=1, max_length=64)
    tenant_id: str = Field(min_length=1, max_length=64)
    parameter_digest: str = Field(min_length=64, max_length=64)
    parameters: dict[str, Any]


def _db_path() -> Path:
    path = Path(os.getenv("VPN_SIMULATOR_DB", "/data/vpn-simulator.sqlite3"))
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


@contextmanager
def _connection():
    conn = sqlite3.connect(_db_path(), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS vpn_grants (
                id TEXT PRIMARY KEY,
                business_request_id TEXT NOT NULL UNIQUE,
                tenant_id TEXT NOT NULL,
                idempotency_key TEXT NOT NULL UNIQUE,
                parameter_digest TEXT NOT NULL,
                parameters_json TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        yield conn
        conn.commit()
    finally:
        conn.close()


def _canonical(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "grant_id": row["id"],
        "business_request_id": row["business_request_id"],
        "tenant_id": row["tenant_id"],
        "parameter_digest": row["parameter_digest"],
        "parameters": json.loads(row["parameters_json"]),
        "status": row["status"],
        "created_at": row["created_at"],
    }


@app.on_event("startup")
def initialize() -> None:
    with _connection():
        pass


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/grants")
def create_grant(
    request: GrantRequest,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    tenant_header: str = Header(alias="X-AsterDesk-Tenant"),
) -> dict[str, Any]:
    if tenant_header != request.tenant_id:
        raise HTTPException(status_code=403, detail="tenant header mismatch")
    canonical = _canonical(request.parameters)
    computed = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    if computed != request.parameter_digest:
        raise HTTPException(status_code=422, detail="parameter digest mismatch")
    with _write_lock, _connection() as conn:
        existing = conn.execute(
            "SELECT * FROM vpn_grants WHERE idempotency_key = ? OR business_request_id = ?",
            (idempotency_key, request.business_request_id),
        ).fetchone()
        if existing:
            if (
                existing["idempotency_key"] != idempotency_key
                or existing["parameter_digest"] != request.parameter_digest
                or existing["parameters_json"] != canonical
                or existing["tenant_id"] != request.tenant_id
            ):
                raise HTTPException(status_code=409, detail="idempotency conflict")
            return _row(existing)
        grant_id = f"vpn-grant-{uuid.uuid4().hex}"
        created_at = datetime.now(tz=UTC).isoformat()
        conn.execute(
            """
            INSERT INTO vpn_grants
                (id, business_request_id, tenant_id, idempotency_key, parameter_digest,
                 parameters_json, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 'active', ?)
            """,
            (
                grant_id,
                request.business_request_id,
                request.tenant_id,
                idempotency_key,
                request.parameter_digest,
                canonical,
                created_at,
            ),
        )
        row = conn.execute("SELECT * FROM vpn_grants WHERE id = ?", (grant_id,)).fetchone()
        return _row(row)


@app.get("/v1/grants/by-request/{business_request_id}")
def get_grant(
    business_request_id: str,
    tenant_header: str = Header(alias="X-AsterDesk-Tenant"),
) -> dict[str, Any]:
    with _connection() as conn:
        row = conn.execute(
            "SELECT * FROM vpn_grants WHERE business_request_id = ? AND tenant_id = ?",
            (business_request_id, tenant_header),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="grant not found")
    return _row(row)


@app.get("/v1/stats")
def stats(tenant_header: str | None = Header(default=None, alias="X-AsterDesk-Tenant")) -> dict[str, int]:
    with _connection() as conn:
        if tenant_header:
            count = conn.execute("SELECT COUNT(*) FROM vpn_grants WHERE tenant_id = ?", (tenant_header,)).fetchone()[0]
        else:
            count = conn.execute("SELECT COUNT(*) FROM vpn_grants").fetchone()[0]
    return {"grant_count": int(count)}
