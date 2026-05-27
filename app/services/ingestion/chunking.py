from __future__ import annotations

import re

from app.services.ingestion.deduplication import content_hash
from app.services.ingestion.models import (
    ChunkStrategy,
    ChunkingConfig,
    DocumentChunk,
    ElementType,
    ParsedDocument,
    StructuralElement,
)


_TOKEN_RE = re.compile(r"\S+")


def _token_count(text: str) -> int:
    return len(_TOKEN_RE.findall(text))


def _window_text(text: str, max_tokens: int, overlap_tokens: int) -> list[str]:
    tokens = _TOKEN_RE.findall(text)
    if not tokens:
        return []
    if len(tokens) <= max_tokens:
        return [" ".join(tokens)]

    windows: list[str] = []
    step = max(1, max_tokens - overlap_tokens)
    for start in range(0, len(tokens), step):
        window = tokens[start : start + max_tokens]
        if not window:
            break
        windows.append(" ".join(window))
        if start + max_tokens >= len(tokens):
            break
    return windows


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


class DocumentChunker:
    def chunk(self, document: ParsedDocument, config: ChunkingConfig) -> list[DocumentChunk]:
        if config.strategy == ChunkStrategy.SLIDING_WINDOW:
            return self._sliding_window(document, config)
        if config.strategy == ChunkStrategy.SEMANTIC:
            return self._semantic(document, config)
        return self._parent_child(document, config)

    def _sliding_window(
        self, document: ParsedDocument, config: ChunkingConfig
    ) -> list[DocumentChunk]:
        text_parts = [_element_text(element) for element in document.elements]
        all_text = "\n\n".join(part for part in text_parts if part)
        element_ids = [element.element_id for element in document.elements if _element_text(element)]
        return self._make_chunks(
            document_id=document.source.document_id,
            text=all_text,
            element_ids=element_ids,
            config=config,
            strategy=ChunkStrategy.SLIDING_WINDOW,
            start_index=0,
            metadata=_section_media_metadata(document.elements),
        )

    def _semantic(self, document: ParsedDocument, config: ChunkingConfig) -> list[DocumentChunk]:
        chunks: list[DocumentChunk] = []
        for section_index, section in enumerate(self._sections(document)):
            section_text = "\n\n".join(_element_text(element) for element in section if _element_text(element))
            if not section_text:
                continue
            element_ids = [element.element_id for element in section]
            chunks.extend(
                self._make_chunks(
                    document_id=document.source.document_id,
                    text=section_text,
                    element_ids=element_ids,
                    config=config,
                    strategy=ChunkStrategy.SEMANTIC,
                    start_index=len(chunks),
                    metadata={
                        "section_index": section_index,
                        **_section_media_metadata(section),
                    },
                )
            )
        return chunks

    def _parent_child(
        self, document: ParsedDocument, config: ChunkingConfig
    ) -> list[DocumentChunk]:
        chunks: list[DocumentChunk] = []
        for section_index, section in enumerate(self._sections(document)):
            section_text = "\n\n".join(_element_text(element) for element in section if _element_text(element))
            if not section_text:
                continue

            element_ids = [element.element_id for element in section]
            parent_id = f"{document.source.document_id}:parent:{section_index}"
            parent = DocumentChunk(
                chunk_id=parent_id,
                document_id=document.source.document_id,
                chunk_index=len(chunks),
                text=section_text,
                strategy=ChunkStrategy.PARENT_CHILD,
                source_element_ids=element_ids,
                content_hash=content_hash(section_text),
                is_embeddable=False,
                metadata={
                    "chunk_role": "parent",
                    "section_index": section_index,
                    "token_count": _token_count(section_text),
                    **_section_media_metadata(section),
                },
            )
            chunks.append(parent)

            child_windows = _window_text(section_text, config.max_tokens, config.overlap_tokens)
            if len(child_windows) == 1 and _token_count(child_windows[0]) < config.min_tokens:
                child_windows = [section_text]

            for child_text in child_windows:
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
                            "section_index": section_index,
                            "token_count": _token_count(child_text),
                            **_section_media_metadata(section),
                        },
                    )
                )

        return chunks

    def _make_chunks(
        self,
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

    def _sections(self, document: ParsedDocument) -> list[list[StructuralElement]]:
        sections: list[list[StructuralElement]] = []
        current: list[StructuralElement] = []

        for element in document.elements:
            starts_new_section = (
                element.element_type in {ElementType.TITLE, ElementType.HEADING}
                and bool(current)
            )
            if starts_new_section:
                sections.append(current)
                current = []
            current.append(element)

        if current:
            sections.append(current)

        return sections
