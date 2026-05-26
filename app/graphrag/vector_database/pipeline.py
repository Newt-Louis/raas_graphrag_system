from __future__ import annotations

from collections.abc import Sequence
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
            [chunk.text for chunk in chunks],
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
