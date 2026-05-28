from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class GraphDatabaseScope:
    tenant_id: str
    app_id: str
    collection_id: str | None = None


@dataclass(frozen=True)
class GraphIngestResult:
    tenant_id: str
    app_id: str
    collection_id: str | None
    document_id: str
    stored_count: int
    store_path: str


@dataclass(frozen=True)
class GraphElementContext:
    element_id: str
    element_type: str
    text: str
    order_index: int
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GraphChunkContext:
    chunk_id: str
    document_id: str
    text: str
    chunk_index: int
    source_elements: list[GraphElementContext] = field(default_factory=list)
    previous_chunk_id: str | None = None
    next_chunk_id: str | None = None
    parent_chunk_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GraphContextResult:
    tenant_id: str
    app_id: str
    collection_id: str | None
    chunks: list[GraphChunkContext]
