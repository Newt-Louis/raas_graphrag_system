from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.schemas.chat import (
    ChatRetrieveRequest,
    ChatRetrieveResponse,
    RetrievedContextResponse,
)
from app.services.retrieval.factory import get_retrieval_orchestrator
from app.services.retrieval.models import RetrievalRequest


router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/retrieve", response_model=ChatRetrieveResponse)
async def retrieve_chat_context(request: ChatRetrieveRequest) -> ChatRetrieveResponse:
    orchestrator = get_retrieval_orchestrator()
    try:
        result = orchestrator.retrieve(
            RetrievalRequest(
                tenant_id=request.tenant_id,
                app_id=request.app_id,
                collection_id=request.collection_id,
                query=request.message,
                top_k=request.top_k,
                min_score=request.min_score,
            )
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    return ChatRetrieveResponse(
        tenant_id=result.tenant_id,
        app_id=result.app_id,
        collection_id=result.collection_id,
        query=result.query,
        strategy=result.strategy,
        contexts=[
            RetrievedContextResponse(
                source=context.source,
                text=context.text,
                score=context.score,
                document_id=context.document_id,
                chunk_id=context.chunk_id,
                metadata=context.metadata,
            )
            for context in result.contexts
        ],
    )
