from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.graphrag.graph_database import GraphDatabaseScope, get_kuzu_graph_store
from app.graphrag.vector_database import VectorDatabaseScope
from app.graphrag.vector_database.factory import get_lancedb_vector_store
from app.models.documents import Document
from app.repositories.documents import DocumentRepository
from app.services.ingestion.models import ChunkStrategy, IngestionBundle


class DocumentLifecycleError(RuntimeError):
    pass


class DocumentAlreadyUploadedError(DocumentLifecycleError):
    pass


class DocumentNotFoundError(DocumentLifecycleError):
    pass


@dataclass(frozen=True)
class DocumentDeleteResult:
    document_id: str
    deleted_vector_count: int
    deleted_graph_count: int


class DocumentLifecycleService:
    """Coordinates the initial document registry and indexed storage cleanup."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = DocumentRepository(db)

    def list_documents(self) -> list[Document]:
        return self.repository.list_documents()

    def ensure_filename_available(self, filename: str) -> str:
        normalized_filename = Path(filename).name
        if self.repository.get_document_by_filename(normalized_filename) is not None:
            raise DocumentAlreadyUploadedError(
                f"Document '{normalized_filename}' has already been uploaded."
            )
        return normalized_filename

    def register_indexing_document(
        self,
        *,
        bundle: IngestionBundle,
        chunk_strategy: ChunkStrategy,
    ) -> Document:
        source = bundle.parsed_document.source
        scope = bundle.parsed_document.scope
        document = Document(
            id=UUID(source.document_id),
            tenant_id=None,
            app_id=None,
            collection_id=scope.collection_id,
            filename=Path(source.filename).name,
            extension=source.extension,
            content_type=source.content_type,
            byte_size=source.byte_size,
            sha256=source.sha256,
            stored_path=str(source.stored_path) if source.stored_path else None,
            status="indexing",
            chunk_count=len(bundle.chunks),
            metadata_json={
                "scope": {
                    "tenant_id": scope.tenant_id,
                    "app_id": scope.app_id,
                    "collection_id": scope.collection_id,
                },
                "chunk_strategy": chunk_strategy.value,
            },
        )
        try:
            self.repository.add_document(document)
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise DocumentAlreadyUploadedError(
                f"Document '{document.filename}' has already been uploaded."
            ) from exc
        except Exception as exc:
            self.db.rollback()
            raise DocumentLifecycleError("Document metadata could not be saved.") from exc
        return document

    def mark_document_ready(self, document: Document, *, vector_result: Any, graph_result: Any) -> Document:
        document.status = "ready"
        document.vector_record_count = vector_result.stored_count
        document.graph_record_count = graph_result.stored_count
        document.last_indexed_at = datetime.now(UTC)
        document.metadata_json = {
            **(document.metadata_json or {}),
            "embedding_model": vector_result.embedding_model,
            "semantic_entity_count": graph_result.semantic_entity_count,
            "semantic_relation_count": graph_result.semantic_relation_count,
            "semantic_mention_count": graph_result.semantic_mention_count,
        }
        self._commit_status_update("Document ready status could not be saved.")
        return document

    def mark_document_failed(self, document: Document, *, reason: str) -> Document:
        document.status = "failed"
        document.metadata_json = {
            **(document.metadata_json or {}),
            "error": reason,
        }
        self._commit_status_update("Document failed status could not be saved.")
        return document

    def delete_document(self, document_id: UUID) -> DocumentDeleteResult:
        document = self.repository.get_document(document_id)
        if document is None:
            raise DocumentNotFoundError("Document not found.")

        scope = _scope_from_document(document)
        deleted_vector_count, deleted_graph_count = self.delete_indexed_artifacts(
            scope=scope,
            document_id=str(document.id),
        )
        _delete_stored_file(document.stored_path)
        try:
            self.repository.delete_document(document)
            self.db.commit()
        except Exception as exc:
            self.db.rollback()
            raise DocumentLifecycleError("Document metadata could not be deleted.") from exc

        return DocumentDeleteResult(
            document_id=str(document.id),
            deleted_vector_count=deleted_vector_count,
            deleted_graph_count=deleted_graph_count,
        )

    def delete_indexed_artifacts(
        self,
        *,
        scope: VectorDatabaseScope,
        document_id: str,
    ) -> tuple[int, int]:
        vector_count = get_lancedb_vector_store().delete_document(
            scope=scope,
            document_id=document_id,
        )
        graph_count = get_kuzu_graph_store().delete_document(
            scope=GraphDatabaseScope(
                tenant_id=scope.tenant_id,
                app_id=scope.app_id,
                collection_id=scope.collection_id,
            ),
            document_id=document_id,
        )
        return vector_count, graph_count

    def _commit_status_update(self, error_message: str) -> None:
        try:
            self.db.commit()
        except Exception as exc:
            self.db.rollback()
            raise DocumentLifecycleError(error_message) from exc


def _scope_from_document(document: Document) -> VectorDatabaseScope:
    metadata = document.metadata_json or {}
    raw_scope = metadata.get("scope") or {}
    tenant_id = str(raw_scope.get("tenant_id") or "").strip()
    app_id = str(raw_scope.get("app_id") or "").strip()
    if not tenant_id or not app_id:
        raise DocumentLifecycleError("Document index scope metadata is missing.")
    return VectorDatabaseScope(
        tenant_id=tenant_id,
        app_id=app_id,
        collection_id=raw_scope.get("collection_id"),
    )


def _delete_stored_file(stored_path: str | None) -> None:
    if not stored_path:
        return
    path = Path(stored_path)
    try:
        if path.is_file():
            path.unlink()
    except OSError as exc:
        raise DocumentLifecycleError(f"Stored document file could not be deleted: {path}.") from exc
