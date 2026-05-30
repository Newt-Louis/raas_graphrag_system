from __future__ import annotations

from collections import Counter

from app.graphrag.query_pipeline import GraphRAGQueryPipeline
from app.schemas.visualize import (
    GraphVisualizationEdge,
    GraphVisualizationNode,
    GraphVisualizationRequest,
    GraphVisualizationResponse,
    GraphVisualizationStats,
)


class GraphVisualizationService:
    def __init__(self, query_pipeline: GraphRAGQueryPipeline | None = None) -> None:
        self.query_pipeline = query_pipeline or GraphRAGQueryPipeline()

    def graph_data(self, payload: GraphVisualizationRequest) -> GraphVisualizationResponse:
        result = self.query_pipeline.visualization(
            tenant_id=payload.tenant_id,
            app_id=payload.app_id,
            collection_id=payload.collection_id,
            document_id=payload.document_id,
            include_structure=payload.include_structure,
            include_semantic=payload.include_semantic,
            limit=payload.limit,
        )
        nodes = [
            GraphVisualizationNode(
                id=node.id,
                node_type=node.node_type,
                label=node.label,
                properties=node.properties,
            )
            for node in result.nodes
        ]
        edges = [
            GraphVisualizationEdge(
                id=edge.id,
                source=edge.source,
                target=edge.target,
                relation_type=edge.relation_type,
                properties=edge.properties,
            )
            for edge in result.edges
        ]
        return GraphVisualizationResponse(
            tenant_id=result.tenant_id,
            app_id=result.app_id,
            collection_id=result.collection_id,
            document_id=result.document_id,
            nodes=nodes,
            edges=edges,
            stats=GraphVisualizationStats(
                node_count=len(nodes),
                edge_count=len(edges),
                nodes_by_type=dict(Counter(node.node_type for node in nodes)),
                edges_by_type=dict(Counter(edge.relation_type for edge in edges)),
            ),
        )
