from __future__ import annotations

import re
from pathlib import Path
from uuid import UUID
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.graphrag.ai_client import GraphRAGAIClient
from app.graphrag.vector_database import (
    VectorDatabasePipelineError,
    VectorDatabaseScope,
    VectorDocumentChunk,
    VectorIngestRequest,
    VectorQueryRequest,
)
from app.graphrag.vector_database.factory import get_lancedb_vector_store
from app.graphrag.vector_database.pipeline import GraphRAGVectorDatabasePipeline
from app.schemas.ingest import (
    DocumentIngestResponse,
    SupportedFormatsResponse,
    VectorDatabaseMatchResponse,
    VectorDatabaseQueryRequest,
    VectorDatabaseQueryResponse,
)
from app.services.ai_gateway_runtime import AIGatewayRuntimeError, build_embedding_gateway
from app.services.ingestion import DocumentIngestionPipeline
from app.services.ingestion.models import ChunkStrategy, ChunkingConfig, DocumentChunk, DocumentScope
from app.services.ingestion.parsers import (
    ALLOWED_DOCUMENT_EXTENSIONS,
    BLOCKED_IMAGE_EXTENSIONS,
    DocumentValidationError,
    ParserUnavailableError,
    validate_document_file,
)

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
    embedding_profile_id: UUID | None = Form(default=None),
    expected_dim: int | None = Form(default=None, ge=1),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
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

    pipeline = DocumentIngestionPipeline()
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

    vector_result = await _persist_chunks_to_lancedb(
        db=db,
        tenant_id=tenant_id,
        app_id=app_id,
        collection_id=collection_id,
        chunks=bundle.chunks,
        embedding_profile_id=embedding_profile_id,
        expected_dim=expected_dim,
    )

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
        embedding_profile_id=vector_result.embedding_profile_id,
        embedding_model=vector_result.embedding_model,
        vector_table=vector_result.table_name,
        vector_stored_count=vector_result.stored_count,
        warnings=bundle.warnings,
    )


@router.post("/query", response_model=VectorDatabaseQueryResponse)
async def query_vector_database(
    payload: VectorDatabaseQueryRequest,
    db: Session = Depends(get_db),
) -> VectorDatabaseQueryResponse:
    try:
        profile_id = UUID(payload.embedding_profile_id) if payload.embedding_profile_id else None
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid embedding_profile_id.") from exc

    try:
        vector_pipeline = _vector_database_pipeline(
            db=db,
            tenant_id=payload.tenant_id,
            app_id=payload.app_id,
            embedding_profile_id=profile_id,
        )
        result = await vector_pipeline.query(
            VectorQueryRequest(
                scope=VectorDatabaseScope(
                    tenant_id=payload.tenant_id,
                    app_id=payload.app_id,
                    collection_id=payload.collection_id,
                ),
                query=payload.query,
                top_k=payload.top_k,
                min_similarity=payload.min_similarity,
                embedding_profile_id=str(profile_id) if profile_id else None,
                expected_dim=payload.expected_dim,
            )
        )
    except AIGatewayRuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except VectorDatabasePipelineError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    return VectorDatabaseQueryResponse(
        query=result.query,
        tenant_id=result.tenant_id,
        app_id=result.app_id,
        collection_id=result.collection_id,
        vector_table=result.table_name,
        embedding_profile_id=result.embedding_profile_id,
        embedding_model=result.embedding_model,
        usage=result.usage,
        matches=[
            VectorDatabaseMatchResponse(
                vector_id=match.vector_id,
                document_id=match.document_id,
                chunk_id=match.chunk_id,
                text=match.text,
                similarity=match.similarity,
                distance=match.distance,
                metadata=match.metadata,
            )
            for match in result.matches
        ],
    )


async def _persist_chunks_to_lancedb(
    *,
    db: Session,
    tenant_id: str,
    app_id: str,
    collection_id: str | None,
    chunks: list[DocumentChunk],
    embedding_profile_id: UUID | None,
    expected_dim: int | None,
):
    try:
        vector_pipeline = _vector_database_pipeline(
            db=db,
            tenant_id=tenant_id,
            app_id=app_id,
            embedding_profile_id=embedding_profile_id,
        )
        return await vector_pipeline.ingest(
            VectorIngestRequest(
                scope=VectorDatabaseScope(
                    tenant_id=tenant_id,
                    app_id=app_id,
                    collection_id=collection_id,
                ),
                chunks=[
                    VectorDocumentChunk(
                        document_id=chunk.document_id,
                        chunk_id=chunk.chunk_id,
                        vector_id=chunk.chunk_id,
                        chunk_index=chunk.chunk_index,
                        text=chunk.text,
                        metadata={
                            "parent_chunk_id": chunk.parent_chunk_id,
                            "content_hash": chunk.content_hash,
                            "source_element_ids": chunk.source_element_ids,
                            **chunk.metadata,
                        },
                    )
                    for chunk in chunks
                    if chunk.is_embeddable
                ],
                embedding_profile_id=str(embedding_profile_id) if embedding_profile_id else None,
                expected_dim=expected_dim,
            )
        )
    except AIGatewayRuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except VectorDatabasePipelineError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


def _vector_database_pipeline(
    *,
    db: Session,
    tenant_id: str,
    app_id: str,
    embedding_profile_id: UUID | None,
) -> GraphRAGVectorDatabasePipeline:
    gateway = build_embedding_gateway(
        db,
        tenant_id=tenant_id,
        app_id=app_id,
        profile_id=embedding_profile_id,
    )
    return GraphRAGVectorDatabasePipeline(
        ai_client=GraphRAGAIClient(gateway),
        vector_store=get_lancedb_vector_store(),
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
