from __future__ import annotations

import asyncio
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Protocol

from llama_index.core.node_parser import (
    HierarchicalNodeParser,
    SemanticSplitterNodeParser,
    SentenceSplitter,
    get_leaf_nodes,
    get_root_nodes,
)
from llama_index.core.schema import BaseNode, Document, MetadataMode, NodeRelationship

from app.graphrag.llama_index import GatewayEmbedding
from app.services.ingestion.deduplication import content_hash
from app.services.ingestion.models import (
    ChunkStrategy,
    ChunkingConfig,
    DocumentChunk,
    ElementType,
    ParsedDocument,
    StructuralElement,
)

try:
    import tiktoken
except ModuleNotFoundError:  # pragma: no cover - fallback for minimal deployments
    tiktoken = None


_TOKEN_RE = re.compile(r"\S+")
_TOKEN_ENCODING = tiktoken.get_encoding("cl100k_base") if tiktoken is not None else None


class SemanticChunkingError(RuntimeError):
    pass


class SemanticEmbeddingClient(Protocol):
    async def embed_semantic_units(self, texts: list[str], **kwargs: Any):
        ...


@dataclass(frozen=True)
class _StructuralSection:
    index: int
    elements: list[StructuralElement]
    boundary_type: str | None = None
    boundary_value: str | int | None = None


def _token_count(text: str) -> int:
    if _TOKEN_ENCODING is not None:
        return len(_TOKEN_ENCODING.encode(text))
    return len(_TOKEN_RE.findall(text))


def _llama_tokenizer(text: str) -> list[Any]:
    """Tokenizer cho SentenceSplitter, khớp cách đếm token của hệ thống (cl100k)."""
    if _TOKEN_ENCODING is not None:
        return _TOKEN_ENCODING.encode(text)
    return _TOKEN_RE.findall(text)


def _element_text(element: StructuralElement) -> str:
    if element.element_type == ElementType.TABLE and element.table:
        return "\n".join(" | ".join(cell.strip() for cell in row) for row in element.table)
    if element.element_type == ElementType.IMAGE:
        label = element.metadata.get("alt_text") or element.image_ref or "embedded image"
        return f"[Image: {label}]"
    return element.text.strip()


def _section_media_metadata(section: list[StructuralElement]) -> dict[str, object]:
    media = []
    for element in section:
        if element.element_type != ElementType.IMAGE:
            continue
        media.append(
            {
                "type": "image",
                "element_id": element.element_id,
                "image_ref": element.image_ref,
                **element.metadata,
            }
        )
    return {"media": media} if media else {}


def _section_metadata(section: _StructuralSection) -> dict[str, object]:
    metadata: dict[str, object] = {
        "section_index": section.index,
        **_section_media_metadata(section.elements),
    }
    if section.boundary_type is not None:
        metadata["boundary_type"] = section.boundary_type
        metadata["boundary_value"] = section.boundary_value
    return metadata


class DocumentChunker:
    """Cắt tài liệu thành chunk bằng các node parser của LlamaIndex.

    Giữ nguyên hợp đồng đầu ra (``list[DocumentChunk]`` kèm provenance:
    ``source_element_ids``, ``parent_chunk_id``, ``is_embeddable``, ``chunk_role``,
    page/boundary) để lớp graph (Kuzu) và vector (LanceDB) phía sau không phải đổi.

    - ``sliding_window`` -> ``SentenceSplitter``
    - ``parent_child``   -> ``HierarchicalNodeParser`` (node cha + con, liên kết PARENT/CHILD)
    - ``semantic``       -> ``SemanticSplitterNodeParser`` (embedding qua gateway nội bộ)

    Mỗi structural section (đã tách theo trang/slide/sheet/heading) trở thành một
    LlamaIndex ``Document`` riêng nên chunk không vượt ranh giới trang và thừa hưởng
    đúng ``source_element_ids`` của section.
    """

    def chunk(self, document: ParsedDocument, config: ChunkingConfig) -> list[DocumentChunk]:
        if config.strategy == ChunkStrategy.SEMANTIC:
            raise SemanticChunkingError(
                "Semantic chunking requires sentence embeddings. Use chunk_async() with an embedding client."
            )
        if config.strategy == ChunkStrategy.SLIDING_WINDOW:
            return self._sliding_window(document, config)
        return self._parent_child(document, config)

    async def chunk_async(
        self,
        document: ParsedDocument,
        config: ChunkingConfig,
        *,
        semantic_embedding_client: SemanticEmbeddingClient | None = None,
    ) -> list[DocumentChunk]:
        if config.strategy != ChunkStrategy.SEMANTIC:
            return self.chunk(document, config)
        if semantic_embedding_client is None:
            raise SemanticChunkingError("Semantic chunking requires an embedding client.")
        return await self._semantic(document, config, semantic_embedding_client)

    # ------------------------------------------------------------------ sliding
    def _sliding_window(self, document: ParsedDocument, config: ChunkingConfig) -> list[DocumentChunk]:
        splitter = SentenceSplitter(
            chunk_size=max(1, config.max_tokens),
            chunk_overlap=max(0, min(config.overlap_tokens, config.max_tokens - 1)),
            tokenizer=_llama_tokenizer,
        )
        chunks: list[DocumentChunk] = []
        for llama_doc, section_meta in self._section_documents(document):
            for node in splitter.get_nodes_from_documents([llama_doc]):
                chunk = self._chunk_from_node(
                    node,
                    document_id=document.source.document_id,
                    chunk_index=len(chunks),
                    strategy=ChunkStrategy.SLIDING_WINDOW,
                    role="window",
                    is_embeddable=True,
                    chunk_id=f"{document.source.document_id}:chunk:{len(chunks)}",
                )
                if chunk is not None:
                    chunks.append(chunk)
        return chunks

    # ------------------------------------------------------------- parent_child
    def _parent_child(self, document: ParsedDocument, config: ChunkingConfig) -> list[DocumentChunk]:
        parent_size = max(config.max_tokens, config.parent_max_tokens)
        overlap = max(0, min(config.overlap_tokens, config.max_tokens - 1))
        level_splitters = [
            SentenceSplitter(chunk_size=parent_size, chunk_overlap=overlap, tokenizer=_llama_tokenizer),
            SentenceSplitter(chunk_size=config.max_tokens, chunk_overlap=overlap, tokenizer=_llama_tokenizer),
        ]
        node_parser_ids = ["parent_level", "child_level"]
        parser = HierarchicalNodeParser.from_defaults(
            node_parser_ids=node_parser_ids,
            node_parser_map=dict(zip(node_parser_ids, level_splitters, strict=True)),
        )

        documents = [llama_doc for llama_doc, _ in self._section_documents(document)]
        if not documents:
            return []
        all_nodes = parser.get_nodes_from_documents(documents)
        roots = get_root_nodes(all_nodes)
        leaves_by_parent: dict[str | None, list[BaseNode]] = defaultdict(list)
        for leaf in get_leaf_nodes(all_nodes):
            parent_info = leaf.relationships.get(NodeRelationship.PARENT)
            leaves_by_parent[parent_info.node_id if parent_info else None].append(leaf)

        chunks: list[DocumentChunk] = []
        node_id_to_chunk_id: dict[str, str] = {}
        parent_counter = 0
        child_counter = 0
        for root in roots:
            parent_chunk_id = f"{document.source.document_id}:parent:{parent_counter}"
            parent_counter += 1
            node_id_to_chunk_id[root.node_id] = parent_chunk_id
            parent_chunk = self._chunk_from_node(
                root,
                document_id=document.source.document_id,
                chunk_index=len(chunks),
                strategy=ChunkStrategy.PARENT_CHILD,
                role="parent",
                is_embeddable=False,
                chunk_id=parent_chunk_id,
            )
            if parent_chunk is None:
                continue
            chunks.append(parent_chunk)
            for leaf in leaves_by_parent.get(root.node_id, []):
                child_chunk_id = f"{document.source.document_id}:child:{child_counter}"
                child_counter += 1
                child_chunk = self._chunk_from_node(
                    leaf,
                    document_id=document.source.document_id,
                    chunk_index=len(chunks),
                    strategy=ChunkStrategy.PARENT_CHILD,
                    role="child",
                    is_embeddable=True,
                    chunk_id=child_chunk_id,
                    parent_chunk_id=parent_chunk_id,
                )
                if child_chunk is not None:
                    chunks.append(child_chunk)
        return chunks

    # ----------------------------------------------------------------- semantic
    async def _semantic(
        self,
        document: ParsedDocument,
        config: ChunkingConfig,
        embedding_client: SemanticEmbeddingClient,
    ) -> list[DocumentChunk]:
        embed_model = GatewayEmbedding(
            self._semantic_embed_fn(document, embedding_client),
            embed_batch_size=100,
        )
        parser = SemanticSplitterNodeParser(
            embed_model=embed_model,
            buffer_size=max(1, config.semantic_buffer_size),
            breakpoint_percentile_threshold=max(1, min(99, config.semantic_breakpoint_percentile)),
        )
        documents = [llama_doc for llama_doc, _ in self._section_documents(document)]
        if not documents:
            return []
        # SemanticSplitter chạy sync và gọi embedding kiểu sync; chạy trong thread
        # riêng để GatewayEmbedding bridge async->sync an toàn ngoài event loop chính.
        nodes = await asyncio.to_thread(parser.get_nodes_from_documents, documents)

        chunks: list[DocumentChunk] = []
        for node in nodes:
            chunk = self._chunk_from_node(
                node,
                document_id=document.source.document_id,
                chunk_index=len(chunks),
                strategy=ChunkStrategy.SEMANTIC,
                role="semantic",
                is_embeddable=True,
                chunk_id=f"{document.source.document_id}:semantic:{len(chunks)}",
            )
            if chunk is not None:
                chunks.append(chunk)
        return chunks

    def _semantic_embed_fn(self, document: ParsedDocument, client: SemanticEmbeddingClient):
        scope = document.scope

        async def _embed(texts: list[str]) -> list[list[float]]:
            result = await client.embed_semantic_units(
                texts,
                tenant_id=scope.tenant_id,
                app_id=scope.app_id,
                collection_id=scope.collection_id,
            )
            if not getattr(result, "success", False):
                raise SemanticChunkingError(
                    getattr(result, "final_reason", None) or "Semantic sentence embedding failed."
                )
            vectors = getattr(result, "data", None)
            if not isinstance(vectors, list) or len(vectors) != len(texts):
                raise SemanticChunkingError(
                    f"Semantic chunking received {len(vectors) if isinstance(vectors, list) else 0} "
                    f"vectors for {len(texts)} text units."
                )
            return vectors

        return _embed

    # ------------------------------------------------------------------ helpers
    def _section_documents(self, document: ParsedDocument) -> list[tuple[Document, dict[str, object]]]:
        documents: list[tuple[Document, dict[str, object]]] = []
        for section in self._sections(document):
            section_text = self._section_text(section)
            if not section_text:
                continue
            metadata: dict[str, object] = {
                **_section_metadata(section),
                "source_element_ids": self._element_ids(section),
            }
            llama_doc = Document(text=section_text, metadata=dict(metadata))
            # Không để metadata lọt vào text embedding/LLM khi parser xử lý.
            llama_doc.excluded_embed_metadata_keys = list(metadata.keys())
            llama_doc.excluded_llm_metadata_keys = list(metadata.keys())
            documents.append((llama_doc, metadata))
        return documents

    def _chunk_from_node(
        self,
        node: BaseNode,
        *,
        document_id: str,
        chunk_index: int,
        strategy: ChunkStrategy,
        role: str,
        is_embeddable: bool,
        chunk_id: str,
        parent_chunk_id: str | None = None,
    ) -> DocumentChunk | None:
        text = node.get_content(metadata_mode=MetadataMode.NONE).strip()
        if not text:
            return None
        meta = node.metadata or {}
        chunk_metadata: dict[str, Any] = {
            "chunk_role": role,
            "token_count": _token_count(text),
        }
        for key in ("section_index", "boundary_type", "boundary_value", "media"):
            if key in meta:
                chunk_metadata[key] = meta[key]
        return DocumentChunk(
            chunk_id=chunk_id,
            document_id=document_id,
            chunk_index=chunk_index,
            text=text,
            strategy=strategy,
            source_element_ids=list(meta.get("source_element_ids") or []),
            content_hash=content_hash(text),
            parent_chunk_id=parent_chunk_id,
            is_embeddable=is_embeddable,
            metadata=chunk_metadata,
        )

    def _sections(self, document: ParsedDocument) -> list[_StructuralSection]:
        sections: list[_StructuralSection] = []
        current: list[StructuralElement] = []
        current_boundary: tuple[str, str | int] | None = None

        def flush() -> None:
            nonlocal current
            if current:
                boundary_type, boundary_value = current_boundary or (None, None)
                sections.append(
                    _StructuralSection(
                        index=len(sections),
                        elements=current,
                        boundary_type=boundary_type,
                        boundary_value=boundary_value,
                    )
                )
                current = []

        for element in document.elements:
            boundary = self._hard_boundary(element)
            starts_new_heading = (
                element.element_type in {ElementType.TITLE, ElementType.HEADING}
                and bool(current)
            )
            crosses_hard_boundary = boundary is not None and current_boundary not in {None, boundary}
            if starts_new_heading or crosses_hard_boundary:
                flush()
                current_boundary = None
            if boundary is not None:
                current_boundary = boundary
            current.append(element)
        flush()
        return sections

    def _hard_boundary(self, element: StructuralElement) -> tuple[str, str | int] | None:
        if element.slide_number is not None:
            return ("slide", element.slide_number)
        if element.sheet_name:
            return ("sheet", element.sheet_name)
        if element.page_number is not None:
            return ("page", element.page_number)
        return None

    def _section_text(self, section: _StructuralSection) -> str:
        return "\n\n".join(
            text
            for element in section.elements
            if (text := _element_text(element))
        )

    def _element_ids(self, section: _StructuralSection) -> list[str]:
        return [
            element.element_id
            for element in section.elements
            if _element_text(element)
        ]
