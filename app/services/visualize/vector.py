from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.graphrag.ai_client import GraphRAGAIClient
from app.graphrag.graph_database import (
    GraphDatabaseScope,
    KuzuGraphStore,
    KuzuGraphStoreError,
)
from app.graphrag.vector_database import (
    VectorDatabaseScope,
    VectorQueryRequest,
)
from app.graphrag.vector_database.lancedb_store import LanceDBPrecomputedVectorStore
from app.graphrag.vector_database.pipeline import GraphRAGVectorDatabasePipeline
from app.models.ai_gateway import EmbeddingModelProfile
from app.schemas.visualize import (
    VectorEmbeddingProfileHealthItem,
    VectorEmbeddingProfileHealthResponse,
    VectorHealthRequest,
    VectorSearchDebugMatch,
    VectorSearchDebugRequest,
    VectorSearchDebugResponse,
    VisualizeGraphChunkContext,
    VisualizeGraphElementContext,
)
from app.services.ai_gateway_runtime import build_embedding_gateway


class VisualizeInputError(ValueError):
    pass


@dataclass(frozen=True)
class _ProfileInfo:
    profile_id: str
    profile_name: str
    model_name: str
    embedding_dimension: int | None


class VectorVisualizationService:
    def __init__(
        self,
        *,
        db: Session,
        vector_store: LanceDBPrecomputedVectorStore,
        graph_store: KuzuGraphStore | None = None,
    ) -> None:
        self.db = db
        self.vector_store = vector_store
        self.graph_store = graph_store

    async def search_debug(self, payload: VectorSearchDebugRequest) -> VectorSearchDebugResponse:
        scope = VectorDatabaseScope(
            tenant_id=payload.tenant_id,
            app_id=payload.app_id,
            collection_id=payload.collection_id,
        )
        pipeline = GraphRAGVectorDatabasePipeline(
            ai_client=GraphRAGAIClient(
                build_embedding_gateway(
                    self.db,
                    rotator_options={
                        "max_attempts": 3,
                        "max_retry_same": 0,
                        "wait_for_cooldown": False,
                    },
                )
            ),
            vector_store=self.vector_store,
        )
        result = await pipeline.query(
            VectorQueryRequest(
                scope=scope,
                query=payload.query,
                top_k=payload.top_k,
                min_similarity=payload.min_similarity,
            )
        )
        graph_context = self._graph_context_by_chunk_id(
            tenant_id=payload.tenant_id,
            app_id=payload.app_id,
            collection_id=payload.collection_id,
            chunk_ids=[match.chunk_id for match in result.matches],
        )
        return VectorSearchDebugResponse(
            query=result.query,
            tenant_id=result.tenant_id,
            app_id=result.app_id,
            collection_id=result.collection_id,
            vector_table=result.table_name,
            embedding_model=result.embedding_model,
            top_k=payload.top_k,
            min_similarity=payload.min_similarity,
            usage=result.usage,
            matches=[
                VectorSearchDebugMatch(
                    rank=index,
                    vector_id=match.vector_id,
                    document_id=match.document_id,
                    chunk_id=match.chunk_id,
                    chunk_text=match.text,
                    similarity=match.similarity,
                    distance=match.distance,
                    metadata=match.metadata,
                    graph_context=graph_context.get(match.chunk_id),
                )
                for index, match in enumerate(result.matches, start=1)
            ],
        )

    def embedding_health(self, payload: VectorHealthRequest) -> VectorEmbeddingProfileHealthResponse:
        scope = VectorDatabaseScope(
            tenant_id=payload.tenant_id,
            app_id=payload.app_id,
            collection_id=payload.collection_id,
        )
        records = self.vector_store.list_records(
            scope=scope,
            document_id=payload.document_id,
            limit=payload.limit,
        )
        profiles = self._embedding_profiles()
        graph_stats = self._graph_document_stats(
            tenant_id=payload.tenant_id,
            app_id=payload.app_id,
            collection_id=payload.collection_id,
            document_id=payload.document_id,
        )

        grouped: dict[tuple[str, str | None, str | None, int | None], list] = defaultdict(list)
        for record in records:
            grouped[
                (
                    record.document_id,
                    record.embedding_profile_id,
                    record.embedding_model,
                    record.vector_dimension,
                )
            ].append(record)

        documents = [
            self._health_item(
                document_id=document_id,
                embedding_profile_id=embedding_profile_id,
                embedding_model=embedding_model,
                vector_dimension=vector_dimension,
                records=group_records,
                profile=self._profile_for_record(
                    profiles,
                    embedding_profile_id=embedding_profile_id,
                    embedding_model=embedding_model,
                ),
                graph_stats=graph_stats.get(document_id),
                collection_id=payload.collection_id,
            )
            for (
                document_id,
                embedding_profile_id,
                embedding_model,
                vector_dimension,
            ), group_records in grouped.items()
        ]
        for document_id, stats in graph_stats.items():
            if any(item.document_id == document_id for item in documents):
                continue
            documents.append(
                self._health_item(
                    document_id=document_id,
                    embedding_profile_id=None,
                    embedding_model=None,
                    vector_dimension=None,
                    records=[],
                    profile=None,
                    graph_stats=stats,
                    collection_id=payload.collection_id,
                )
            )
        documents.sort(
            key=lambda item: (
                item.document_id,
                item.embedding_profile_name or "",
                item.embedding_model or "",
                item.vector_dimension or 0,
            )
        )

        return VectorEmbeddingProfileHealthResponse(
            tenant_id=payload.tenant_id,
            app_id=payload.app_id,
            collection_id=payload.collection_id,
            vector_table=self.vector_store.table_name,
            checked_at=datetime.now(UTC),
            total_embedded_chunks=len(records),
            documents=documents,
        )

    def _health_item(
        self,
        *,
        document_id: str,
        embedding_profile_id: str | None,
        embedding_model: str | None,
        vector_dimension: int | None,
        records: list,
        profile: _ProfileInfo | None,
        graph_stats,
        collection_id: str | None,
    ) -> VectorEmbeddingProfileHealthItem:
        embedding_dimension = profile.embedding_dimension if profile else None
        graph_chunk_count = graph_stats.chunk_count if graph_stats else None
        graph_embeddable_chunk_count = graph_stats.embeddable_chunk_count if graph_stats else None
        missing_embedding_count = (
            max(0, graph_embeddable_chunk_count - len(records))
            if graph_embeddable_chunk_count is not None
            else None
        )
        return VectorEmbeddingProfileHealthItem(
            document_id=document_id,
            collection_id=collection_id or _metadata_value(records, "collection_id"),
            embedding_profile_name=profile.profile_name if profile else None,
            embedding_model=embedding_model or (profile.model_name if profile else None),
            embedding_dimension=embedding_dimension,
            vector_dimension=vector_dimension,
            dimension_status=_dimension_status(embedding_dimension, vector_dimension),
            embedded_chunk_count=len(records),
            graph_chunk_count=graph_chunk_count,
            graph_embeddable_chunk_count=graph_embeddable_chunk_count,
            missing_embedding_count=missing_embedding_count,
            source_metadata=_document_metadata(records),
            last_indexed_at=_datetime_metadata(records, "last_indexed_at") or _datetime_metadata(records, "indexed_at"),
        )

    def _embedding_profiles(self) -> dict[str, _ProfileInfo]:
        rows = self.db.scalars(select(EmbeddingModelProfile)).all()
        return {
            str(row.id): _ProfileInfo(
                profile_id=str(row.id),
                profile_name=row.profile_name,
                model_name=row.model_name,
                embedding_dimension=row.embedding_dimensions,
            )
            for row in rows
        }

    def _profile_for_record(
        self,
        profiles: dict[str, _ProfileInfo],
        *,
        embedding_profile_id: str | None,
        embedding_model: str | None,
    ) -> _ProfileInfo | None:
        profile = profiles.get(embedding_profile_id or "")
        if profile is not None or not embedding_model:
            return profile

        matching_profiles = [
            candidate
            for candidate in profiles.values()
            if _embedding_models_match(candidate.model_name, embedding_model)
        ]
        if not matching_profiles:
            return None

        dimensions = {
            candidate.embedding_dimension
            for candidate in matching_profiles
            if candidate.embedding_dimension is not None
        }
        embedding_dimension = next(iter(dimensions)) if len(dimensions) == 1 else None
        if len(matching_profiles) == 1:
            candidate = matching_profiles[0]
            return _ProfileInfo(
                profile_id=embedding_profile_id or candidate.profile_id,
                profile_name=candidate.profile_name,
                model_name=candidate.model_name,
                embedding_dimension=embedding_dimension,
            )
        return _ProfileInfo(
            profile_id=embedding_profile_id or "runtime-embedding-pool",
            profile_name="runtime embedding pool",
            model_name=embedding_model,
            embedding_dimension=embedding_dimension,
        )

    def _graph_context_by_chunk_id(
        self,
        *,
        tenant_id: str,
        app_id: str,
        collection_id: str | None,
        chunk_ids: list[str],
    ) -> dict[str, VisualizeGraphChunkContext]:
        if not self.graph_store or not chunk_ids:
            return {}
        try:
            result = self.graph_store.chunk_context(
                scope=GraphDatabaseScope(
                    tenant_id=tenant_id,
                    app_id=app_id,
                    collection_id=collection_id,
                ),
                chunk_ids=chunk_ids,
            )
        except KuzuGraphStoreError:
            return {}
        return {
            chunk.chunk_id: VisualizeGraphChunkContext(
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                text=chunk.text,
                chunk_index=chunk.chunk_index,
                previous_chunk_id=chunk.previous_chunk_id,
                next_chunk_id=chunk.next_chunk_id,
                parent_chunk_id=chunk.parent_chunk_id,
                metadata=chunk.metadata,
                source_elements=[
                    VisualizeGraphElementContext(
                        element_id=element.element_id,
                        element_type=element.element_type,
                        text=element.text,
                        order_index=element.order_index,
                        metadata=element.metadata,
                    )
                    for element in chunk.source_elements
                ],
            )
            for chunk in result.chunks
        }

    def _graph_document_stats(
        self,
        *,
        tenant_id: str,
        app_id: str,
        collection_id: str | None,
        document_id: str | None,
    ):
        if not self.graph_store:
            return {}
        try:
            return self.graph_store.document_chunk_stats(
                scope=GraphDatabaseScope(
                    tenant_id=tenant_id,
                    app_id=app_id,
                    collection_id=collection_id,
                ),
                document_id=document_id,
            )
        except KuzuGraphStoreError:
            return {}


def _dimension_status(embedding_dimension: int | None, vector_dimension: int | None) -> str:
    if embedding_dimension is None or vector_dimension is None:
        return "unknown"
    if embedding_dimension == vector_dimension:
        return "ok"
    return "mismatch"


def _embedding_models_match(configured_model: str, indexed_model: str) -> bool:
    configured = configured_model.strip().lower().strip("/")
    indexed = indexed_model.strip().lower().strip("/")
    return configured == indexed or configured.endswith(f"/{indexed}") or indexed.endswith(f"/{configured}")


def _metadata_value(records: list, key: str) -> str | None:
    for record in records:
        value = record.metadata.get(key)
        if value:
            return str(value)
    return None


def _document_metadata(records: list) -> dict[str, Any]:
    if not records:
        return {}
    metadata = dict(records[0].metadata or {})
    return {
        key: value
        for key, value in metadata.items()
        if key
        not in {
            "tenant_id",
            "app_id",
            "collection_id",
            "chunk_id",
            "chunk_index",
            "embedding_profile_id",
            "embedding_model",
        }
    }


def _datetime_metadata(records: list, key: str) -> datetime | None:
    for record in records:
        value = record.metadata.get(key)
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                continue
            return parsed
    return None
