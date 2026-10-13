"""Binizox parser sidecar HTTP 边界。"""

from __future__ import annotations

import json
import os

from fastapi import FastAPI, File, Form, HTTPException, UploadFile

from app.parser import parse_document

MAX_DOCUMENT_BYTES = int(os.getenv("BINIZOX_MAX_DOCUMENT_BYTES", str(25 * 1024 * 1024)))

app = FastAPI(title="Binizox Parser Sidecar", version="0.1.0")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/parse")
async def parse(
    document: str = Form(...),
    file: UploadFile = File(...),  # noqa: B008 - FastAPI uses the default as dependency metadata.
) -> dict:
    try:
        document_ref = json.loads(document)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=422, detail="document must be valid JSON"
        ) from exc

    required = {
        "document_id",
        "tenant_id",
        "storage_uri",
        "format",
        "version",
        "knowledge_base_id",
        "filename",
    }
    missing = sorted(required - set(document_ref))
    if missing:
        raise HTTPException(
            status_code=422, detail=f"missing document fields: {', '.join(missing)}"
        )
    if document_ref["format"] not in {"pdf", "docx"}:
        raise HTTPException(status_code=415, detail="only PDF and DOCX are supported")

    data = await file.read(MAX_DOCUMENT_BYTES + 1)
    if len(data) > MAX_DOCUMENT_BYTES:
        raise HTTPException(status_code=413, detail="document exceeds size limit")
    if not data:
        raise HTTPException(status_code=422, detail="document is empty")
    return parse_document(document_ref, data)
