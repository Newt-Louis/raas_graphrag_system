from __future__ import annotations

from app.graphrag.graph_database import GraphDatabaseScope, KuzuGraphStore
from app.services.retrieval.models import RetrievedContext, RetrievalRequest, RetrievalResult
from app.services.vector.store import VectorSearchQuery, VectorStore


class RetrievalOrchestrator:
    """Coordinates retrieval sources before response synthesis.

    Vector retrieval selects candidate chunks. Graph retrieval then expands those
    candidates through semantic entities and returns Kuzu chunk context.
    """

    def __init__(self, vector_store: VectorStore, graph_store: KuzuGraphStore | None = None) -> None:
        self.vector_store = vector_store
        self.graph_store = graph_store

    def retrieve(self, request: RetrievalRequest) -> RetrievalResult:
        vector_results = self.vector_store.search(
            VectorSearchQuery(
                tenant_id=request.tenant_id,
                app_id=request.app_id,
                collection_id=request.collection_id,
                query=request.query,
                top_k=request.top_k,
                min_score=request.min_score,
            )
        )
        contexts = [
            RetrievedContext(
                source="vector",
                text=result.text,
                score=result.score,
                document_id=str(result.metadata.get("document_id") or ""),
                chunk_id=str(result.metadata.get("chunk_id") or result.vector_id),
                metadata=result.metadata,
            )
            for result in vector_results
        ]
        strategy = "vector_only"
        if self.graph_store is not None and contexts:
            scope = GraphDatabaseScope(
                tenant_id=request.tenant_id,
                app_id=request.app_id,
                collection_id=request.collection_id,
            )
            seed_chunk_ids = [context.chunk_id for context in contexts]
            semantic_result = self.graph_store.semantic_context_for_chunks(
                scope=scope,
                chunk_ids=seed_chunk_ids,
                hops=1,
            )
            graph_result = self.graph_store.chunk_context(
                scope=scope,
                chunk_ids=list(dict.fromkeys([*seed_chunk_ids, *semantic_result.chunk_ids])),
            )
            contexts.extend(
                RetrievedContext(
                    source="graph",
                    text=chunk.text,
                    score=1.0,
                    document_id=chunk.document_id,
                    chunk_id=chunk.chunk_id,
                    metadata={
                        **chunk.metadata,
                        "previous_chunk_id": chunk.previous_chunk_id,
                        "next_chunk_id": chunk.next_chunk_id,
                        "parent_chunk_id": chunk.parent_chunk_id,
                        "source_elements": [
                            {
                                "element_id": element.element_id,
                                "element_type": element.element_type,
                                "order_index": element.order_index,
                                "text": element.text,
                                "metadata": element.metadata,
                            }
                            for element in chunk.source_elements
                        ],
                        "semantic_entities": [
                            {
                                "entity_id": entity.entity_id,
                                "entity_type": entity.entity_type,
                                "name": entity.name,
                                "description": entity.description,
                            }
                            for entity in semantic_result.entities
                        ],
                    },
                )
                for chunk in graph_result.chunks
            )
            strategy = "vector_semantic_graph" if semantic_result.entities else "vector_graph"
        return RetrievalResult(
            query=request.query,
            tenant_id=request.tenant_id,
            app_id=request.app_id,
            collection_id=request.collection_id,
            contexts=contexts,
            strategy=strategy,
        )
