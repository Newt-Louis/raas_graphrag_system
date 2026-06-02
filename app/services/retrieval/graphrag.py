from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.graphrag.ai_client import GraphRAGAIClient
from app.graphrag.graph_database import (
    GraphChunkContext,
    GraphDatabaseScope,
    GraphEntityContext,
    KuzuGraphStore,
    KuzuGraphStoreError,
    get_kuzu_graph_store,
)
from app.graphrag.vector_database import (
    GraphRAGVectorDatabasePipeline,
    VectorDatabaseScope,
    VectorMatch,
    VectorQueryRequest,
)
from app.graphrag.vector_database.factory import get_lancedb_vector_store
from app.services.ai_gateway_runtime import build_embedding_gateway


@dataclass
class GraphRAGRetrieval:
    """Unified retrieval payload shared by chat synthesis and debug endpoints."""

    scope: VectorDatabaseScope
    query: str
    vector_matches: list[VectorMatch]
    graph_chunks: list[GraphChunkContext]
    graph_entities: list[GraphEntityContext]
    strategy: str
    embedding_profile_id: str | None = None
    embedding_model: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)


class GraphRAGRetrievalService:
    """Scoped GraphRAG retrieval through the real embedding gateway and LlamaIndex.

    Embeds the query via the AI Gateway embedding profile, searches LanceDB through
    the LlamaIndex vector-store adapter, then expands grounded matches with Kuzu
    semantic/structure graph context. This is the single retrieval path used by both
    chat answer synthesis and the retrieval/debug endpoints so no caller falls back
    to a parallel local-hashing index.
    """

    def __init__(
        self,
        db: Session,
        *,
        vector_store=None,
        graph_store: KuzuGraphStore | None = None,
        embedding_ai_client: GraphRAGAIClient | None = None,
    ) -> None:
        self.db = db
        self.vector_store = vector_store or get_lancedb_vector_store()
        self.graph_store = graph_store or get_kuzu_graph_store()
        self._embedding_ai_client = embedding_ai_client

    async def retrieve(
        self,
        *,
        scope: VectorDatabaseScope,
        query: str,
        top_k: int,
        min_similarity: float,
        expand_graph: bool = True,
    ) -> GraphRAGRetrieval:
        pipeline = GraphRAGVectorDatabasePipeline(
            ai_client=self._ai_client(),
            vector_store=self.vector_store,
        )
        vector_result = await pipeline.query(
            VectorQueryRequest(
                scope=scope,
                query=query,
                top_k=top_k,
                min_similarity=min_similarity,
            )
        )
        matches = list(vector_result.matches)
        graph_chunks, graph_entities = (
            self._expand_graph_context(scope, matches) if expand_graph else ([], [])
        )
        return GraphRAGRetrieval(
            scope=scope,
            query=query,
            vector_matches=matches,
            graph_chunks=graph_chunks,
            graph_entities=graph_entities,
            strategy=_retrieval_strategy(matches, graph_chunks, graph_entities),
            embedding_profile_id=vector_result.embedding_profile_id,
            embedding_model=vector_result.embedding_model,
            usage=dict(vector_result.usage or {}),
        )

    def _ai_client(self) -> GraphRAGAIClient:
        if self._embedding_ai_client is None:
            self._embedding_ai_client = GraphRAGAIClient(build_embedding_gateway(self.db))
        return self._embedding_ai_client

    def _expand_graph_context(
        self,
        scope: VectorDatabaseScope,
        matches: list[VectorMatch],
    ) -> tuple[list[GraphChunkContext], list[GraphEntityContext]]:
        if not matches:
            return [], []
        graph_scope = GraphDatabaseScope(
            tenant_id=scope.tenant_id,
            app_id=scope.app_id,
            collection_id=scope.collection_id,
        )
        seed_chunk_ids = [match.chunk_id for match in matches]
        try:
            semantic_result = self.graph_store.semantic_context_for_chunks(
                scope=graph_scope,
                chunk_ids=seed_chunk_ids,
                hops=1,
            )
            chunk_result = self.graph_store.chunk_context(
                scope=graph_scope,
                chunk_ids=list(dict.fromkeys([*seed_chunk_ids, *semantic_result.chunk_ids])),
            )
        except KuzuGraphStoreError:
            return [], []
        return chunk_result.chunks, semantic_result.entities


def _retrieval_strategy(
    matches: list[VectorMatch],
    graph_chunks: list[GraphChunkContext],
    graph_entities: list[GraphEntityContext],
) -> str:
    if not matches:
        return "no_context"
    if graph_entities:
        return "vector_semantic_graph"
    if graph_chunks:
        return "vector_graph"
    return "vector_only"
