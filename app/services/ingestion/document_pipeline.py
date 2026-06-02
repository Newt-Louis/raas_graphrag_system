from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from app.services.ingestion.chunking import DocumentChunker
from app.services.ingestion.chunking import SemanticEmbeddingClient
from app.services.ingestion.deduplication import ChunkDeduplicator
from app.services.ingestion.models import (
    ChunkingConfig,
    DocumentScope,
    GraphRecord,
    IngestionBundle,
    SourceFile,
    VectorRecord,
)
from app.services.ingestion.parsers import (
    DocumentParserRegistry,
    sha256_file,
    validate_document_file,
)
from app.services.ingestion.storage import IngestionFanoutSink


class DocumentIngestionPipeline:
    def __init__(
        self,
        parser_registry: DocumentParserRegistry | None = None,
        chunker: DocumentChunker | None = None,
        deduplicator: ChunkDeduplicator | None = None,
        sink: IngestionFanoutSink | None = None,
    ) -> None:
        self.parser_registry = parser_registry or DocumentParserRegistry()
        self.chunker = chunker or DocumentChunker()
        self.deduplicator = deduplicator or ChunkDeduplicator()
        self.sink = sink or IngestionFanoutSink()

    def ingest_file(
        self,
        path: Path,
        scope: DocumentScope,
        filename: str | None = None,
        content_type: str | None = None,
        chunking: ChunkingConfig | None = None,
        known_chunk_hashes: set[str] | None = None,
    ) -> IngestionBundle:
        source = self._source_file(path, filename=filename, content_type=content_type)
        parsed = self.parser_registry.parse(path, scope, source)
        raw_chunks = self.chunker.chunk(parsed, chunking or ChunkingConfig())
        return self._bundle(parsed, raw_chunks, known_chunk_hashes)

    async def ingest_file_async(
        self,
        path: Path,
        scope: DocumentScope,
        filename: str | None = None,
        content_type: str | None = None,
        chunking: ChunkingConfig | None = None,
        known_chunk_hashes: set[str] | None = None,
        semantic_embedding_client: SemanticEmbeddingClient | None = None,
    ) -> IngestionBundle:
        source = self._source_file(path, filename=filename, content_type=content_type)
        parsed = self.parser_registry.parse(path, scope, source)
        raw_chunks = await self.chunker.chunk_async(
            parsed,
            chunking or ChunkingConfig(),
            semantic_embedding_client=semantic_embedding_client,
        )
        return self._bundle(parsed, raw_chunks, known_chunk_hashes)

    def _bundle(self, parsed, raw_chunks, known_chunk_hashes: set[str] | None) -> IngestionBundle:
        chunks, duplicate_count = self.deduplicator.dedupe(raw_chunks, known_chunk_hashes)
        bundle = IngestionBundle(
            parsed_document=parsed,
            chunks=chunks,
            graph_records=self._graph_records(parsed, chunks),
            vector_records=self._vector_records(parsed.scope, chunks),
            duplicate_chunk_count=duplicate_count,
            warnings=list(parsed.warnings),
        )
        self.sink.persist(bundle)
        return bundle

    def _source_file(
        self,
        path: Path,
        filename: str | None,
        content_type: str | None,
    ) -> SourceFile:
        actual_filename = filename or path.name
        extension = validate_document_file(actual_filename, content_type)
        checksum = sha256_file(path)
        return SourceFile(
            document_id=str(uuid4()),
            filename=actual_filename,
            extension=extension,
            content_type=content_type,
            byte_size=path.stat().st_size,
            sha256=checksum,
            stored_path=path,
        )

    def _graph_records(self, parsed, chunks) -> list[GraphRecord]:
        scope_props = {
            "tenant_id": parsed.scope.tenant_id,
            "app_id": parsed.scope.app_id,
            "collection_id": parsed.scope.collection_id,
            "document_id": parsed.source.document_id,
        }
        records = [
            GraphRecord(
                record_id=parsed.source.document_id,
                record_type="document",
                properties={
                    **scope_props,
                    "filename": parsed.source.filename,
                    "title": parsed.title,
                    "sha256": parsed.source.sha256,
                    "extension": parsed.source.extension,
                },
            )
        ]

        for element in parsed.elements:
            records.append(
                GraphRecord(
                    record_id=element.element_id,
                    record_type=f"document_element:{element.element_type.value}",
                    properties={
                        **scope_props,
                        "order": element.order,
                        "level": element.level,
                        "page_number": element.page_number,
                        "sheet_name": element.sheet_name,
                        "slide_number": element.slide_number,
                        "text": element.text,
                        "table": element.table,
                        "image_ref": element.image_ref,
                        "metadata": element.metadata,
                    },
                )
            )

        for chunk in chunks:
            records.append(
                GraphRecord(
                    record_id=chunk.chunk_id,
                    record_type="document_chunk",
                    properties={
                        **scope_props,
                        "chunk_index": chunk.chunk_index,
                        "strategy": chunk.strategy.value,
                        "source_element_ids": chunk.source_element_ids,
                        "parent_chunk_id": chunk.parent_chunk_id,
                        "is_embeddable": chunk.is_embeddable,
                        "content_hash": chunk.content_hash,
                        "metadata": chunk.metadata,
                    },
                )
            )

        return records

    def _vector_records(self, scope: DocumentScope, chunks) -> list[VectorRecord]:
        records: list[VectorRecord] = []
        for chunk in chunks:
            if not chunk.is_embeddable:
                continue
            records.append(
                VectorRecord(
                    vector_id=chunk.chunk_id,
                    text=chunk.text,
                    metadata={
                        "tenant_id": scope.tenant_id,
                        "app_id": scope.app_id,
                        "collection_id": scope.collection_id,
                        "document_id": chunk.document_id,
                        "chunk_id": chunk.chunk_id,
                        "parent_chunk_id": chunk.parent_chunk_id,
                        "content_hash": chunk.content_hash,
                        "source_element_ids": chunk.source_element_ids,
                        **chunk.metadata,
                    },
                )
            )
        return records
