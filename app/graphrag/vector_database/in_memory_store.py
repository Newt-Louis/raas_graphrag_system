from __future__ import annotations

from llama_index.core.base.base_retriever import BaseRetriever
from llama_index.core.schema import NodeWithScore, QueryBundle
from llama_index.core.vector_stores import VectorStoreQuery
from llama_index.core.vector_stores.simple import SimpleVectorStore
from llama_index.core.vector_stores.utils import build_metadata_filter_fn

from app.graphrag.llama_index import RetrievalOnlyQueryEngine
from app.graphrag.vector_database.lancedb_store import (
    _cosine_similarity,
    _scope_filters,
    _stored_record_from_node,
    _text_node_from_record,
)
from app.graphrag.vector_database.models import (
    PrecomputedVectorRecord,
    VectorDatabaseScope,
    VectorMatch,
    VectorStoredRecord,
)


class InMemoryPrecomputedVectorStore:
    """LlamaIndex SimpleVectorStore adapter for unit tests and local checks."""

    def __init__(self, table_name: str = "in_memory_vector_chunks", distance_metric: str = "cosine") -> None:
        self.table_name = table_name
        self.distance_metric = distance_metric
        self.llama_vector_store = SimpleVectorStore()
        self._nodes = {}

    def add_records(self, records: list[PrecomputedVectorRecord]) -> int:
        nodes = [_text_node_from_record(record) for record in records]
        self.llama_vector_store.delete_nodes(node_ids=[node.node_id for node in nodes])
        self.llama_vector_store.add(nodes)
        for node in nodes:
            self._nodes[node.node_id] = node
        return len(nodes)

    def search(
        self,
        *,
        scope: VectorDatabaseScope,
        query_vector: list[float],
        top_k: int = 5,
        min_similarity: float = 0.0,
    ) -> list[VectorMatch]:
        retriever = _ScopedInMemoryRetriever(
            vector_store=self.llama_vector_store,
            nodes=self._nodes,
            scope=scope,
            query_vector=query_vector,
            top_k=top_k,
        )
        nodes = RetrievalOnlyQueryEngine(retriever).retrieve(
            QueryBundle(query_str="scoped in-memory vector retrieval", embedding=query_vector)
        )
        matches = []
        for item in nodes:
            record = _stored_record_from_node(item.node)
            similarity = _cosine_similarity(query_vector, list(item.node.embedding or []))
            if similarity < min_similarity:
                continue
            matches.append(
                VectorMatch(
                    vector_id=record.vector_id,
                    document_id=record.document_id,
                    chunk_id=record.chunk_id,
                    text=record.text,
                    similarity=similarity,
                    distance=1.0 - similarity,
                    metadata=record.metadata,
                )
            )
        matches.sort(key=lambda match: match.similarity, reverse=True)
        return matches[:top_k]

    def list_records(
        self,
        *,
        scope: VectorDatabaseScope,
        document_id: str | None = None,
        limit: int = 10_000,
    ) -> list[VectorStoredRecord]:
        filters = _scope_filters(scope, document_id=document_id)
        matching_ids = _matching_ids(self.llama_vector_store, filters)
        return [
            _stored_record_from_node(self._nodes[node_id])
            for node_id in matching_ids[: max(1, limit)]
        ]

    def delete_document(self, *, scope: VectorDatabaseScope, document_id: str) -> int:
        filters = _scope_filters(scope, document_id=document_id)
        matching_ids = _matching_ids(self.llama_vector_store, filters)
        self.llama_vector_store.delete_nodes(node_ids=matching_ids)
        for node_id in matching_ids:
            self._nodes.pop(node_id, None)
        return len(matching_ids)


class _ScopedInMemoryRetriever(BaseRetriever):
    def __init__(
        self,
        *,
        vector_store: SimpleVectorStore,
        nodes: dict,
        scope: VectorDatabaseScope,
        query_vector: list[float],
        top_k: int,
    ) -> None:
        super().__init__()
        self.vector_store = vector_store
        self.nodes = nodes
        self.scope = scope
        self.query_vector = query_vector
        self.top_k = top_k

    def _retrieve(self, query_bundle: QueryBundle) -> list[NodeWithScore]:
        result = self.vector_store.query(
            VectorStoreQuery(
                query_embedding=self.query_vector,
                query_str=query_bundle.query_str,
                similarity_top_k=self.top_k,
                filters=_scope_filters(self.scope),
            )
        )
        return [
            NodeWithScore(node=self.nodes[node_id], score=score)
            for node_id, score in zip(result.ids or [], result.similarities or [], strict=True)
        ]


def _matching_ids(vector_store: SimpleVectorStore, filters) -> list[str]:
    matches = build_metadata_filter_fn(
        lambda node_id: vector_store.data.metadata_dict[node_id],
        filters,
    )
    return [node_id for node_id in vector_store.data.embedding_dict if matches(node_id)]
