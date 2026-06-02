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
from app.graphrag.graph_database import (
    GraphDatabaseScope,
    KuzuGraphStoreError,
    SemanticGraphExtractor,
    get_kuzu_graph_store,
)
from app.graphrag.ingestion_pipeline import GraphRAGIngestionPipeline
from app.graphrag.query_pipeline import GraphRAGQueryPipeline
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
    GraphChunkContextResponse,
    GraphElementContextResponse,
    SupportedFormatsResponse,
    VectorDatabaseMatchResponse,
    VectorDatabaseQueryRequest,
    VectorDatabaseQueryResponse,
)
from app.services.ai_gateway_runtime import AIGatewayRuntimeError, build_embedding_gateway, build_llm_gateway
from app.services.documents import (
    DocumentAlreadyUploadedError,
    DocumentLifecycleError,
    DocumentLifecycleService,
)
from app.services.ingestion import DocumentIngestionPipeline
from app.services.ingestion.chunking import SemanticChunkingError
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
    max_tokens: int = Form(default=700, ge=100),
    overlap_tokens: int = Form(default=80, ge=0, le=1000),
    parent_max_tokens: int = Form(default=1800, ge=100),
    semantic_similarity_threshold: float = Form(default=0.72, ge=0.0, le=1.0),
    extract_semantic_graph: bool = Form(default=True),
    llm_profile_id: UUID | None = Form(default=None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> DocumentIngestResponse:
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing filename.")

    document_service = DocumentLifecycleService(db)
    try:
        validate_document_file(file.filename, file.content_type)
        filename = document_service.ensure_filename_available(file.filename)
    except DocumentValidationError as exc:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(exc)) from exc
    except DocumentAlreadyUploadedError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    stored_path = await _store_upload(
        file=file,
        tenant_id=tenant_id,
        app_id=app_id,
    )

    pipeline = DocumentIngestionPipeline()
    chunking_config = ChunkingConfig(
        strategy=chunk_strategy,
        max_tokens=max_tokens,
        overlap_tokens=min(overlap_tokens, max_tokens - 1),
        parent_max_tokens=max(parent_max_tokens, max_tokens),
        semantic_similarity_threshold=semantic_similarity_threshold,
    )
    try:
        semantic_embedding_client = (
            GraphRAGAIClient(build_embedding_gateway(db))
            if chunk_strategy == ChunkStrategy.SEMANTIC
            else None
        )
        bundle = await pipeline.ingest_file_async(
            path=stored_path,
            scope=DocumentScope(
                tenant_id=tenant_id,
                app_id=app_id,
                collection_id=collection_id,
            ),
            filename=filename,
            content_type=file.content_type,
            chunking=chunking_config,
            semantic_embedding_client=semantic_embedding_client,
        )
    except ParserUnavailableError as exc:
        _delete_stored_upload(stored_path)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except DocumentValidationError as exc:
        _delete_stored_upload(stored_path)
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(exc)) from exc
    except AIGatewayRuntimeError as exc:
        _delete_stored_upload(stored_path)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except SemanticChunkingError as exc:
        _delete_stored_upload(stored_path)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except Exception:
        _delete_stored_upload(stored_path)
        raise

    try:
        document = document_service.register_indexing_document(
            bundle=bundle,
            chunking=chunking_config,
        )
    except DocumentAlreadyUploadedError as exc:
        _delete_stored_upload(stored_path)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except DocumentLifecycleError as exc:
        _delete_stored_upload(stored_path)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

    try:
        vector_result = await _persist_chunks_to_lancedb(
            db=db,
            tenant_id=tenant_id,
            app_id=app_id,
            collection_id=collection_id,
            chunks=bundle.chunks,
        )
        graph_result = await _persist_graph_bundle_to_kuzu(
            db=db,
            bundle=bundle,
            extract_semantic_graph=extract_semantic_graph,
            llm_profile_id=llm_profile_id,
        )
        document_service.mark_document_ready(
            document,
            vector_result=vector_result,
            graph_result=graph_result,
        )
    except Exception as exc:
        _cleanup_indexed_artifacts(bundle)
        try:
            document_service.mark_document_failed(document, reason=str(exc))
        except DocumentLifecycleError:
            pass
        raise

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
        embedding_model=vector_result.embedding_model,
        vector_table=vector_result.table_name,
        vector_stored_count=vector_result.stored_count,
        graph_store=graph_result.store_path,
        graph_stored_count=graph_result.stored_count,
        semantic_entity_count=graph_result.semantic_entity_count,
        semantic_relation_count=graph_result.semantic_relation_count,
        semantic_mention_count=graph_result.semantic_mention_count,
        warnings=[*bundle.warnings, *graph_result.semantic_warnings],
    )


@router.post("/query", response_model=VectorDatabaseQueryResponse)
async def query_vector_database(
    payload: VectorDatabaseQueryRequest,
    db: Session = Depends(get_db),
) -> VectorDatabaseQueryResponse:
    try:
        vector_pipeline = _vector_database_pipeline(
            db=db,
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
            )
        )
    except AIGatewayRuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except VectorDatabasePipelineError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    graph_context = _graph_context_for_matches(
        tenant_id=payload.tenant_id,
        app_id=payload.app_id,
        collection_id=payload.collection_id,
        chunk_ids=[match.chunk_id for match in result.matches],
    )

    return VectorDatabaseQueryResponse(
        query=result.query,
        tenant_id=result.tenant_id,
        app_id=result.app_id,
        collection_id=result.collection_id,
        vector_table=result.table_name,
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
        graph_context=graph_context,
    )


async def _persist_chunks_to_lancedb(
    *,
    db: Session,
    tenant_id: str,
    app_id: str,
    collection_id: str | None,
    chunks: list[DocumentChunk],
):
    try:
        vector_pipeline = _vector_database_pipeline(
            db=db,
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
            )
        )
    except AIGatewayRuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except VectorDatabasePipelineError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


async def _persist_graph_bundle_to_kuzu(
    *,
    db: Session,
    bundle,
    extract_semantic_graph: bool,
    llm_profile_id: UUID | None,
):
    try:
        semantic_extractor = None
        if extract_semantic_graph:
            scope = bundle.parsed_document.scope
            semantic_extractor = SemanticGraphExtractor(
                GraphRAGAIClient(
                    build_llm_gateway(
                        db,
                        tenant_id=scope.tenant_id,
                        app_id=scope.app_id,
                        profile_id=llm_profile_id,
                    )
                ),
                profile_id=str(llm_profile_id) if llm_profile_id else None,
            )
        return await GraphRAGIngestionPipeline().ingest_graph(
            bundle,
            semantic_extractor=semantic_extractor,
        )
    except AIGatewayRuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except KuzuGraphStoreError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


def _graph_context_for_matches(
    *,
    tenant_id: str,
    app_id: str,
    collection_id: str | None,
    chunk_ids: list[str],
) -> list[GraphChunkContextResponse]:
    if not chunk_ids:
        return []
    try:
        pipeline = GraphRAGQueryPipeline()
        semantic_result = pipeline.semantic_context_for_chunks(
            tenant_id=tenant_id,
            app_id=app_id,
            collection_id=collection_id,
            chunk_ids=chunk_ids,
            hops=1,
        )
        graph_result = pipeline.chunk_context(
            tenant_id=tenant_id,
            app_id=app_id,
            collection_id=collection_id,
            chunk_ids=list(dict.fromkeys([*chunk_ids, *semantic_result.chunk_ids])),
        )
        parent_chunk_ids = [
            chunk.parent_chunk_id
            for chunk in graph_result.chunks
            if chunk.parent_chunk_id
        ]
        if parent_chunk_ids:
            parent_result = pipeline.chunk_context(
                tenant_id=tenant_id,
                app_id=app_id,
                collection_id=collection_id,
                chunk_ids=list(dict.fromkeys(parent_chunk_ids)),
            )
            graph_chunks = list(
                {
                    chunk.chunk_id: chunk
                    for chunk in [*parent_result.chunks, *graph_result.chunks]
                }.values()
            )
        else:
            graph_chunks = graph_result.chunks
    except KuzuGraphStoreError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

    return [
        GraphChunkContextResponse(
            chunk_id=chunk.chunk_id,
            document_id=chunk.document_id,
            text=chunk.text,
            chunk_index=chunk.chunk_index,
            previous_chunk_id=chunk.previous_chunk_id,
            next_chunk_id=chunk.next_chunk_id,
            parent_chunk_id=chunk.parent_chunk_id,
            metadata=chunk.metadata,
            source_elements=[
                GraphElementContextResponse(
                    element_id=element.element_id,
                    element_type=element.element_type,
                    text=element.text,
                    order_index=element.order_index,
                    metadata=element.metadata,
                )
                for element in chunk.source_elements
            ],
        )
        for chunk in graph_chunks
    ]


def _vector_database_pipeline(
    *,
    db: Session,
) -> GraphRAGVectorDatabasePipeline:
    gateway = build_embedding_gateway(db)
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


def _cleanup_indexed_artifacts(bundle) -> None:
    source = bundle.parsed_document.source
    scope = bundle.parsed_document.scope
    vector_scope = VectorDatabaseScope(
        tenant_id=scope.tenant_id,
        app_id=scope.app_id,
        collection_id=scope.collection_id,
    )
    try:
        get_lancedb_vector_store().delete_document(
            scope=vector_scope,
            document_id=source.document_id,
        )
    except Exception:
        pass
    try:
        get_kuzu_graph_store().delete_document(
            scope=GraphDatabaseScope(
                tenant_id=scope.tenant_id,
                app_id=scope.app_id,
                collection_id=scope.collection_id,
            ),
            document_id=source.document_id,
        )
    except Exception:
        pass


def _delete_stored_upload(stored_path: Path) -> None:
    try:
        if stored_path.is_file():
            stored_path.unlink()
    except OSError:
        pass
