from __future__ import annotations

import re
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from app.core.config import settings
from app.schemas.ingest import DocumentIngestResponse, SupportedFormatsResponse
from app.services.ingestion import DocumentIngestionPipeline
from app.services.ingestion.storage import IngestionFanoutSink
from app.services.ingestion.models import ChunkStrategy, ChunkingConfig, DocumentScope
from app.services.ingestion.parsers import (
    ALLOWED_DOCUMENT_EXTENSIONS,
    BLOCKED_IMAGE_EXTENSIONS,
    DocumentValidationError,
    ParserUnavailableError,
    validate_document_file,
)
from app.services.vector.factory import get_vector_store

router = APIRouter(prefix="/ingest", tags=["ingest"])


@router.get("", response_model=SupportedFormatsResponse)
async def supported_formats() -> SupportedFormatsResponse:
    return SupportedFormatsResponse(
        allowed_extensions=sorted(ALLOWED_DOCUMENT_EXTENSIONS),
        blocked_image_extensions=sorted(BLOCKED_IMAGE_EXTENSIONS),
    )


@router.post("", response_model=DocumentIngestResponse, status_code=status.HTTP_201_CREATED)
async def ingest_document(
    tenant_id: str = Form(..., min_length=1),
    app_id: str = Form(..., min_length=1),
    collection_id: str | None = Form(default=None),
    chunk_strategy: ChunkStrategy = Form(default=ChunkStrategy.PARENT_CHILD),
    max_tokens: int = Form(default=700, ge=100, le=4000),
    overlap_tokens: int = Form(default=80, ge=0, le=1000),
    file: UploadFile = File(...),
) -> DocumentIngestResponse:
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing filename.")

    try:
        validate_document_file(file.filename, file.content_type)
    except DocumentValidationError as exc:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(exc)) from exc

    stored_path = await _store_upload(
        file=file,
        tenant_id=tenant_id,
        app_id=app_id,
    )

    pipeline = DocumentIngestionPipeline(
        sink=IngestionFanoutSink(vector_sink=get_vector_store()),
    )
    try:
        bundle = pipeline.ingest_file(
            path=stored_path,
            scope=DocumentScope(
                tenant_id=tenant_id,
                app_id=app_id,
                collection_id=collection_id,
            ),
            filename=file.filename,
            content_type=file.content_type,
            chunking=ChunkingConfig(
                strategy=chunk_strategy,
                max_tokens=max_tokens,
                overlap_tokens=min(overlap_tokens, max_tokens - 1),
            ),
        )
    except ParserUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except DocumentValidationError as exc:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(exc)) from exc

    source = bundle.parsed_document.source
    return DocumentIngestResponse(
        status="ready",
        tenant_id=tenant_id,
        app_id=app_id,
        collection_id=collection_id,
        document_id=source.document_id,
        filename=source.filename,
        extension=source.extension,
        sha256=source.sha256,
        chunk_strategy=chunk_strategy,
        stats=bundle.stats,
        warnings=bundle.warnings,
    )


async def _store_upload(file: UploadFile, tenant_id: str, app_id: str) -> Path:
    base_dir = settings.DOCUMENT_UPLOAD_DIR / _safe_segment(tenant_id) / _safe_segment(app_id)
    base_dir.mkdir(parents=True, exist_ok=True)

    original_name = Path(file.filename or "document").name
    safe_name = _safe_filename(original_name)
    stored_path = base_dir / f"{uuid4()}_{safe_name}"
    max_bytes = settings.MAX_DOCUMENT_UPLOAD_MB * 1024 * 1024

    written = 0
    try:
        with stored_path.open("wb") as handle:
            while chunk := await file.read(1024 * 1024):
                written += len(chunk)
                if written > max_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"Document exceeds {settings.MAX_DOCUMENT_UPLOAD_MB} MB.",
                    )
                handle.write(chunk)
    except Exception:
        if stored_path.exists():
            stored_path.unlink()
        raise
    finally:
        await file.close()

    return stored_path


def _safe_segment(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", value).strip("._") or "default"


def _safe_filename(value: str) -> str:
    stem = re.sub(r"[^a-zA-Z0-9_.-]+", "_", value).strip("._")
    return stem or "document"
