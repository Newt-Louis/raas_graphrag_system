from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Protocol

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
_SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.!?])(?:[\"')\]]*)\s+|\n+")
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


@dataclass(frozen=True)
class _SemanticUnit:
    text: str
    embedding_text: str
    source_element_ids: list[str]
    prefix: str = ""
    prefix_element_ids: list[str] | None = None


def _token_count(text: str) -> int:
    if _TOKEN_ENCODING is not None:
        return len(_TOKEN_ENCODING.encode(text))
    return len(_TOKEN_RE.findall(text))


def _window_text(text: str, max_tokens: int, overlap_tokens: int) -> list[str]:
    if max_tokens <= 0:
        return []
    if _TOKEN_ENCODING is None:
        return _fallback_window_text(text, max_tokens, overlap_tokens)

    tokens = _TOKEN_ENCODING.encode(text)
    if not tokens:
        return []
    if len(tokens) <= max_tokens:
        return [text.strip()]

    windows: list[str] = []
    for start in _window_starts(len(tokens), max_tokens, overlap_tokens):
        window = tokens[start : start + max_tokens]
        decoded = _TOKEN_ENCODING.decode(window).strip()
        if decoded:
            windows.append(decoded)
    return windows


def _fallback_window_text(text: str, max_tokens: int, overlap_tokens: int) -> list[str]:
    tokens = _TOKEN_RE.findall(text)
    if not tokens:
        return []
    if len(tokens) <= max_tokens:
        return [" ".join(tokens)]

    windows: list[str] = []
    for start in _window_starts(len(tokens), max_tokens, overlap_tokens):
        window = tokens[start : start + max_tokens]
        windows.append(" ".join(window))
    return windows


def _window_starts(token_count: int, max_tokens: int, overlap_tokens: int) -> list[int]:
    if token_count <= max_tokens:
        return [0]
    step = max(1, max_tokens - overlap_tokens)
    starts = [0]
    while starts[-1] + max_tokens < token_count:
        next_start = starts[-1] + step
        if next_start + max_tokens >= token_count:
            next_start = token_count - max_tokens
        if next_start <= starts[-1]:
            break
        starts.append(next_start)
    return starts


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

    def _sliding_window(
        self, document: ParsedDocument, config: ChunkingConfig
    ) -> list[DocumentChunk]:
        chunks: list[DocumentChunk] = []
        for section in self._sections(document):
            section_text = self._section_text(section)
            if not section_text:
                continue
            chunks.extend(
                self._make_chunks(
                    document_id=document.source.document_id,
                    text=section_text,
                    element_ids=self._element_ids(section),
                    config=config,
                    strategy=ChunkStrategy.SLIDING_WINDOW,
                    start_index=len(chunks),
                    metadata={
                        "chunk_role": "window",
                        **_section_metadata(section),
                    },
                )
            )
        return chunks

    async def _semantic(
        self,
        document: ParsedDocument,
        config: ChunkingConfig,
        embedding_client: SemanticEmbeddingClient,
    ) -> list[DocumentChunk]:
        sections_with_units = [
            (section, self._semantic_units(section, config))
            for section in self._sections(document)
        ]
        all_units = [
            unit
            for _, units in sections_with_units
            for unit in units
        ]
        if not all_units:
            return []

        result = await embedding_client.embed_semantic_units(
            [unit.embedding_text for unit in all_units],
            tenant_id=document.scope.tenant_id,
            app_id=document.scope.app_id,
            collection_id=document.scope.collection_id,
        )
        vectors = self._semantic_vectors(result, expected_count=len(all_units))
        chunks: list[DocumentChunk] = []
        vector_offset = 0
        for section, units in sections_with_units:
            section_vectors = vectors[vector_offset : vector_offset + len(units)]
            vector_offset += len(units)
            chunks.extend(
                self._semantic_section_chunks(
                    document_id=document.source.document_id,
                    section=section,
                    units=units,
                    vectors=section_vectors,
                    config=config,
                    start_index=len(chunks),
                )
            )
        return chunks

    def _parent_child(
        self, document: ParsedDocument, config: ChunkingConfig
    ) -> list[DocumentChunk]:
        chunks: list[DocumentChunk] = []
        parent_index = 0
        parent_max_tokens = max(config.max_tokens, config.parent_max_tokens)
        for section in self._sections(document):
            section_text = self._section_text(section)
            if not section_text:
                continue

            element_ids = self._element_ids(section)
            for parent_text in _window_text(section_text, parent_max_tokens, 0):
                parent_id = f"{document.source.document_id}:parent:{parent_index}"
                parent_index += 1
                parent_metadata = {
                    "chunk_role": "parent",
                    "token_count": _token_count(parent_text),
                    **_section_metadata(section),
                }
                chunks.append(
                    DocumentChunk(
                        chunk_id=parent_id,
                        document_id=document.source.document_id,
                        chunk_index=len(chunks),
                        text=parent_text,
                        strategy=ChunkStrategy.PARENT_CHILD,
                        source_element_ids=element_ids,
                        content_hash=content_hash(parent_text),
                        is_embeddable=False,
                        metadata=parent_metadata,
                    )
                )

                for child_text in _window_text(parent_text, config.max_tokens, config.overlap_tokens):
                    chunk_index = len(chunks)
                    chunks.append(
                        DocumentChunk(
                            chunk_id=f"{document.source.document_id}:child:{chunk_index}",
                            document_id=document.source.document_id,
                            chunk_index=chunk_index,
                            text=child_text,
                            strategy=ChunkStrategy.PARENT_CHILD,
                            source_element_ids=element_ids,
                            content_hash=content_hash(child_text),
                            parent_chunk_id=parent_id,
                            is_embeddable=True,
                            metadata={
                                "chunk_role": "child",
                                "token_count": _token_count(child_text),
                                **_section_metadata(section),
                            },
                        )
                    )
        return chunks

    def _semantic_units(
        self,
        section: _StructuralSection,
        config: ChunkingConfig,
    ) -> list[_SemanticUnit]:
        units: list[_SemanticUnit] = []
        prefix_parts: list[str] = []
        prefix_element_ids: list[str] = []
        for element in section.elements:
            text = _element_text(element)
            if not text:
                continue
            if element.element_type in {ElementType.TITLE, ElementType.HEADING}:
                prefix_parts.append(text)
                prefix_element_ids.append(element.element_id)
                continue
            for part in self._semantic_element_parts(element):
                prefix = self._semantic_prefix(prefix_parts, config.max_tokens)
                prefix_tokens = _token_count(prefix)
                unit_max_tokens = max(1, config.max_tokens - prefix_tokens - (2 if prefix else 0))
                for window in _window_text(part, unit_max_tokens, min(config.overlap_tokens, unit_max_tokens - 1)):
                    units.append(
                        _SemanticUnit(
                            text=window,
                            embedding_text=f"{prefix}\n{window}".strip(),
                            source_element_ids=[element.element_id],
                            prefix=prefix,
                            prefix_element_ids=list(prefix_element_ids),
                        )
                    )

        if not units and prefix_parts:
            prefix = "\n".join(prefix_parts)
            units.append(
                _SemanticUnit(
                    text=prefix,
                    embedding_text=prefix,
                    source_element_ids=list(prefix_element_ids),
                )
            )
        return units

    def _semantic_prefix(self, prefix_parts: list[str], max_tokens: int) -> str:
        prefix = "\n".join(prefix_parts)
        if _token_count(prefix) <= max(0, max_tokens - 2):
            return prefix
        windows = _window_text(prefix, max(1, max_tokens // 4), 0)
        return windows[0] if windows else ""

    def _semantic_element_parts(self, element: StructuralElement) -> list[str]:
        text = _element_text(element)
        if not text:
            return []
        if element.element_type == ElementType.TABLE and element.table:
            return [
                " | ".join(cell.strip() for cell in row)
                for row in element.table
                if any(cell.strip() for cell in row)
            ]
        if element.element_type in {ElementType.CODE, ElementType.JSON_RECORD, ElementType.IMAGE}:
            return [text]
        return [part.strip() for part in _SENTENCE_BOUNDARY_RE.split(text) if part.strip()]

    def _semantic_vectors(self, result, *, expected_count: int) -> list[list[float]]:
        if not getattr(result, "success", False):
            raise SemanticChunkingError(
                getattr(result, "final_reason", None) or "Semantic sentence embedding failed."
            )
        vectors = getattr(result, "data", None)
        if not isinstance(vectors, list) or len(vectors) != expected_count:
            raise SemanticChunkingError(
                f"Semantic chunking received {len(vectors) if isinstance(vectors, list) else 0} "
                f"vectors for {expected_count} text units."
            )
        if not all(
            isinstance(vector, list)
            and vector
            and all(isinstance(value, (int, float)) for value in vector)
            for vector in vectors
        ):
            raise SemanticChunkingError("Semantic chunking received malformed embedding vectors.")
        return vectors

    def _semantic_section_chunks(
        self,
        *,
        document_id: str,
        section: _StructuralSection,
        units: list[_SemanticUnit],
        vectors: list[list[float]],
        config: ChunkingConfig,
        start_index: int,
    ) -> list[DocumentChunk]:
        if not units:
            return []

        chunks: list[DocumentChunk] = []
        current_units = [units[0]]
        similarities: list[float] = []
        for previous_vector, unit, vector in zip(vectors, units[1:], vectors[1:], strict=False):
            similarity = _cosine_similarity(previous_vector, vector)
            candidate_text = self._semantic_chunk_text([*current_units, unit])
            if (
                similarity < config.semantic_similarity_threshold
                or _token_count(candidate_text) > config.max_tokens
            ):
                chunks.append(
                    self._semantic_chunk(
                        document_id=document_id,
                        section=section,
                        units=current_units,
                        similarities=similarities,
                        threshold=config.semantic_similarity_threshold,
                        chunk_index=start_index + len(chunks),
                    )
                )
                current_units = [unit]
                similarities = []
                continue
            current_units.append(unit)
            similarities.append(similarity)

        chunks.append(
            self._semantic_chunk(
                document_id=document_id,
                section=section,
                units=current_units,
                similarities=similarities,
                threshold=config.semantic_similarity_threshold,
                chunk_index=start_index + len(chunks),
            )
        )
        return chunks

    def _semantic_chunk(
        self,
        *,
        document_id: str,
        section: _StructuralSection,
        units: list[_SemanticUnit],
        similarities: list[float],
        threshold: float,
        chunk_index: int,
    ) -> DocumentChunk:
        text = self._semantic_chunk_text(units)
        return DocumentChunk(
            chunk_id=f"{document_id}:semantic:{chunk_index}",
            document_id=document_id,
            chunk_index=chunk_index,
            text=text,
            strategy=ChunkStrategy.SEMANTIC,
            source_element_ids=_unique(
                [
                    element_id
                    for unit in units
                    for element_id in [*(unit.prefix_element_ids or []), *unit.source_element_ids]
                ]
            ),
            content_hash=content_hash(text),
            metadata={
                "chunk_role": "semantic",
                "semantic_unit_count": len(units),
                "semantic_similarity_threshold": threshold,
                "semantic_min_adjacent_similarity": min(similarities) if similarities else None,
                "token_count": _token_count(text),
                **_section_metadata(section),
            },
        )

    def _semantic_chunk_text(self, units: list[_SemanticUnit]) -> str:
        prefix = units[0].prefix if units else ""
        text = "\n\n".join(unit.text for unit in units if unit.text)
        if prefix and not text.startswith(prefix):
            return f"{prefix}\n\n{text}".strip()
        return text.strip()

    def _make_chunks(
        self,
        *,
        document_id: str,
        text: str,
        element_ids: list[str],
        config: ChunkingConfig,
        strategy: ChunkStrategy,
        start_index: int,
        metadata: dict[str, object] | None = None,
    ) -> list[DocumentChunk]:
        chunks: list[DocumentChunk] = []
        for offset, window in enumerate(_window_text(text, config.max_tokens, config.overlap_tokens)):
            chunk_index = start_index + offset
            chunks.append(
                DocumentChunk(
                    chunk_id=f"{document_id}:chunk:{chunk_index}",
                    document_id=document_id,
                    chunk_index=chunk_index,
                    text=window,
                    strategy=strategy,
                    source_element_ids=element_ids,
                    content_hash=content_hash(window),
                    metadata={
                        **(metadata or {}),
                        "token_count": _token_count(window),
                    },
                )
            )
        return chunks

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


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        raise SemanticChunkingError("Semantic chunking received vectors with incompatible dimensions.")
    dot = sum(float(a) * float(b) for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(float(value) ** 2 for value in left))
    right_norm = math.sqrt(sum(float(value) ** 2 for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot / (left_norm * right_norm)


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))
