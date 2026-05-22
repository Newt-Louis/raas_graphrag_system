from __future__ import annotations

from app.services.retrieval.models import RetrievedContext, RetrievalRequest, RetrievalResult
from app.services.vector.store import VectorSearchQuery, VectorStore


class RetrievalOrchestrator:
    """Coordinates retrieval sources before response synthesis.

    Only vector retrieval is active now. Graph retrieval can be added here later
    without letting chat endpoints depend directly on either database.
    """

    def __init__(self, vector_store: VectorStore) -> None:
        self.vector_store = vector_store

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
        return RetrievalResult(
            query=request.query,
            tenant_id=request.tenant_id,
            app_id=request.app_id,
            collection_id=request.collection_id,
            contexts=contexts,
        )
