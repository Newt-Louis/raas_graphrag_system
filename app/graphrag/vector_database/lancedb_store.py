from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from llama_index.core.base.base_retriever import BaseRetriever
from llama_index.core.schema import (
    NodeRelationship,
    NodeWithScore,
    QueryBundle,
    RelatedNodeInfo,
    TextNode,
)
from llama_index.core.vector_stores import MetadataFilter, MetadataFilters, VectorStoreQuery
from llama_index.vector_stores.lancedb import LanceDBVectorStore
from llama_index.vector_stores.lancedb.base import TableNotFoundError

from app.graphrag.llama_index import RetrievalOnlyQueryEngine
from app.graphrag.vector_database.models import (
    PrecomputedVectorRecord,
    VectorDatabaseScope,
    VectorMatch,
    VectorStoredRecord,
)


class LanceDBSchemaError(RuntimeError):
    """Raised when the on-disk LanceDB table predates the current LlamaIndex schema."""


def _raise_if_incompatible_schema(exc: Exception, table_name: str) -> None:
    message = str(exc)
    markers = ("No field named metadata", "metadata_json", "Schema error")
    if any(marker in message for marker in markers):
        raise LanceDBSchemaError(
            f"LanceDB table '{table_name}' có schema cũ không tương thích "
            f"(thiếu cột struct 'metadata'). Hãy reset data/lancedb bằng "
            f"`.venv/bin/python -m app.graphrag.reset_db` rồi ingest lại tài liệu."
        ) from exc


class LanceDBPrecomputedVectorStore:
    """Tenant-scoped LlamaIndex adapter for AI-Gateway-produced embeddings."""

    def __init__(self, db_path: Path, table_name: str, distance_metric: str = "cosine") -> None:
        self.db_path = db_path
        self.table_name = table_name
        self.distance_metric = distance_metric.lower()
        self.db_path.mkdir(parents=True, exist_ok=True)
        self._llama_vector_store: LanceDBVectorStore | None = None

    @property
    def llama_vector_store(self) -> LanceDBVectorStore:
        if self._llama_vector_store is None:
            self._llama_vector_store = LanceDBVectorStore(
                uri=str(self.db_path),
                table_name=self.table_name,
                mode="create",
                query_type="vector",
                overfetch_factor=4,
            )
        return self._llama_vector_store

    def add_records(self, records: list[PrecomputedVectorRecord]) -> int:
        if not records:
            return 0

        nodes = [_text_node_from_record(record) for record in records]
        self._delete_nodes_if_table_exists([node.node_id for node in nodes])
        self.llama_vector_store.add(nodes)
        return len(nodes)

    def search(
        self,
        *,
        scope: VectorDatabaseScope,
        query_vector: list[float],
        top_k: int = 5,
        min_similarity: float = 0.0,
    ) -> list[VectorMatch]:
        if not self._table_exists():
            return []

        retriever = _ScopedVectorRetriever(
            vector_store=self.llama_vector_store,
            scope=scope,
            query_vector=query_vector,
            top_k=top_k,
        )
        nodes = RetrievalOnlyQueryEngine(retriever).retrieve(
            QueryBundle(query_str="scoped vector retrieval", embedding=query_vector)
        )

        matches: list[VectorMatch] = []
        for item in nodes:
            record = _stored_record_from_node(item.node)
            embedding = list(item.node.embedding or [])
            similarity = _cosine_similarity(query_vector, embedding)
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
        if not self._table_exists():
            return []

        filters = _scope_filters(scope, document_id=document_id)
        try:
            nodes = self.llama_vector_store.get_nodes(filters=filters)
        except TableNotFoundError:
            return []
        except Exception as exc:
            _raise_if_incompatible_schema(exc, self.table_name)
            raise
        return [_stored_record_from_node(node) for node in nodes[: max(1, limit)]]

    def delete_document(self, *, scope: VectorDatabaseScope, document_id: str) -> int:
        records = self.list_records(scope=scope, document_id=document_id)
        self._delete_nodes_if_table_exists([record.vector_id for record in records])
        return len(records)

    def _table_exists(self) -> bool:
        return getattr(self.llama_vector_store, "_table", None) is not None

    def _delete_nodes_if_table_exists(self, node_ids: list[str]) -> None:
        if not node_ids or not self._table_exists():
            return
        try:
            self.llama_vector_store.delete_nodes(node_ids)
        except TableNotFoundError:
            return


class _ScopedVectorRetriever(BaseRetriever):
    """Feeds precomputed query embeddings through the LlamaIndex vector-store API."""

    def __init__(
        self,
        *,
        vector_store: LanceDBVectorStore,
        scope: VectorDatabaseScope,
        query_vector: list[float],
        top_k: int,
    ) -> None:
        super().__init__()
        self.vector_store = vector_store
        self.scope = scope
        self.query_vector = query_vector
        self.top_k = top_k

    def _retrieve(self, query_bundle: QueryBundle) -> list[NodeWithScore]:
        try:
            result = self.vector_store.query(
                VectorStoreQuery(
                    query_embedding=self.query_vector,
                    query_str=query_bundle.query_str,
                    similarity_top_k=self.top_k,
                    filters=_scope_filters(self.scope),
                )
            )
        except (TableNotFoundError, Warning):
            return []
        except Exception as exc:
            _raise_if_incompatible_schema(exc, getattr(self.vector_store, "table_name", "?"))
            raise
        return [
            NodeWithScore(node=node, score=score)
            for node, score in zip(result.nodes or [], result.similarities or [], strict=True)
        ]


def _text_node_from_record(record: PrecomputedVectorRecord) -> TextNode:
    metadata = {
        "tenant_id": record.tenant_id,
        "app_id": record.app_id,
        "collection_id": record.collection_id or "",
        "document_id": record.document_id,
        "chunk_id": record.chunk_id,
        "chunk_index": record.chunk_index,
        "embedding_profile_id": record.embedding_profile_id or "",
        "embedding_model": record.embedding_model or "",
        "app_metadata_json": json.dumps(record.metadata, ensure_ascii=False, sort_keys=True),
    }
    return TextNode(
        id_=record.vector_id,
        text=record.text,
        embedding=[float(value) for value in record.vector],
        metadata=metadata,
        relationships={
            NodeRelationship.SOURCE: RelatedNodeInfo(node_id=record.document_id),
        },
    )


def _stored_record_from_node(node) -> VectorStoredRecord:
    metadata = dict(node.metadata or {})
    app_metadata = _decode_metadata(metadata.get("app_metadata_json"))
    app_metadata.update(
        {
            "tenant_id": str(metadata.get("tenant_id") or ""),
            "app_id": str(metadata.get("app_id") or ""),
            "collection_id": str(metadata.get("collection_id") or "") or None,
            "document_id": str(metadata.get("document_id") or ""),
            "chunk_id": str(metadata.get("chunk_id") or node.node_id),
            "chunk_index": int(metadata.get("chunk_index") or 0),
            "embedding_profile_id": _optional_string(metadata.get("embedding_profile_id")),
            "embedding_model": _optional_string(metadata.get("embedding_model")),
        }
    )
    embedding = list(node.embedding or [])
    return VectorStoredRecord(
        vector_id=str(node.node_id),
        document_id=str(metadata.get("document_id") or ""),
        chunk_id=str(metadata.get("chunk_id") or node.node_id),
        chunk_index=int(metadata.get("chunk_index") or 0),
        text=node.get_content(),
        embedding_profile_id=_optional_string(metadata.get("embedding_profile_id")),
        embedding_model=_optional_string(metadata.get("embedding_model")),
        vector_dimension=len(embedding) or None,
        metadata=app_metadata,
    )


def _scope_filters(
    scope: VectorDatabaseScope,
    *,
    document_id: str | None = None,
) -> MetadataFilters:
    filters = [
        MetadataFilter(key="tenant_id", value=scope.tenant_id),
        MetadataFilter(key="app_id", value=scope.app_id),
    ]
    if scope.collection_id:
        filters.append(MetadataFilter(key="collection_id", value=scope.collection_id))
    if document_id:
        filters.append(MetadataFilter(key="document_id", value=document_id))
    return MetadataFilters(filters=filters)


def _decode_metadata(raw: Any) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        decoded = json.loads(str(raw))
    except json.JSONDecodeError:
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _optional_string(raw: Any) -> str | None:
    value = str(raw or "").strip()
    return value or None


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return max(0.0, min(1.0, dot / (left_norm * right_norm)))
