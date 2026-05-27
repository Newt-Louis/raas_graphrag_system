from __future__ import annotations

import base64
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from app.ai_gateway.base_rotator import RotationResult
from app.graphrag.ai_client import GraphRAGAIClient
from app.graphrag.vector_database.lancedb_store import LanceDBPrecomputedVectorStore
from app.graphrag.vector_database.models import (
    PrecomputedVectorRecord,
    VectorDocumentChunk,
    VectorIngestRequest,
    VectorIngestResult,
    VectorQueryRequest,
    VectorQueryResult,
)


class VectorDatabasePipelineError(RuntimeError):
    pass


class GraphRAGVectorDatabasePipeline:
    """Embeds document/query text through AI Gateway, then writes/searches LanceDB."""

    def __init__(self, ai_client: GraphRAGAIClient, vector_store: LanceDBPrecomputedVectorStore) -> None:
        self.ai_client = ai_client
        self.vector_store = vector_store

    async def ingest(self, request: VectorIngestRequest) -> VectorIngestResult:
        chunks = _embeddable_chunks(request.chunks)
        if not chunks:
            return VectorIngestResult(
                tenant_id=request.scope.tenant_id,
                app_id=request.scope.app_id,
                collection_id=request.scope.collection_id,
                table_name=self.vector_store.table_name,
                embedded_count=0,
                stored_count=0,
                embedding_profile_id=request.embedding_profile_id,
                embedding_model=None,
            )

        overrides: dict[str, Any] = {}
        if request.batch_size is not None:
            overrides["batch_size"] = request.batch_size

        embedding_result = await self.ai_client.embed_documents(
            [_embedding_input_from_chunk(chunk) for chunk in chunks],
            tenant_id=request.scope.tenant_id,
            app_id=request.scope.app_id,
            collection_id=request.scope.collection_id,
            profile_id=request.embedding_profile_id,
            expected_dim=request.expected_dim,
            **overrides,
        )
        vectors = _vectors_from_result(embedding_result, expected_count=len(chunks))
        records = [
            _record_from_chunk(
                chunk=chunk,
                vector=vector,
                tenant_id=request.scope.tenant_id,
                app_id=request.scope.app_id,
                collection_id=request.scope.collection_id,
                embedding_result=embedding_result,
            )
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]

        stored_count = self.vector_store.add_records(records)
        return VectorIngestResult(
            tenant_id=request.scope.tenant_id,
            app_id=request.scope.app_id,
            collection_id=request.scope.collection_id,
            table_name=self.vector_store.table_name,
            embedded_count=len(vectors),
            stored_count=stored_count,
            embedding_profile_id=embedding_result.profile_id or request.embedding_profile_id,
            embedding_model=embedding_result.used_model,
            usage=embedding_result.usage,
        )

    async def query(self, request: VectorQueryRequest) -> VectorQueryResult:
        if not request.query.strip():
            raise VectorDatabasePipelineError("Query text cannot be blank.")

        embedding_result = await self.ai_client.embed_query(
            request.query,
            tenant_id=request.scope.tenant_id,
            app_id=request.scope.app_id,
            profile_id=request.embedding_profile_id,
            expected_dim=request.expected_dim,
        )
        vectors = _vectors_from_result(embedding_result, expected_count=1)
        matches = self.vector_store.search(
            scope=request.scope,
            query_vector=vectors[0],
            top_k=request.top_k,
            min_similarity=request.min_similarity,
        )
        return VectorQueryResult(
            query=request.query,
            tenant_id=request.scope.tenant_id,
            app_id=request.scope.app_id,
            collection_id=request.scope.collection_id,
            table_name=self.vector_store.table_name,
            matches=matches,
            embedding_profile_id=embedding_result.profile_id or request.embedding_profile_id,
            embedding_model=embedding_result.used_model,
            usage=embedding_result.usage,
        )


def _embeddable_chunks(chunks: Sequence[VectorDocumentChunk]) -> list[VectorDocumentChunk]:
    return [chunk for chunk in chunks if chunk.text.strip()]


def _vectors_from_result(result: RotationResult, *, expected_count: int) -> list[list[float]]:
    if not result.success:
        reason = result.final_reason or "Embedding gateway call failed."
        raise VectorDatabasePipelineError(reason)
    if not isinstance(result.data, list):
        raise VectorDatabasePipelineError("Embedding gateway returned an invalid vector payload.")
    vectors = result.data
    if len(vectors) != expected_count:
        raise VectorDatabasePipelineError(
            f"Embedding gateway returned {len(vectors)} vectors for {expected_count} inputs."
        )
    if not all(_is_vector(vector) for vector in vectors):
        raise VectorDatabasePipelineError("Embedding gateway returned malformed vectors.")
    return vectors


def _is_vector(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, (int, float)) for item in value)


def _embedding_input_from_chunk(chunk: VectorDocumentChunk) -> Any:
    image_input = _image_embedding_input(chunk)
    if image_input is not None:
        return image_input
    return chunk.text


def _image_embedding_input(chunk: VectorDocumentChunk) -> list[dict[str, Any]] | None:
    media_items = chunk.metadata.get("media")
    if not isinstance(media_items, list):
        return None

    for media in media_items:
        if not isinstance(media, dict) or media.get("type") != "image":
            continue
        stored_path = media.get("stored_path")
        if not stored_path:
            continue
        data_url = _image_data_url(Path(str(stored_path)), str(media.get("content_type") or ""))
        if data_url is None:
            continue
        return [
            {
                "type": "text",
                "text": chunk.text or "Represent this image for semantic retrieval.",
            },
            {
                "type": "image_url",
                "image_url": {"url": data_url},
            },
        ]
    return None


def _image_data_url(path: Path, content_type: str) -> str | None:
    if not path.is_file():
        return None
    mime_type = content_type.strip().lower()
    if mime_type not in {"image/jpeg", "image/jpg", "image/png"}:
        suffix = path.suffix.lower()
        mime_type = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
        }.get(suffix, "")
    if mime_type not in {"image/jpeg", "image/jpg", "image/png"}:
        return None
    if mime_type == "image/jpg":
        mime_type = "image/jpeg"

    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _record_from_chunk(
    *,
    chunk: VectorDocumentChunk,
    vector: list[float],
    tenant_id: str,
    app_id: str,
    collection_id: str | None,
    embedding_result: RotationResult,
) -> PrecomputedVectorRecord:
    return PrecomputedVectorRecord(
        vector_id=chunk.vector_id or _default_vector_id(tenant_id, app_id, collection_id, chunk),
        vector=[float(value) for value in vector],
        text=chunk.text,
        tenant_id=tenant_id,
        app_id=app_id,
        collection_id=collection_id,
        document_id=chunk.document_id,
        chunk_id=chunk.chunk_id,
        chunk_index=chunk.chunk_index,
        embedding_profile_id=embedding_result.profile_id,
        embedding_model=embedding_result.used_model,
        metadata=dict(chunk.metadata),
    )


def _default_vector_id(
    tenant_id: str,
    app_id: str,
    collection_id: str | None,
    chunk: VectorDocumentChunk,
) -> str:
    collection_part = collection_id or "default"
    return f"{tenant_id}:{app_id}:{collection_part}:{chunk.document_id}:{chunk.chunk_id}"
