from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class DocumentStatus(StrEnum):
    UPLOADED = "uploaded"
    PARSING = "parsing"
    INDEXING = "indexing"
    READY = "ready"
    FAILED = "failed"
    ARCHIVED = "archived"
    DELETED = "deleted"


class ElementType(StrEnum):
    TITLE = "title"
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    LIST_ITEM = "list_item"
    TABLE = "table"
    IMAGE = "image"
    CODE = "code"
    JSON_RECORD = "json_record"
    SHEET = "sheet"
    SLIDE = "slide"


class ChunkStrategy(StrEnum):
    SEMANTIC = "semantic"
    SLIDING_WINDOW = "sliding_window"
    PARENT_CHILD = "parent_child"


@dataclass(frozen=True)
class DocumentScope:
    tenant_id: str
    app_id: str
    collection_id: str | None = None


@dataclass(frozen=True)
class SourceFile:
    document_id: str
    filename: str
    extension: str
    content_type: str | None
    byte_size: int
    sha256: str
    stored_path: Path | None = None


@dataclass
class StructuralElement:
    element_id: str
    element_type: ElementType
    text: str = ""
    order: int = 0
    level: int | None = None
    page_number: int | None = None
    sheet_name: str | None = None
    slide_number: int | None = None
    table: list[list[str]] | None = None
    image_ref: str | None = None
    parent_path: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ParsedDocument:
    scope: DocumentScope
    source: SourceFile
    title: str | None
    elements: list[StructuralElement]
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ChunkingConfig:
    strategy: ChunkStrategy = ChunkStrategy.PARENT_CHILD
    max_tokens: int = 700
    overlap_tokens: int = 80
    min_tokens: int = 40
    parent_max_tokens: int = 1_800
    # Giữ lại để tương thích form cũ; chunker LlamaIndex dùng percentile bên dưới.
    semantic_similarity_threshold: float = 0.72
    # SemanticSplitterNodeParser cắt chunk khi khoảng cách ngữ nghĩa giữa các câu
    # vượt percentile này của phân phối khoảng cách. 95 là mặc định chuẩn.
    semantic_breakpoint_percentile: int = 95
    # Số câu đệm gom quanh mỗi câu khi tính embedding ranh giới (semantic).
    semantic_buffer_size: int = 1


@dataclass
class DocumentChunk:
    chunk_id: str
    document_id: str
    chunk_index: int
    text: str
    strategy: ChunkStrategy
    source_element_ids: list[str]
    content_hash: str
    parent_chunk_id: str | None = None
    is_embeddable: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class GraphRecord:
    record_id: str
    record_type: str
    properties: dict[str, Any]


@dataclass
class VectorRecord:
    vector_id: str
    text: str
    metadata: dict[str, Any]


@dataclass
class IngestionBundle:
    parsed_document: ParsedDocument
    chunks: list[DocumentChunk]
    graph_records: list[GraphRecord]
    vector_records: list[VectorRecord]
    duplicate_chunk_count: int
    warnings: list[str] = field(default_factory=list)

    @property
    def stats(self) -> dict[str, int]:
        return {
            "elements": len(self.parsed_document.elements),
            "chunks": len(self.chunks),
            "graph_records": len(self.graph_records),
            "vector_records": len(self.vector_records),
            "duplicate_chunks": self.duplicate_chunk_count,
        }
