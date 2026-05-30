from __future__ import annotations

import unittest
from datetime import UTC, datetime
from unittest.mock import patch

from app.api.v1 import visualize
from app.schemas.visualize import (
    GraphVisualizationRequest,
    GraphVisualizationResponse,
    GraphVisualizationStats,
    VectorEmbeddingProfileHealthResponse,
    VectorHealthRequest,
)


class FakeVectorVisualizationService:
    def embedding_health(self, payload):
        return VectorEmbeddingProfileHealthResponse(
            tenant_id=payload.tenant_id,
            app_id=payload.app_id,
            collection_id=payload.collection_id,
            vector_table="document_chunks",
            checked_at=datetime.now(UTC),
            total_embedded_chunks=0,
            documents=[],
        )


class FakeGraphVisualizationService:
    def graph_data(self, payload):
        return GraphVisualizationResponse(
            tenant_id=payload.tenant_id,
            app_id=payload.app_id,
            collection_id=payload.collection_id,
            nodes=[],
            edges=[],
            stats=GraphVisualizationStats(node_count=0, edge_count=0),
        )


class VectorVisualizationApiTests(unittest.TestCase):
    def test_vector_health_route_is_registered_for_post(self) -> None:
        route = next(route for route in visualize.router.routes if route.path == "/visualize/vector/health")

        self.assertEqual(route.methods, {"POST"})

    def test_vector_health_handler_returns_service_response(self) -> None:
        with patch("app.api.v1.visualize._vector_service", return_value=FakeVectorVisualizationService()):
            response = visualize.vector_embedding_health(
                VectorHealthRequest(tenant_id="tenant-a", app_id="app-a", collection_id=None),
                db=object(),
            )

        self.assertEqual(response.vector_table, "document_chunks")

    def test_graph_visualization_route_is_registered_for_post(self) -> None:
        route = next(route for route in visualize.router.routes if route.path == "/visualize/graph")

        self.assertEqual(route.methods, {"POST"})

    def test_graph_visualization_handler_returns_service_response(self) -> None:
        with patch("app.api.v1.visualize.GraphVisualizationService", return_value=FakeGraphVisualizationService()):
            response = visualize.graph_visualization(
                GraphVisualizationRequest(tenant_id="tenant-a", app_id="app-a"),
            )

        self.assertEqual(response.stats.node_count, 0)


if __name__ == "__main__":
    unittest.main()
