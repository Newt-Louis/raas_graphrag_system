from __future__ import annotations

from typing import Protocol

from app.services.ingestion.models import IngestionBundle


class GraphIngestionSink(Protocol):
    def persist_graph(self, bundle: IngestionBundle) -> int:
        ...


class VectorIngestionSink(Protocol):
    def persist_vectors(self, bundle: IngestionBundle) -> int:
        ...


class NoOpGraphSink:
    def persist_graph(self, bundle: IngestionBundle) -> int:
        return len(bundle.graph_records)


class NoOpVectorSink:
    def persist_vectors(self, bundle: IngestionBundle) -> int:
        return len(bundle.vector_records)


class IngestionFanoutSink:
    """Persists one parsed/chunked bundle into graph and vector targets together."""

    def __init__(
        self,
        graph_sink: GraphIngestionSink | None = None,
        vector_sink: VectorIngestionSink | None = None,
    ) -> None:
        self.graph_sink = graph_sink or NoOpGraphSink()
        self.vector_sink = vector_sink or NoOpVectorSink()

    def persist(self, bundle: IngestionBundle) -> dict[str, int]:
        return {
            "graph_records": self.graph_sink.persist_graph(bundle),
            "vector_records": self.vector_sink.persist_vectors(bundle),
        }
