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
    semantic_entity_count: int = 0
    semantic_relation_count: int = 0
    semantic_mention_count: int = 0
    semantic_warnings: list[str] = field(default_factory=list)


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


@dataclass(frozen=True)
class GraphDocumentChunkStats:
    document_id: str
    chunk_count: int
    embeddable_chunk_count: int


@dataclass(frozen=True)
class SemanticEntity:
    local_id: str
    entity_type: str
    name: str
    normalized_name: str
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SemanticRelation:
    source_id: str
    target_id: str
    relation_type: str
    description: str = ""
    confidence: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SemanticExtraction:
    entities: list[SemanticEntity] = field(default_factory=list)
    relations: list[SemanticRelation] = field(default_factory=list)


@dataclass(frozen=True)
class GraphSemanticPersistResult:
    entity_count: int = 0
    relation_count: int = 0
    mention_count: int = 0


@dataclass(frozen=True)
class GraphEntityContext:
    entity_id: str
    entity_type: str
    name: str
    description: str = ""


@dataclass(frozen=True)
class GraphTraversalResult:
    tenant_id: str
    app_id: str
    collection_id: str | None
    entities: list[GraphEntityContext] = field(default_factory=list)
    chunk_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class GraphVisualizationNode:
    id: str
    node_type: str
    label: str
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GraphVisualizationEdge:
    id: str
    source: str
    target: str
    relation_type: str
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GraphVisualizationResult:
    tenant_id: str
    app_id: str
    collection_id: str | None
    document_id: str | None
    nodes: list[GraphVisualizationNode] = field(default_factory=list)
    edges: list[GraphVisualizationEdge] = field(default_factory=list)
