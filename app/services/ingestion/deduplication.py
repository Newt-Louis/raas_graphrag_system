from __future__ import annotations

import hashlib
import re
from dataclasses import replace

from app.services.ingestion.models import DocumentChunk


_WHITESPACE_RE = re.compile(r"\s+")


def normalize_for_dedupe(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text).strip().lower()


def content_hash(text: str) -> str:
    normalized = normalize_for_dedupe(text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class ChunkDeduplicator:
    """Removes repeated embeddable chunks before vector indexing."""

    def dedupe(
        self,
        chunks: list[DocumentChunk],
        known_hashes: set[str] | None = None,
    ) -> tuple[list[DocumentChunk], int]:
        seen = set(known_hashes or set())
        unique: list[DocumentChunk] = []
        duplicate_count = 0

        for chunk in chunks:
            if not chunk.is_embeddable:
                unique.append(chunk)
                continue

            chunk_hash = chunk.content_hash or content_hash(chunk.text)
            if chunk_hash in seen:
                duplicate_count += 1
                continue

            seen.add(chunk_hash)
            unique.append(replace(chunk, content_hash=chunk_hash))

        return unique, duplicate_count
