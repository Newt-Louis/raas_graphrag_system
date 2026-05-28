from __future__ import annotations

from app.graphrag.graph_database import GraphDatabaseScope, KuzuGraphStore
from app.services.retrieval.models import RetrievedContext, RetrievalRequest, RetrievalResult
from app.services.vector.store import VectorSearchQuery, VectorStore


class RetrievalOrchestrator:
    """Coordinates retrieval sources before response synthesis.

    Vector retrieval selects candidate chunks. Graph retrieval then expands those
    candidates with Kuzu structural context when a graph store is configured.
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
        if self.graph_store is not None and contexts:
            graph_result = self.graph_store.chunk_context(
                scope=GraphDatabaseScope(
                    tenant_id=request.tenant_id,
                    app_id=request.app_id,
                    collection_id=request.collection_id,
                ),
                chunk_ids=[context.chunk_id for context in contexts],
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
                    },
                )
                for chunk in graph_result.chunks
            )
        return RetrievalResult(
            query=request.query,
            tenant_id=request.tenant_id,
            app_id=request.app_id,
            collection_id=request.collection_id,
            contexts=contexts,
            strategy="vector_graph" if self.graph_store is not None else "vector_only",
        )
