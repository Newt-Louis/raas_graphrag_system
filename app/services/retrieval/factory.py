from __future__ import annotations

from app.graphrag.graph_database import get_kuzu_graph_store
from app.services.retrieval.orchestrator import RetrievalOrchestrator
from app.services.vector.factory import get_vector_store


def get_retrieval_orchestrator() -> RetrievalOrchestrator:
    return RetrievalOrchestrator(
        vector_store=get_vector_store(),
        graph_store=get_kuzu_graph_store(),
    )
