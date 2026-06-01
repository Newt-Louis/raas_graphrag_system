from __future__ import annotations

from llama_index.core.base.base_retriever import BaseRetriever
from llama_index.core.schema import NodeWithScore, QueryBundle, TextNode

from app.graphrag.graph_database.models import (
    GraphContextResult,
    GraphDatabaseScope,
    GraphTraversalResult,
)
from app.graphrag.llama_index import RetrievalOnlyQueryEngine


class LlamaIndexGraphQueryEngine:
    """Scoped Kuzu graph retrieval composed through a LlamaIndex QueryEngine."""

    def __init__(self, graph_store) -> None:
        self.graph_store = graph_store

    def chunk_context(self, *, scope: GraphDatabaseScope, chunk_ids: list[str]) -> GraphContextResult:
        retriever = _ChunkContextRetriever(self.graph_store, scope=scope, chunk_ids=chunk_ids)
        RetrievalOnlyQueryEngine(retriever).retrieve(QueryBundle(query_str="scoped graph chunk context"))
        return GraphContextResult(
            tenant_id=scope.tenant_id,
            app_id=scope.app_id,
            collection_id=scope.collection_id,
            chunks=retriever.chunks,
        )

    def entity_context(
        self,
        *,
        scope: GraphDatabaseScope,
        entity_names: list[str],
        hops: int,
    ) -> GraphTraversalResult:
        retriever = _SemanticTraversalRetriever(
            self.graph_store,
            scope=scope,
            entity_names=entity_names,
            hops=hops,
        )
        RetrievalOnlyQueryEngine(retriever).retrieve(QueryBundle(query_str="scoped graph entity traversal"))
        return retriever.result

    def semantic_context_for_chunks(
        self,
        *,
        scope: GraphDatabaseScope,
        chunk_ids: list[str],
        hops: int,
    ) -> GraphTraversalResult:
        retriever = _SemanticTraversalRetriever(
            self.graph_store,
            scope=scope,
            chunk_ids=chunk_ids,
            hops=hops,
        )
        RetrievalOnlyQueryEngine(retriever).retrieve(QueryBundle(query_str="scoped graph chunk traversal"))
        return retriever.result


class _ChunkContextRetriever(BaseRetriever):
    def __init__(self, graph_store, *, scope: GraphDatabaseScope, chunk_ids: list[str]) -> None:
        super().__init__()
        self.graph_store = graph_store
        self.scope = scope
        self.chunk_ids = chunk_ids
        self.chunks = []

    def _retrieve(self, query_bundle: QueryBundle) -> list[NodeWithScore]:
        connection = self.graph_store._connection()
        try:
            self.graph_store.ensure_schema(connection)
            self.chunks = [
                context
                for chunk_id in dict.fromkeys(self.chunk_ids)
                if (context := self.graph_store._chunk_context(connection, self.scope, chunk_id)) is not None
            ]
        finally:
            connection.close()
        return [
            NodeWithScore(
                node=TextNode(
                    id_=f"graph-context:{self.scope.tenant_id}:{self.scope.app_id}:{chunk.chunk_id}",
                    text=chunk.text,
                    metadata={"chunk_id": chunk.chunk_id, "document_id": chunk.document_id},
                ),
                score=1.0,
            )
            for chunk in self.chunks
        ]


class _SemanticTraversalRetriever(BaseRetriever):
    def __init__(
        self,
        graph_store,
        *,
        scope: GraphDatabaseScope,
        hops: int,
        entity_names: list[str] | None = None,
        chunk_ids: list[str] | None = None,
    ) -> None:
        super().__init__()
        self.graph_store = graph_store
        self.scope = scope
        self.hops = hops
        self.entity_names = entity_names
        self.chunk_ids = chunk_ids
        self.result = GraphTraversalResult(
            tenant_id=scope.tenant_id,
            app_id=scope.app_id,
            collection_id=scope.collection_id,
        )

    def _retrieve(self, query_bundle: QueryBundle) -> list[NodeWithScore]:
        connection = self.graph_store._connection()
        try:
            self.graph_store.ensure_schema(connection)
            if self.entity_names is not None:
                seed_ids = []
                for name in dict.fromkeys(self.entity_names):
                    normalized_name = _normalized_name(name)
                    if not normalized_name:
                        continue
                    rows = _rows(
                        connection.execute(
                            """
                            MATCH (e:Entity)
                            WHERE e.tenant_id = $tenant_id AND e.app_id = $app_id
                              AND e.collection_id = $collection_id AND e.normalized_name CONTAINS $name
                            RETURN e.id
                            """,
                            {**_scope_params(self.scope), "name": normalized_name},
                        )
                    )
                    seed_ids.extend(str(row[0]) for row in rows)
            else:
                chunk_node_ids = [
                    _record_node_id(self.scope, "chunk", chunk_id)
                    for chunk_id in dict.fromkeys(self.chunk_ids or [])
                ]
                seed_ids = self.graph_store._seed_entity_ids_for_chunks(connection, chunk_node_ids)
            self.result = self.graph_store._semantic_context(connection, self.scope, seed_ids, hops=self.hops)
        finally:
            connection.close()
        return [
            NodeWithScore(
                node=TextNode(id_=entity.entity_id, text=entity.name, metadata={"entity_type": entity.entity_type}),
                score=1.0,
            )
            for entity in self.result.entities
        ]


def _scope_params(scope: GraphDatabaseScope) -> dict[str, str]:
    return {
        "tenant_id": scope.tenant_id,
        "app_id": scope.app_id,
        "collection_id": scope.collection_id or "",
    }


def _record_node_id(scope: GraphDatabaseScope, record_type: str, record_id: str) -> str:
    return f"{scope.tenant_id}:{scope.app_id}:{scope.collection_id or ''}:{record_type}:{record_id}"


def _normalized_name(value: str) -> str:
    return " ".join(str(value).casefold().split())


def _rows(result) -> list[list]:
    rows = []
    while result.has_next():
        rows.append(result.get_next())
    return rows
