from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.documents import Document


class DocumentRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_documents(self) -> list[Document]:
        return list(self.db.scalars(select(Document).order_by(Document.created_at.desc())).all())

    def get_document(self, document_id: UUID) -> Document | None:
        return self.db.get(Document, document_id)

    def get_document_by_filename(self, filename: str) -> Document | None:
        return self.db.scalar(
            select(Document).where(func.lower(Document.filename) == filename.lower())
        )

    def add_document(self, document: Document) -> Document:
        self.db.add(document)
        self.db.flush()
        return document

    def delete_document(self, document: Document) -> None:
        self.db.delete(document)
