from __future__ import annotations

import logging
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
from app.graphrag.llama_index import GatewayLLM
from app.graphrag.vector_database import (
    GraphRAGVectorDatabasePipeline,
    VectorDatabaseScope,
    VectorMatch,
    VectorQueryRequest,
)
from app.graphrag.vector_database.factory import get_lancedb_vector_store
from app.services.ai_gateway_runtime import build_embedding_gateway

logger = logging.getLogger("graphrag.retrieval")


@dataclass
class GraphQueryBlock:
    """Một kết quả text2cypher: câu OpenCypher đã sinh và dữ liệu graph trả về."""

    text: str
    cypher: str | None = None


@dataclass
class GraphRAGRetrieval:
    """Unified retrieval payload shared by chat synthesis and debug endpoints."""

    scope: VectorDatabaseScope
    query: str
    vector_matches: list[VectorMatch]
    graph_chunks: list[GraphChunkContext]
    graph_entities: list[GraphEntityContext]
    strategy: str
    graph_query_blocks: list[GraphQueryBlock] = field(default_factory=list)
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
        router_llm: GatewayLLM | None = None,
    ) -> None:
        self.db = db
        self.vector_store = vector_store or get_lancedb_vector_store()
        self.graph_store = graph_store or get_kuzu_graph_store()
        self._embedding_ai_client = embedding_ai_client
        self.router_llm = router_llm

    async def retrieve(
        self,
        *,
        scope: VectorDatabaseScope,
        query: str,
        top_k: int,
        min_similarity: float,
        expand_graph: bool = True,
        enable_graph_query: bool = True,
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
        # Hybrid retrieval: LLM router quyết định có cần truy vấn graph (text2cypher)
        # cho câu hỏi quan hệ/đa-hop hay không. Vector luôn chạy để đảm bảo grounding.
        graph_query_blocks: list[GraphQueryBlock] = []
        if enable_graph_query:
            graph_query_blocks = await self._graph_query_blocks(scope, query)
        return GraphRAGRetrieval(
            scope=scope,
            query=query,
            vector_matches=matches,
            graph_chunks=graph_chunks,
            graph_entities=graph_entities,
            graph_query_blocks=graph_query_blocks,
            strategy=_retrieval_strategy(matches, graph_chunks, graph_entities, graph_query_blocks),
            embedding_profile_id=vector_result.embedding_profile_id,
            embedding_model=vector_result.embedding_model,
            usage=dict(vector_result.usage or {}),
        )

    async def _graph_query_blocks(
        self,
        scope: VectorDatabaseScope,
        query: str,
    ) -> list[GraphQueryBlock]:
        # Chỉ chạy text2cypher trên Kùzu thật + khi có router LLM. Với store giả
        # (unit test) hoặc thiếu LLM thì bỏ qua, vector vẫn đảm bảo grounding.
        if self.router_llm is None or not isinstance(self.graph_store, KuzuGraphStore):
            return []
        graph_scope = GraphDatabaseScope(
            tenant_id=scope.tenant_id,
            app_id=scope.app_id,
            collection_id=scope.collection_id,
        )
        try:
            import asyncio

            return await asyncio.to_thread(self._run_graph_query, graph_scope, query)
        except Exception as exc:  # noqa: BLE001 - graph query phụ trợ, không được làm vỡ chat
            logger.info("Graph text2cypher skipped: %s", str(exc)[:200])
            return []

    def _run_graph_query(self, graph_scope: GraphDatabaseScope, query: str) -> list[GraphQueryBlock]:
        from llama_index.core.schema import QueryBundle
        from llama_index.core.selectors import LLMSingleSelector

        from app.graphrag.llama_index.graph_text2cypher import build_kuzu_text2cypher_retriever

        # Router: LLM phân luồng vector-only vs cần graph traversal (đây là bộ chọn
        # mà RouterRetriever dùng bên trong). Vector vẫn luôn chạy cho grounding.
        choices = [
            "Direct factual lookup or definition answerable from a single document passage "
            "(use vector search only).",
            "Question about how entities/people/projects are connected, their relationships, "
            "or multi-hop reasoning across the knowledge graph (use graph traversal).",
        ]
        selector = LLMSingleSelector.from_defaults(llm=self.router_llm)
        selection = selector.select(choices, query=query)
        wants_graph = any(single.index == 1 for single in selection.selections)
        if not wants_graph:
            return []

        retriever = build_kuzu_text2cypher_retriever(
            graph_store=self.graph_store,
            llm=self.router_llm,
            scope=graph_scope,
        )
        nodes = retriever.retrieve(QueryBundle(query_str=query))
        blocks: list[GraphQueryBlock] = []
        for node in nodes:
            text = node.node.get_content().strip()
            if not text:
                continue
            cypher = None
            metadata = getattr(node.node, "metadata", None) or {}
            if isinstance(metadata.get("query"), str):
                cypher = metadata["query"]
            blocks.append(GraphQueryBlock(text=text, cypher=cypher))
        return blocks

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
            parent_chunk_ids = [
                chunk.parent_chunk_id
                for chunk in chunk_result.chunks
                if chunk.parent_chunk_id
            ]
            if parent_chunk_ids:
                parent_result = self.graph_store.chunk_context(
                    scope=graph_scope,
                    chunk_ids=list(dict.fromkeys(parent_chunk_ids)),
                )
                graph_chunks = list(
                    {
                        chunk.chunk_id: chunk
                        for chunk in [*parent_result.chunks, *chunk_result.chunks]
                    }.values()
                )
            else:
                graph_chunks = chunk_result.chunks
        except KuzuGraphStoreError:
            return [], []
        return graph_chunks, semantic_result.entities


def _retrieval_strategy(
    matches: list[VectorMatch],
    graph_chunks: list[GraphChunkContext],
    graph_entities: list[GraphEntityContext],
    graph_query_blocks: list[GraphQueryBlock] | None = None,
) -> str:
    base = "no_context"
    if matches:
        if graph_entities:
            base = "vector_semantic_graph"
        elif graph_chunks:
            base = "vector_graph"
        else:
            base = "vector_only"
    if graph_query_blocks:
        return f"{base}+text2cypher"
    return base
