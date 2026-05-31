from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.documents import DocumentDeleteResponse, DocumentResponse
from app.services.documents import (
    DocumentLifecycleError,
    DocumentLifecycleService,
    DocumentNotFoundError,
)


router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("", response_model=list[DocumentResponse])
def list_documents(db: Session = Depends(get_db)) -> list[DocumentResponse]:
    return DocumentLifecycleService(db).list_documents()


@router.delete("/{document_id}", response_model=DocumentDeleteResponse)
def delete_document(
    document_id: UUID,
    db: Session = Depends(get_db),
) -> DocumentDeleteResponse:
    try:
        result = DocumentLifecycleService(db).delete_document(document_id)
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except DocumentLifecycleError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
    return DocumentDeleteResponse(
        document_id=result.document_id,
        deleted_vector_count=result.deleted_vector_count,
        deleted_graph_count=result.deleted_graph_count,
    )
